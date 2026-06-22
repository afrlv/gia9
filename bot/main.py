#!/usr/bin/env python3
import json
import logging
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, time as dt_time, timedelta
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

BASE_URL = os.environ.get("GIA_BASE_URL", "https://rcoi02.ru/gia9_result/")
LOGIN_URL = urljoin(BASE_URL, "lk/pageall.php")
STATE_PATH = Path(os.environ.get("STATE_FILE", "/data/state.json"))
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL_SECONDS", "300"))
TIMEZONE = ZoneInfo(os.environ.get("TZ", "Asia/Yekaterinburg"))
QUIET_HOURS_ENABLED = os.environ.get("QUIET_HOURS_ENABLED", "true").lower() in {
    "1",
    "true",
    "yes",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("gia9")


@dataclass(frozen=True)
class ExamResult:
    result_id: str
    date: str
    exam_form: str
    subject: str
    score: str
    grade: str
    status: str
    appeal: str
    school_year: str

    def summary(self) -> str:
        return (
            f"{self.date} — {self.subject} ({self.exam_form})\n"
            f"Балл: {self.score}, отметка: {self.grade}\n"
            f"Статус: {self.status}, апелляция: {self.appeal}"
        )


def parse_hhmm(value: str, name: str) -> dt_time:
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", value.strip())
    if not match:
        log.error("%s должен быть в формате HH:MM, получено: %s", name, value)
        sys.exit(1)
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        log.error("%s содержит недопустимое время: %s", name, value)
        sys.exit(1)
    return dt_time(hour, minute)


QUIET_HOURS_START = parse_hhmm(
    os.environ.get("QUIET_HOURS_START", "23:00"), "QUIET_HOURS_START"
)
QUIET_HOURS_END = parse_hhmm(
    os.environ.get("QUIET_HOURS_END", "8:00"), "QUIET_HOURS_END"
)


def is_quiet_hours(now: datetime | None = None) -> bool:
    if not QUIET_HOURS_ENABLED:
        return False

    current = (now or datetime.now(TIMEZONE)).time()
    start, end = QUIET_HOURS_START, QUIET_HOURS_END

    if start == end:
        return True
    if start < end:
        return start <= current < end
    return current >= start or current < end


def seconds_until_checks_resume(
    now: datetime | None = None,
) -> tuple[int, datetime]:
    now = now or datetime.now(TIMEZONE)
    if not is_quiet_hours(now):
        return 0, now

    resume_at = datetime.combine(now.date(), QUIET_HOURS_END, tzinfo=TIMEZONE)
    if now.time() >= QUIET_HOURS_START:
        resume_at += timedelta(days=1)

    pause = max(1, int((resume_at - now).total_seconds()))
    return pause, resume_at


def format_duration(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours} ч {minutes} мин"
    if minutes:
        return f"{minutes} мин {secs} сек"
    return f"{secs} сек"


def wait_for_active_hours() -> None:
    while True:
        if not is_quiet_hours():
            return

        now = datetime.now(TIMEZONE)
        pause, resume_at = seconds_until_checks_resume(now)

        log.info(
            "Тихие часы %s–%s (%s): проверки приостановлены, возобновление через %s (в %s)",
            QUIET_HOURS_START.strftime("%H:%M"),
            QUIET_HOURS_END.strftime("%H:%M"),
            TIMEZONE.key,
            format_duration(pause),
            resume_at.strftime("%H:%M"),
        )
        time.sleep(min(pause, 300))


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        log.error("Переменная окружения %s не задана", name)
        sys.exit(1)
    return value


def load_state() -> dict[str, dict]:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Не удалось прочитать state (%s), начинаем с пустого", exc)
        return {}


def save_state(results: dict[str, dict]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def extract_result_id(link_href: str) -> str:
    match = re.search(r"id=(\d+)", link_href)
    if match:
        return match.group(1)
    return link_href


def parse_results(html: str) -> list[ExamResult]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.tb_result")
    if table is None:
        return []

    rows = table.select("tr")[1:]
    results: list[ExamResult] = []

    for row in rows:
        cells = row.find_all("td")
        if len(cells) != 8:
            continue

        subject_link = cells[2].find("a")
        subject = subject_link.get_text(strip=True) if subject_link else cells[2].get_text(strip=True)
        href = subject_link.get("href", "") if subject_link else ""
        result_id = extract_result_id(href) if href else f"{cells[0].get_text(strip=True)}:{subject}"

        results.append(
            ExamResult(
                result_id=result_id,
                date=cells[0].get_text(strip=True),
                exam_form=cells[1].get_text(strip=True),
                subject=subject,
                score=cells[3].get_text(strip=True),
                grade=cells[4].get_text(strip=True),
                status=cells[5].get_text(strip=True),
                appeal=cells[6].get_text(strip=True),
                school_year=cells[7].get_text(strip=True),
            )
        )

    return results


def login(session: requests.Session) -> str:
    family = required_env("GIA_FAMILY")
    name = required_env("GIA_NAME")
    father = required_env("GIA_FATHER")
    passport = required_env("GIA_PASSPORT")
    region = os.environ.get("GIA_REGION", "Республика Башкортостан")

    if not re.fullmatch(r"\d{6}", passport):
        log.error("GIA_PASSPORT должен содержать ровно 6 цифр")
        sys.exit(1)

    session.get(BASE_URL, timeout=30)

    response = session.post(
        LOGIN_URL,
        data={
            "family": family,
            "name": name,
            "father": father,
            "number": passport,
            "region": region,
            "pd": "on",
            "do": "Войти",
        },
        timeout=30,
    )
    response.raise_for_status()
    response.encoding = "utf-8"
    return response.text


def is_logged_in(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    if soup.select_one("table.tb_result") is not None:
        return True
    if soup.select_one("div.user") is not None:
        return True
    return False


def send_telegram(message: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return

    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": message},
        timeout=30,
    )
    response.raise_for_status()


def imessage_enabled() -> bool:
    return os.environ.get("IMESSAGE_ENABLED", "").lower() in {"1", "true", "yes"}


def send_imessage(message: str) -> None:
    if not imessage_enabled():
        return

    relay_url = os.environ.get(
        "IMESSAGE_RELAY_URL", "http://host.docker.internal:8765"
    ).rstrip("/")
    headers: dict[str, str] = {}
    token = os.environ.get("IMESSAGE_RELAY_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    response = requests.post(
        f"{relay_url}/notify",
        json={"message": message},
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()


def notify_new_results(new_results: list[ExamResult]) -> None:
    header = "Новые результаты ГИА-9:"
    lines = [header, ""]
    for result in new_results:
        lines.append(result.summary())
        lines.append("")

    message = "\n".join(lines).strip()
    log.info("Новые результаты:\n%s", message)

    try:
        send_telegram(message)
    except requests.RequestException as exc:
        log.warning("Не удалось отправить Telegram: %s", exc)

    try:
        send_imessage(message)
    except requests.RequestException as exc:
        log.warning("Не удалось отправить iMessage: %s", exc)


def check_once(
    session: requests.Session,
    known: dict[str, dict],
    *,
    notify: bool = True,
) -> dict[str, dict]:
    html = login(session)
    if not is_logged_in(html):
        raise RuntimeError("Не удалось войти — проверьте учётные данные")

    current = parse_results(html)
    if not current:
        log.info("Таблица результатов пуста или недоступна")
        return known

    current_map = {r.result_id: asdict(r) for r in current}
    new_ids = set(current_map) - set(known)

    if new_ids and notify:
        new_results = [ExamResult(**current_map[rid]) for rid in sorted(new_ids)]
        notify_new_results(new_results)
    elif new_ids:
        log.info("Сохранено %d результатов в baseline без уведомлений", len(new_ids))
    else:
        log.info("Новых результатов нет (%d записей)", len(current))

    for result in current:
        log.info(
            "%s | %s | %s | балл %s | %s",
            result.date,
            result.subject,
            result.exam_form,
            result.score,
            result.grade,
        )

    return current_map


def main() -> None:
    log.info("Старт мониторинга ГИА-9, интервал %d сек", CHECK_INTERVAL)
    if QUIET_HOURS_ENABLED:
        log.info(
            "Тихие часы: %s–%s (%s), проверки только днём",
            QUIET_HOURS_START.strftime("%H:%M"),
            QUIET_HOURS_END.strftime("%H:%M"),
            TIMEZONE.key,
        )
    if imessage_enabled():
        relay_url = os.environ.get(
            "IMESSAGE_RELAY_URL", "http://host.docker.internal:8765"
        )
        log.info("iMessage включён, relay: %s", relay_url)

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "ru-RU,ru;q=0.9",
        }
    )

    known = load_state()
    if known:
        log.info("Загружено %d известных результатов из state", len(known))

    seed_pending = (
        os.environ.get("SEED_STATE", "").lower() in {"1", "true", "yes"} and not known
    )
    if seed_pending:
        log.info("Режим SEED_STATE: сохраняем текущие результаты без уведомлений")

    while True:
        wait_for_active_hours()

        try:
            previous = dict(known)
            known = check_once(session, known, notify=not seed_pending)

            if seed_pending:
                seed_pending = False
                log.info("Baseline сохранён, дальше будем уведомлять только о новых")

            if known != previous:
                save_state(known)
        except Exception as exc:
            log.exception("Ошибка при проверке: %s", exc)

        if is_quiet_hours():
            continue

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
