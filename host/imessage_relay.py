#!/usr/bin/env python3
"""HTTP relay: принимает текст от Docker-бота и отправляет iMessage через Messages.app."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("IMESSAGE_RELAY_PORT", "8765"))
HOST = os.environ.get("IMESSAGE_RELAY_HOST", "127.0.0.1")
TOKEN = os.environ.get("IMESSAGE_RELAY_TOKEN", "").strip()


def parse_recipients(raw: str) -> list[str]:
    return [part for part in re.split(r"[,;\s]+", raw.strip()) if part]


RECIPIENTS = parse_recipients(os.environ.get("IMESSAGE_TO", ""))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("imessage-relay")


def applescript_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def applescript_string(text: str) -> str:
    parts = text.split("\n")
    if len(parts) == 1:
        return f'"{applescript_escape(parts[0])}"'
    return " & return & ".join(f'"{applescript_escape(part)}"' for part in parts)


def send_imessage(recipient: str, message: str) -> None:
    body = applescript_string(message)
    recipient_escaped = applescript_escape(recipient)
    script = f"""
tell application "Messages"
    set targetService to 1st account whose service type = iMessage
    set targetBuddy to participant "{recipient_escaped}" of targetService
    send {body} to targetBuddy
end tell
""".strip()

    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "unknown error").strip()
        raise RuntimeError(detail)


def send_imessage_to_all(message: str) -> tuple[list[str], list[str]]:
    sent: list[str] = []
    failed: list[str] = []

    for recipient in RECIPIENTS:
        try:
            send_imessage(recipient, message)
        except RuntimeError as exc:
            log.error("Messages.app error for %s: %s", recipient, exc)
            failed.append(recipient)
        else:
            log.info("Sent iMessage to %s (%d chars)", recipient, len(message))
            sent.append(recipient)

    return sent, failed


class RelayHandler(BaseHTTPRequestHandler):
    server_version = "GIA9iMessageRelay/1.0"

    def log_message(self, fmt: str, *args) -> None:
        log.info("%s - %s", self.address_string(), fmt % args)

    def _authorized(self) -> bool:
        if not TOKEN:
            return True
        auth = self.headers.get("Authorization", "")
        return auth == f"Bearer {TOKEN}"

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.rstrip("/") == "/health":
            self._send_json(200, {"ok": True, "recipients": RECIPIENTS})
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path.rstrip("/") != "/notify":
            self._send_json(404, {"error": "not found"})
            return

        if not self._authorized():
            self._send_json(401, {"error": "unauthorized"})
            return

        if not RECIPIENTS:
            self._send_json(500, {"error": "IMESSAGE_TO is not configured"})
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(400, {"error": "invalid json"})
            return

        message = str(payload.get("message", "")).strip()
        if not message:
            self._send_json(400, {"error": "message is required"})
            return

        sent, failed = send_imessage_to_all(message)
        if not sent:
            self._send_json(502, {"error": "failed for all recipients", "failed": failed})
            return

        self._send_json(
            200,
            {"ok": True, "sent": sent, "failed": failed or None},
        )


def main() -> None:
    if sys.platform != "darwin":
        log.error("iMessage relay работает только на macOS")
        sys.exit(1)

    if not RECIPIENTS:
        log.error("Задайте IMESSAGE_TO (один или несколько номеров через запятую)")
        sys.exit(1)

    server = ThreadingHTTPServer((HOST, PORT), RelayHandler)
    log.info(
        "Listening on http://%s:%d (recipients: %s)",
        HOST,
        PORT,
        ", ".join(RECIPIENTS),
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Stopped")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
