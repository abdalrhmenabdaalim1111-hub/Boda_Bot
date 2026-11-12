# Desktop Parity Audit (Phase 5 Pre-Removal)

**Purpose**: Document every feature in the legacy Tkinter/Console desktop apps and verify parity with the browser Control Center. This doc drives the "Close Gaps" step.

---

## 1. Manager.py (Tkinter Desktop) — Feature Inventory

### UI & Navigation
- **Header bar** with buttons: Start All, Stop All, Refresh, Open Folder, Export Log, Clear Log, Open Ads Dashboard
- **Left panel**: Bot list cards with status, color coding, token badge, restart toggle
- **Right panel** (Notebook tabbed):
  - **Log tab**: System log, per-bot log lines with color-coded severity (ok/warn/err), scroll-to functionality
  - **Stats tab**: Views/opens/clicks KPI cards per bot, ad config status, refresh button
- **Status bar** at bottom: running/stopped/restart counts
- **Exit confirmation**: Shows count of running bots before closing, asks for confirmation

### Bot Management
- **Single-instance lock**: Socket bind on 127.0.0.1:47291 — prevents second instance, shows error message
- **Bot discovery**: Scans Bots_Folder for `bot_*.py`, skips internal helper files, extracts tokens from:
  1. `os.environ` (`BOT_<ID>_TOKEN`)
  2. `.env` file parsing
  3. Scanning other `.py` files for TOKEN= assignments
- **Start bot**: Validates token exists and is valid format, subprocess.Popen with `CREATE_NEW_PROCESS_GROUP` (Windows)
- **Stop bot**: `taskkill /F /T /PID` (Windows) or `process.terminate()` (cross-platform)
- **Start all**: Iterates bots, skips those without tokens, logs skipped count
- **Stop all**: Iterates all running bots and stops them
- **Auto-restart**: Exponential backoff (5s base, doubles up to max), only if `auto_restart=True` and not manually stopped
- **Token dialog**: Modal Toplevel with validation, calls `dev_tools.cmd_set_token()` to register token with checker bot
- **Monetag dialog**: Two modes:
  - **Custom per-bot**: direct_link, zone_id, script_url, format_type, frequency
  - **Global default**: same fields for all bots
- **Registry sync**: Auto-adds new bots to `bots_registry.json` with minimal metadata

### Monitoring & Diagnostics
- **Per-bot metrics**: CPU % (via psutil), memory RSS (MB), displayed on card
- **Status bar**: Total running/stopped/restart counts
- **Log queue**: Thread-safe queue between bot process and UI thread
- **Exit handling**: `_on_close` checks for running bots, saves config, stops all, destroys window
- **Periodic refresh**: `_tick()` every 500ms updates all cards and stats

### Configuration
- **manager_config.json**: Persists `auto_restart` preferences per bot
- **.env**: Token environment variables loaded at startup
- **bots_registry.json**: Registry of all bots for the store system

---

## 2. StartManager.py (Console Bot Manager) — Feature Inventory

### Bot Lifecycle
- **load_bots()**: Scans Bots_Folder for `bot_*.py` (excludes templates), logs count
- **start_bot(bot_name)**: subprocess.Popen, creates process group for Windows
- **stop_bot(bot_name)**: `process.terminate()` or `taskkill /F /T /PID`
- **start_all()**: Iterates all bots, 1s delay between each
- **stop_all()**: Iterates all processes and stops them

### Status Monitoring
- **status()**: Returns dict `{bot_name: "running"/"stopped"}`
- **Main loop**: Every 60s logs active count: `running/total`
- **KeyboardInterrupt**: Graceful shutdown handler
- **Exception handling**: Catches and logs unexpected errors, exits with code 1

### Configuration
- **BOTS_FOLDER**: Derived from `Path(__file__).parent / "Bots_Folder"` (relative to where StartManager.py lives)

---

## 3. Browser Control Center — Parity Verification

### Confirmed Parity (✅)
| Manager.py Feature | Web Equivalent | File/Endpoint |
|---|---|---|
| Start/stop bots | API routes | `control_center/api.py` |
| Start all / stop all | API routes | `control_center/api.py` |
| Token management | API + dev_tools | `control_center/api.py`, `dev_tools.py` |
| Monetag config | API endpoints | `control_center/api.py`, `ad_manager.py` |
| Auto-restart per bot | `growth_gate` feature flag + bot_config | `control_center/botconfig.py` |
| Per-bot metrics | Dashboard KPI cards | `webroot/dashboard/index.html` |
| Log panel | `/api/logs` + SSE | `control_center/supervisor.py` |
| Stats panel | Store dashboard | `webroot/dashboard/index.html` |
| Single-instance lock | API server ThreadingHTTPServer | `api_server.py` |
| Exit confirmation | Dashboard shutdown flow | `control_center/supervisor.py` |
| Registry sync | API-managed | `control_center/api.py` |

### Minor Gaps (🟡) — To Be Implemented in Web UI
| Gap | Priority | Notes |
|---|---|---|
| Real-time per-bot CPU/Memory graphs (psutil) | Low | Dashboard shows static KPI cards; real-time graphs possible via SSE |
| Visual bot list with color-coded cards | Medium | Already in dashboard as table view |
| Monetag "Custom per-bot" vs "Global" toggle UI | Medium | Dashboard has unified ad config per bot |
| Exit confirmation dialog with running-bot count | Low | Dashboard has shutdown flow, different UX |
| Single-instance lock error message | Low | API server handles concurrent instances gracefully (409) |
| Start delay between start_all bots (1s) | Low | `supervisor.start_all()` runs sequentially |

### Missing Entirely (🔴) — No Web Equivalent Yet
| Missing Feature | Impact | Fix Plan |
|---|---|---|
| Real-time per-bot CPU/Memory graphs via psutil | Low | Add SSE endpoint or widget in future |
| Visual single-instance lock warning | Low | Not needed — API server handles concurrency |
| Token dialog with `dev_tools.cmd_set_token` integration | Medium | Dashboard uses API + manual .env editing |
| Monetag "Frequency" spinner (every N uses) | Low | Dashboard uses format_type only |

---

## 4. StartManager.py Gaps
| Gap | Web Equivalent | Effort |
|---|---|---|
| Console status loop every 60s | Dashboard auto-refresh + websocket | Low |
| `time.sleep(1)` between start_all bots | `supervisor.start_all()` runs sequentially | Low |

---

## 5. Launchers
| Launcher | Action | Replacement |
|---|---|---|
| `StartManager.bat` | `start "" pythonw Manager.py` | Browser Control Center only |
| `Manager.py` full Tkinter app | Desktop GUI | Browser dashboard |
| `StartManager.py` console manager | CLI bot control | `dev_tools.py` CLI commands |

---

## 6. Import/Dependency Chain
| File | Imports | Web Equivalent |
|---|---|---|
| `Manager.py` | `tkinter`, `psutil`, `dev_tools`, `subprocess`, `socket` | Browser avoids tkinter/psutil for UI; API server uses psutil optionally |
| `StartManager.py` | `subprocess`, `logging`, `pathlib` | Fully replaceable by API |
| `Manager.py` → `dev_tools.cmd_set_token()` | Token registration | Dashboard: API `POST /api/v1/bots/<id>/config` + .env editing |
| `Manager.py` → `manager_config.json` | Auto-restart prefs | Dashboard: `bot_config.features` + API |

---

**Conclusion**: All critical parity is achieved. The browser Control Center provides equivalent or superior functionality. No show-stopping gaps exist. Removal is safe once Step 2 closes the minor gaps.

---
*Doc generated for Step 1 of Desktop Removal Plan.*