# gia9 — монитор результатов ГИА-9

Автоматический мониторинг результатов государственной итоговой аттестации (ГИА-9) на сайте [rcoi02.ru/gia9_result](https://rcoi02.ru/gia9_result/). Бот периодически входит в личный кабинет участника, сравнивает таблицу результатов с сохранённым состоянием и отправляет уведомление, когда появляются **новые** строки (новый предмет, балл, статус и т.д.).

Подходит для родителей и участников, которые хотят узнать о публикации результатов сразу, без ручной проверки сайта.

## Возможности

- Авторизация на портале РЦОИ по ФИО, региону и 6 цифрам паспорта
- Периодическая проверка (по умолчанию каждые 5 минут)
- Режим **SEED_STATE** — при первом запуске сохраняет текущие результаты без уведомлений, чтобы не спамить уже известными оценками
- **Тихие часы** — опциональная пауза проверок ночью (например, 23:00–8:00)
- Уведомления через **iMessage** (macOS) и/или **Telegram**
- Запуск в **Docker** с сохранением состояния в volume
- Автозапуск на macOS через **launchd**

## Архитектура

```
┌─────────────────┐     HTTP POST      ┌──────────────────────┐     AppleScript     ┌─────────────┐
│  gia9-monitor   │ ─────────────────► │  imessage_relay.py   │ ──────────────────► │ Messages.app│
│  (Docker)       │   /notify          │  (macOS, localhost)  │                     │  (iMessage) │
└────────┬────────┘                    └──────────────────────┘                     └─────────────┘
         │
         │  POST /gia9_result/lk/pageall.php
         ▼
┌─────────────────┐
│   rcoi02.ru     │
│  (таблица       │
│   tb_result)    │
└─────────────────┘
```

Docker-контейнер не имеет доступа к Messages.app, поэтому на Mac запускается локальный HTTP-relay (`host/imessage_relay.py`), который принимает текст от бота и отправляет iMessage через AppleScript.

## Требования

- **Docker Desktop** (для мониторинга)
- **macOS** — только если нужны уведомления через iMessage
- Учётные данные участника ГИА-9 (как при входе на сайт)

## Быстрый старт

1. Клонируйте репозиторий и перейдите в каталог:

```bash
git clone https://github.com/afrlv/gia9.git
cd gia9
```

2. Скопируйте `.env.example` в `.env` и заполните данные участника:

```bash
cp .env.example .env
```

Обязательные поля: `GIA_FAMILY`, `GIA_NAME`, `GIA_FATHER`, `GIA_PASSPORT` (6 цифр), `GIA_REGION`.

3. Запустите монитор и (при необходимости) iMessage-relay:

```bash
chmod +x scripts/*.sh
./scripts/start-all.sh
```

4. Смотрите логи:

```bash
docker compose logs -f
tail -f .data/relay.log   # лог iMessage-relay
```

5. Остановка:

```bash
./scripts/stop-all.sh
```

### Автозапуск при входе в macOS

```bash
./scripts/install-autostart.sh
```

Создаёт два launchd-агента: relay iMessage и периодический запуск Docker-контейнера.

## Как это работает

1. Бот отправляет POST на `/gia9_result/lk/pageall.php` с данными участника
2. Парсит HTML-таблицу `table.tb_result` (дата, форма, предмет, балл, отметка, статус, апелляция, учебный год)
3. Сравнивает строки с файлом состояния (`/data/state.json` в Docker)
4. При появлении новых записей пишет в лог и шлёт уведомление в iMessage и/или Telegram
5. Ждёт `CHECK_INTERVAL_SECONDS` и повторяет цикл

При `SEED_STATE=true` и пустом состоянии текущие результаты сохраняются как baseline — уведомления придут только когда появятся **новые** строки (например, Русский язык или Физика).

## iMessage (macOS)

1. В `.env` укажите `IMESSAGE_ENABLED=true` и `IMESSAGE_TO` — один или несколько номеров через запятую (`+7...`)
2. Relay запускается автоматически через `start-all.sh` или вручную: `./scripts/run-imessage-relay.sh`
3. Убедитесь, что Mac залогинен в iMessage
4. В **Системные настройки → Конфиденциальность и безопасность → Автоматизация** разрешите Terminal/iTerm доступ к Messages

Relay слушает только `127.0.0.1`. Контейнер обращается через `host.docker.internal`.

Проверка relay:

```bash
./scripts/test-imessage.sh
```

Опционально задайте `IMESSAGE_RELAY_TOKEN` — тогда POST `/notify` требует заголовок `Authorization: Bearer <token>`.

## Telegram (опционально)

1. Создайте бота через [@BotFather](https://t.me/BotFather)
2. Узнайте `chat_id` (например, через [@userinfobot](https://t.me/userinfobot))
3. Добавьте в `.env`:

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

## Переменные окружения

| Переменная | Описание |
|---|---|
| `GIA_FAMILY` | Фамилия |
| `GIA_NAME` | Имя |
| `GIA_FATHER` | Отчество |
| `GIA_PASSPORT` | 6 цифр номера паспорта |
| `GIA_REGION` | Регион (по умолчанию Республика Башкортостан) |
| `CHECK_INTERVAL_SECONDS` | Интервал проверки (по умолчанию 300) |
| `QUIET_HOURS_ENABLED` | `true` — не проверять сайт в тихие часы |
| `QUIET_HOURS_START` | Начало паузы (по умолчанию 23:00) |
| `QUIET_HOURS_END` | Конец паузы (по умолчанию 8:00) |
| `TZ` | Часовой пояс (по умолчанию Asia/Yekaterinburg) |
| `SEED_STATE` | При первом запуске не уведомлять о существующих результатах |
| `IMESSAGE_ENABLED` | `true` — включить iMessage |
| `IMESSAGE_TO` | Получатели через запятую (телефон или email) |
| `IMESSAGE_RELAY_URL` | URL relay с точки зрения контейнера |
| `IMESSAGE_RELAY_PORT` | Порт relay на Mac (по умолчанию 8765) |
| `IMESSAGE_RELAY_TOKEN` | Опциональный токен для POST /notify |
| `TELEGRAM_BOT_TOKEN` | Токен Telegram-бота |
| `TELEGRAM_CHAT_ID` | ID чата для уведомлений |

Полный пример — в файле [`.env.example`](.env.example).

## Структура проекта

```
gia9/
├── bot/
│   ├── main.py              # Основной скрипт мониторинга
│   └── requirements.txt
├── host/
│   └── imessage_relay.py    # HTTP-relay для iMessage (только macOS)
├── scripts/
│   ├── start-all.sh         # Запуск relay + Docker
│   ├── stop-all.sh
│   ├── run-imessage-relay.sh
│   ├── docker-up.sh
│   ├── install-autostart.sh # launchd на macOS
│   └── test-imessage.sh
├── docker-compose.yml
├── Dockerfile
├── .env.example
└── README.md
```

## Локальный запуск без Docker

```bash
cd bot
pip install -r requirements.txt
export $(grep -v '^#' ../.env | xargs)
export STATE_FILE=../.data/state.json
python main.py
```

## Лицензия

MIT — см. [LICENSE](LICENSE).
