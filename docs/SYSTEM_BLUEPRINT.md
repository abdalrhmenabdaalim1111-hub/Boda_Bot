# Boda Bot System — Master System Architecture & Development Blueprint (v6.0)

> **Document Purpose**: This comprehensive specification serves as the primary system reference for AI agents and software engineers. It details the entire architecture, runtime models, directories, data layer, Mini App build pipeline, monetization integration, and exact extension protocols.

---

## 1. Executive Summary & Core Philosophy

**Boda Bot System** is a unified, scalable ecosystem consisting of **34 production-ready Telegram Bots** paired with **34 corresponding interactive Web Mini Apps**, a **central web-based Control Center**, and an **automated Monetag monetization pipeline**.

### Core Tenets:
1. **Decoupled Architecture**: 
   - **Bot Runtime**: Long-polling asynchronous/multiprocess supervisor designed to run locally on a home laptop/PC without requiring a public IP or open inbound ports.
   - **Mini Apps**: Premium, animated HTML5/JavaScript single-page applications statically hosted on **GitHub Pages** (`webroot/`).
   - **Control Center**: Built-in HTTP server (`127.0.0.1:8080`) providing an Arabic RTL Web UI replacing obsolete desktop Tkinter GUIs.
2. **Deterministic State & Single Source of Truth**:
   - `bots_registry.json`: Master catalog defining all 34 bots, their IDs, Arabic names, emojis, categories, planned Telegram handles, and resource tiers.
   - `Data/boda_bot.db`: SQLite database handling user engagement, referral networks, bot configurations, store items, and audit logs.
   - `.env`: Environment variables holding secret keys and tokens.

---

## 2. Directory Structure & File Roles

```text
D:\بودة\@Boda_Bot/
├── Start_Boda.bat                 # Primary 1-click Windows launcher (calls start_boda.py)
├── Stop_Boda.bat                  # 1-click Windows clean shutdown script
├── start_boda.py                  # Core bootstrap engine: checks port 8080, runs migrations, rebuilds UI, launches browser
├── stop_boda.py                   # Process termination engine for background workers
├── api_server.py                  # HTTP API server (Threaded BaseHTTPRequestHandler) on port 8080
├── bots_registry.json             # Master catalogue of 34 bots with metadata & tiers
├── requirements.txt               # Python package dependencies
├── .env                           # Secret tokens and runtime flags (NEVER COMMITTED)
│
├── control_center/                # Web Dashboard & Control Plane Core
│   ├── __init__.py
│   ├── api.py                     # /api/v1 REST route handlers (CRUD, bots, tokens, logs, store, gate)
│   ├── supervisor.py              # Subprocess BotSupervisor with exponential backoff & memory guards
│   ├── botconfig.py               # Runtime bot settings manager (Fernet encrypted tokens, features)
│   ├── crypto.py                  # Cryptographic layer (token encryption & masking)
│   ├── db.py                      # Thread-safe SQLite connection manager
│   ├── migrations.py              # Numbered, transactional, reversible database migrations
│   ├── auth.py                    # Localhost trust + X-API-Key authorization layer
│   ├── store.py                   # App Store backend CRUD, category filters, and catalog builder
│   └── gate.py                    # Subscription gate and channel membership verification
│
├── Bots_Folder/                   # Bot Runtime & Shared Logic
│   ├── bot_base.py                # Base helper: token resolution from env/db, UTF-8 setup, DB connection
│   ├── database.py                # Legacy and core database queries (users, referrals, stats)
│   ├── ad_manager.py              # Monetag ad configuration & injection coordinator
│   ├── ad_watcher.py              # Mtime daemon triggering auto-rebuilding on ad updates
│   ├── growth_engine.py           # User onboarding, referral attribution & viral loops
│   ├── unified_middleware.py      # Common bot event processing & telemetry
│   ├── bot_<id>.py                # 34 independent Telegram bot implementations
│   ├── bot_template.py            # Boilerplate template for scaffolding new bots
│   └── bot_integration.py         # Shared bot integration testing utilities
│
├── tools/                         # Generators & Build Tooling
│   ├── build_mini_apps.py         # Master build script: generates webroot/ from app_defs.py & templates
│   ├── app_defs.py                # 34 Mini App interface definitions & logic in pure HTML/CSS/JS
│   ├── dashboard_template.py      # Control Center Web Dashboard generator (HTML/CSS/JS)
│   ├── design_system.py           # Telegram Mini App design tokens, components & SDK wrappers
│   ├── ds_tokens.py               # Color themes, typography, spacing variables
│   ├── ds_components.py           # UI components: cards, buttons, spinners, modals
│   └── ds_sdk.py                  # Telegram WebApp JavaScript SDK bridges
│
├── webroot/                       # Static Distribution Folder (Published to GitHub Pages)
│   ├── dashboard/index.html       # Control Center Web Dashboard (http://127.0.0.1:8080/dashboard)
│   ├── store/index.html           # Public Mini App Store
│   ├── <bot_id>/index.html        # 34 static Mini Apps
│   ├── assets/                    # Shared CSS, fonts, and assets
│   ├── data/                      # Public metadata and generated sitemap.xml
│   └── sitemap.xml                # SEO sitemap for all 34 mini apps
│
├── webapps/                       # Legacy single-file HTML mirrors for all 34 apps
│   └── <bot_id>.html              # Single-file variants
│
├── Data/                          # Persistent Local Data
│   ├── boda_bot.db                # SQLite database
│   ├── monetag_config.json        # Active Monetag slot assignments
│   └── events.jsonl               # Streaming telemetry from Mini Apps
│
├── Logs/                          # Runtime logs for supervisor, server, and individual bots
│   ├── server.log                 # Control center server output
│   └── <bot_id>.log               # Per-bot rolling output
│
└── tests/                         # Pytest test suite (620+ tests covering 100% of core)
    ├── test_api_server.py
    ├── test_control_center_api.py
    ├── test_control_center_supervisor.py
    ├── test_control_center_store.py
    └── ...
```

---

## 3. The 34 Bot Catalogue & Classifications

The 34 bots are grouped into 4 distinct execution **Tiers**:

| Tier | Count | Characteristic | Bots List |
|---|---|---|---|
| **`light`** | 20 | Fast, event-driven, minimal CPU/RAM (~25-35MB RAM) | `fun_name`, `random_suggest`, `qrgen`, `formatfix`, `birth_age`, `store`, `iqtest`, `lovecalculator`, `mentalage`, `personalityanalyzer`, `cashier`, `safepass`, `fitcheck`, `logotext`, `braintwist`, `colorpick`, `cvbuilder`, `caltrack`, `luckybox`, `memoryvault` |
| **`external_api`** | 7 | Relies on third-party web APIs (weather, exchange rates, translation) | `currency`, `transbot`, `doctrans`, `shortlink`, `weathernow`, `textspeak`, `cryptorate` |
| **`heavy`** | 6 | Video processing, background removal, image boosting (FFmpeg, PIL, rembg) | `vidload`, `cleantok`, `stickerx`, `backdrop`, `silentcut`, `photoboost` |
| **`needs_scheduler`**| 1 | Cron/timer based background task execution | `alarmbot` |

---

## 4. How the Systems Work & Communicate

### 4.1 Bot Supervisor & Process Isolation
* Each bot runs as an isolated Python subprocess managed by `control_center/supervisor.py`.
* If a bot crashes, the supervisor catches the exit code and applies **exponential backoff** (`2s -> 4s -> 8s -> ... -> 300s`) to prevent log storms.
* **Heavy Memory Guard**: When launching a `heavy` tier bot, the supervisor checks system host RAM. If host RAM usage exceeds 95%, execution is refused to protect the operating system from freezing.
* **Token Injection**: `_build_env(bot_id)` dynamically resolves the bot's token (checking `bot_config` encrypted table first, falling back to `.env`) and injects `BOT_<ID>_TOKEN` directly into the subprocess environment.

### 4.2 Control Center Web Dashboard
* Served by `api_server.py` at `http://127.0.0.1:8080/dashboard`.
* Pure vanilla HTML5/ES6 architecture with **zero external CDN dependencies** (works completely offline).
* Features:
  - **Bot Cards Grid**: Live status pills (Running/Stopped), PID, uptime counter, restart counts, last error alerts.
  - **Live Action Controls**: Start, Stop, Restart individual bots, or execute Start All / Stop All.
  - **Live Log Streaming**: Real-time terminal output via **Server-Sent Events (SSE)** (`GET /api/v1/bots/<bot_id>/logs/stream`).
  - **Token Management Modal**: Live Telegram `getMe` verification before saving to database.
  - **Monetag Ad Management**: Slot injection preview, frequency control, direct links, and script tags.
  - **App Store Manager**: Reordering, category tagging, badges, and publishing.

### 4.3 Mini App Build Pipeline
* Run via `python tools/build_mini_apps.py`.
* Reads UI logic from `tools/app_defs.py`.
* Wraps applications inside `tools/design_system.py` providing unified CSS variables, dark/light theme switching, and Telegram WebApp SDK bindings.
* Preserves Monetag advertisement marker blocks:
  ```html
  <!-- AD:BEGIN slot=head id=monetag_1 -->
  <script src="https://alwingulla.com/..."></script>
  <!-- AD:END slot=head -->
  ```
* Generates static HTML output in `webroot/<bot_id>/index.html` ready for instant deployment to GitHub Pages.

---

## 5. Security & Authentication Architecture

1. **Localhost Trust**:
   - Requests originating from `127.0.0.1` or `::1` are automatically authorized as `local` administrators.
2. **Remote Access & API Protection**:
   - Remote requests require the `X-API-Key` HTTP header matching `API_SERVER_KEY` defined in `.env`.
   - If `API_SERVER_KEY` is not set, external access is rejected by default (Fail-Safe).
3. **Token Encryption at Rest**:
   - Telegram Bot tokens saved via the dashboard are encrypted using Fernet symmetric encryption (`cryptography.fernet`) with `BODA_SECRET_KEY`.
   - Plaintext tokens are NEVER printed in logs, NEVER returned in JSON API responses (always masked, e.g., `8689••••••••ENII`), and NEVER committed to Git.

---

## 6. How to Develop & Extend the System

### Adding a New Bot (Step-by-Step):
1. **Add Catalog Entry**: Append the bot metadata to `bots_registry.json`:
   ```json
   {
     "id": "mybot",
     "name": "بوت تجريبي",
     "emoji": "⚡",
     "category": "أدوات",
     "tag": "أدوات 🛠️",
     "username": "@MyNewBodaBot",
     "tier": "light"
   }
   ```
2. **Create Bot Script**: Copy `Bots_Folder/bot_template.py` to `Bots_Folder/bot_mybot.py`:
   ```python
   import telebot
   from bot_base import get_token, setup_bot_base
   TOKEN = get_token("BOT_MYBOT_TOKEN")
   bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
   # Implement handlers...
   if __name__ == "__main__":
       bot.infinity_polling()
   ```
3. **Define Mini App**: Add the HTML/JS definition inside `tools/app_defs.py` under `"mybot"`.
4. **Compile Static Apps**: Run `python tools/build_mini_apps.py`.
5. **Set Token & Launch**: In Control Center, click "🔑 التوكن" on the new bot card, test with `getMe`, and click "▶ تشغيل".

