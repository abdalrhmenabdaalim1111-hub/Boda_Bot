# Ad Code Manager — Phase 0 Discovery Report

> Read-only discovery for the **Monetag Ad Code Manager** feature.
> Companion to `docs/PROJECT_PROFILE.md` (system-wide adaptation profile).
> Status: **awaiting owner approval** — no file has been modified for this feature.

---

## 1. Scope & Method

Owner goal: paste a Monetag ad snippet in the panel, choose target bots and a slot,
press *Save & Apply* → the correct mini-app file(s) are updated safely; *Publish*
commits/pushes and GitHub Pages serves the update. No manual file editing.

Method: read-only inspection of the generator, templates, real generated pages,
ad configuration stores, tracking endpoint, panel surfaces, CI/Pages workflow and
the test suite. Two baselines recorded (§9).

---

## 2. Detected Stack (summary)

Full detail in `docs/PROJECT_PROFILE.md` §1. Relevant here:

| Layer            | Technology | Evidence |
|------------------|-----------|----------|
| Pages generator  | Python string templates | `tools/build_mini_apps.py`, `tools/app_template.py`, `tools/app_defs.py` |
| Page hosting     | GitHub Pages via Actions | `.github/workflows/pages.yml` |
| Ad config stores | two JSON files (no DB yet) | `Data/ads_config.json`, `Data/monetag_config.json` |
| Ad runtime       | client-side AdSDK reading `window.__BODA_ADS__` | `tools/app_template.py:195-239` |
| Bot-message ads  | `AdManager` monkey-patches `bot.send_message` | `Bots_Folder/ad_manager.py:465` |
| Tracking         | stdlib HTTP API → JSONL + SQLite | `api_server.py:51,497`, `Bots_Folder/ad_watcher.py` |
| Control Center   | `control_center/` API v1 + audit + reversible migrations (branch `feature/control-center`) | committed, not merged to `main` yet |

---

## 3. How the App Files Are Produced (critical)

One generator produces **everything** in `webroot/`:

```
python tools/build_mini_apps.py
```

`main()` (`tools/build_mini_apps.py:355-437`):

1. **`shutil.rmtree(out_dir)`** — deletes the whole `webroot/` first
   (`build_mini_apps.py:366-367`). **Any hand-applied edit is destroyed on every
   rebuild.** This is the #1 blocker for marker-based injection (fix = project
   decision D7: generator must become marker-aware / emit protected blocks).
2. Regenerates: `data/catalog.json`, `data/stats.json` (from SQLite + events),
   `<bot_id>/index.html` for all 34 bots, `webapps/<bot_id>.html` single-file
   copies, `store/index.html`, `index.html` (redirect), `.nojekyll`,
   `sitemap.xml`, `robots.txt`. On the `feature/control-center` branch it also
   emits `dashboard/index.html`.
3. Ad content is **baked in at build time** from the JSON stores (§4).

### Rebuild triggers (ads must survive all of them)

| Trigger | Where |
|---------|-------|
| `AdConfigWatcher` polls ad-config mtimes every 2 s and rebuilds | `Bots_Folder/ad_watcher.py` |
| `sync_mini_apps()` shells out to the builder | `Bots_Folder/ad_watcher.py` — called by `api_server.py` `/api/ads/set` (line 533), `dev_tools.py set-ad` |
| Tkinter dialog saves → spawns `python tools/build_mini_apps.py` | `Manager.py:763-768` |
| CI / manual | any |

**Implication:** the injection engine must cooperate with the generator, not
fight it (see risk R1/R2).

---

## 4. Existing Ad Data & Code (reuse, do not duplicate)

### 4.1 `Data/ads_config.json` (global, Telegram-side)
```json
{ "enabled": true,
  "force_subscribe": { "enabled": false, "channel_username": "@MySponsorChannel", ... },
  "footer_ad":  { "enabled": true, "frequency": 2, "text": "...برعاية..." },
  "button_ad":  { "enabled": true, "button_text": "🌟 قناة الراعي الرسمي", "url": "..." } }
```

### 4.2 `Data/monetag_config.json` (per-bot Monetag)
```
global_default { enabled, direct_link, zone_id, script_url, format, frequency }
bots.<bot_id>  { bot_name, has_custom_ads, direct_link, zone_id, script_url,
                 format, frequency, active, last_updated }
```
34 bot entries. Precedence today: **bot-level custom (`has_custom_ads`) →
global_default** (`build_mini_apps.py:52-114`, `ad_manager.get_monetag_config`).
`currency` currently holds sandbox values (`monetag.example.com`, zone
`99887766`) — must not be touched by the feature.

> Note: today's model stores only **three scalar fields** (direct_link /
> zone_id / script_url) and *constructs* a `<script src>` from them. There is
> **no storage for a raw pasted snippet** anywhere. Raw-snippet support is new
> data, not a refactor.

### 4.3 `AdManager` API (`Bots_Folder/ad_manager.py`)
| Member | Line | Notes |
|--------|------|-------|
| `set_monetag_config(bot_id, direct_link, zone_id, script_url, format_type, frequency, active)` | 125 | writes JSON |
| `set_global_monetag_default(...)` | 151 | global fallback |
| `has_monetag_ad` / `has_custom_monetag_ad` | 168/173 | |
| `record_ad_view` / `record_ad_click` | 179/189 | → `db.record_ad_impression/record_ad_click` → `monetag_ad_stats` (keyed bot+format, **no ad_id**) |
| `build_ad_click_url` / `resolve_ad_click` | 276/286 | store bot `/start adclick_<bot_id>` |
| `check_force_subscribe` | 329 | gate |
| `get_footer_ad` / `get_ad_button` | 386/411 | Telegram-side |
| `attach_unified_ads(bot)` | 465 | monkey-patches `send_message` with footer ads |
| `get_monetag_button` | 517 | |

### 4.4 Mini-app runtime AdSDK (`tools/app_template.py`)
- `window.__BODA_ADS__` JSON is baked before `</body>` (lines 349-354):
  `{banner, sponsor, every, monetag_script, monetag_zone, has_monetag}`.
- `Ad.mountBanner()` appends a `.ad-banner` div to `.container` every N uses;
  `Ad.maybeSponsor()` shows a `#sponsor-overlay` card with the sponsor URL
  (lines 195-239). Clicks/views call `track('ad_view'|'ad_click', {placement})`.
- `build_html()` places the Monetag loader **in `<head>` before `<style>`**
  (line 300-302, 330): `<script src="{script_url}"></script>`.

---

## 5. Real App Files Inspected

- `webroot/currency/index.html` — 336 lines, 17 KB. Clean, uniform structure:
  `<!DOCTYPE html>` → `<head>` (telegram-web-app.js line 18, **Monetag loader
  line 19** `https://thubanoa.com/1?z=99887766`, `<style>`), `<body>` with
  `.container`, `__BODA_*__` script block, app JS, `</body></html>`.
- `webroot/store/index.html` — sponsor implemented **client-side** by the AdSDK
  (`#sponsor-overlay` CSS at lines 115-132); no raw script in page.
- **Zero `AD:BEGIN`/`AD:END` markers exist anywhere** (grep across repo: 0
  matches). All pages come from the same generator, so `</head>` / `</body>`
  anchors are consistent by construction — naive injection is safe *today*,
  but see R1 (rebuilds wipe it).

---

## 6. Tracking Endpoints (reuse)

- `POST /api/track` (`api_server.py:497`) — **open** (no auth), 4 KB cap,
  body dict → `record_event()` (line 51) → `Data/events.jsonl`.
  Accepted fields: anything, but the SDK sends `{bot, event, user_id, ...extra}`
  (e.g. `placement`). Counters are consumed by `collect_stats()` into
  `webroot/data/stats.json`.
- `AdManager.record_ad_view/record_ad_click` → `monetag_ad_stats`
  (currently 4 rows) — **keyed by bot+format only, no ad_id**.
- A/B tables exist (`ab_ad_stats` + `record_ab_*`), currently unused.
- `control_center.config` already defines `BODA_AD_ALLOWED_DOMAINS`,
  `BODA_AD_MAX_BYTES`, `BODA_AD_CPM` — ready-made for the validator and the
  "estimated revenue" field (owner confirmed: manual rate entry).

**Conclusion:** per-ad tracking needs `ad_id` in the track payload + a DB table;
the endpoint itself needs **no breaking change** (extra keys already tolerated).

---

## 7. GitHub Publishing (current flow)

- Remote: `github.com/abdalrhmenabdaalim1111-hub/Boda_Bot.git` (branch `main`).
- `.github/workflows/pages.yml`: **on every push to `main`** → uploads
  `webroot/` artifact → `actions/deploy-pages`. Effective site:
  `https://abdalrhmenabdaalim1111-hub.github.io/Boda_Bot/`
  (`PAGES_BASE`, `build_mini_apps.py:47-48`; overridable via `MINIAPPS_BASE_URL`).
- `webroot/` (39 files) and `webapps/` (34 files) are **committed** to the repo;
  `stats.json` is gitignored and pages have a built-in fallback.
- So *"Publish"* = commit the changed `webroot` files + push `main`. No
  force-push, no repo-settings change needed. While working on a feature
  branch, an instant publish can push a commit to `main` via a temporary
  `git worktree` (no branch switching) — proposed in Phase A3, default OFF
  (manual fallback documented).

---

## 8. Existing Panel Surfaces (where the UI lives today)

| Surface | Location | Capabilities |
|---------|----------|--------------|
| Tkinter Manager | `Manager.py:669-802` `_open_monetag_dialog` | per-bot direct_link/zone/script/format/frequency + "تعميم على الكل"; saves → spawns full rebuild |
| CLI | `dev_tools.py` `ads`, `set-ad <id> <link|zone>` | status table + quick set + rebuild |
| HTTP API | `api_server.py` `POST /api/ads/set` (X-API-Key) | same 3 fields + `sync_mini_apps()` |
| Control Center API | `feature/control-center`: `/api/v1/*`, audit, migrations, `/docs` | no ad routes yet |
| Analytics page | `webroot/dashboard/index.html` (CC branch) | read-only |

**Missing for this feature:** ad library (multi-ad per bot, raw snippet, notes,
enable/disable), slot/assignment model, marker injector with diff/rollback,
publisher, per-ad stats, admin UI.

---

## 9. Test Framework & Baselines

Framework: **pytest** (`pytest.ini`), lint via `python dev_tools.py lint`
(py_compile), secret gate `python tools/secret_scan.py`.

| Baseline | Branch | Result |
|----------|--------|--------|
| System baseline (earlier today) | `feature/control-center` @ `e02e3d2` | **502 passed / 0 failed** (~2.6 min) |
| Feature-branch final | `feature/control-center` @ `a65b6ef` | **502 passed** (commit message records it) |
| Measured during this Phase 0 | `main` @ `5c8faed` (working tree) | **214 collected — 213 passed, 1 failed** |
| The 1 failure | `test_webhook_server.py::test_missing_secret_header_is_rejected` | flaky socket abort (`WinError 10053`) while the parallel session was running live e2e bots — passed in all prior runs; not a regression |

> ⚠ Baseline measured on `main` is unstable: the **parallel session is actively
> working on `main` right now** (regenerated `webroot/` minutes ago, runs e2e
> bots, committed `5c8faed`). The feature must branch off
> `feature/control-center` (502-green), not `main`.

---

## 10. Exists vs Missing

| Capability | Status |
|------------|--------|
| Per-bot Monetag scalar config (link/zone/script) | ✅ exists (JSON + AdManager) |
| Bot-message ads (footer/button/force-subscribe/SmartLink) | ✅ exists (`attach_unified_ads`) |
| Mini-app sponsor + banner (client-side) | ✅ exists (AdSDK) |
| Rebuild pipeline that regenerates all pages | ✅ exists — **but wipes webroot (R1)** |
| Open tracking endpoint accepting extra fields | ✅ exists (`/api/track`) |
| GitHub Pages auto-deploy on push to main | ✅ exists (`pages.yml`) |
| Raw snippet storage (full Monetag code) | ❌ missing |
| Ad library: multiple ads, formats, notes, enable/disable | ❌ missing |
| Slots + assignment resolution (bot > category > global) | ❌ missing (only bot→global) |
| Marker-based idempotent injection + diff + backup + rollback | ❌ missing |
| Generator preserves/emit markers | ❌ missing (R1) |
| Per-ad stats (`ad_id`) | ❌ missing |
| Publish action (stage-only commit + push, manual fallback) | ❌ missing |
| Validation (size, balanced tags, dangerous patterns, domain allow-list) | ❌ missing |
| Admin UI for ads with diff preview | ❌ missing |

---

## 11. Design Options Analysis

| Option | Fit | Verdict |
|--------|-----|---------|
| **A — direct injection only** | Breaks on every rebuild (`rmtree`), watcher races | ✗ fragile alone |
| **B — central runtime config only** | One JSON fetch per page is elegant, but raw Monetag snippets (scripts) cannot be reliably evaluated from JSON at runtime without `innerHTML` script pitfalls; requirement is that the app file *contains* the code | ✗ alone |
| **C — hybrid (recommended)** | SQLite = source of truth (Control Center), JSON mirrors stay in sync (decision D6), generator **emits** marker blocks at build time, injection engine writes markers into files for single-bot apply. Both paths converge byte-identically | ✅ |

**Recommendation: C**, reasons:
1. The pipeline already regenerates every page from one template — fighting it
   is impossible; the generator must know about ads (D7) and emit markers from
   the synced config, so rebuilds keep ads automatically.
2. The Control Center already has the audit log, reversible migrations and the
   `/api/v1` surface this feature needs — a SQLite `ads`/`ad_assignments` model
   is the natural fit; the legacy JSON mirrors keep `AdManager`, the Tkinter
   dialog, the watcher and `/api/ads/set` working unchanged (backward compat).
3. Marker blocks make single-bot *Save & Apply* idempotent, diffable,
   rollback-able — and byte-identical to what the generator would emit.

**Slot mapping (proposed):**

| Slot | Anchor | Notes |
|------|--------|-------|
| `head` | after `telegram-web-app.js`, before `<style>` | matches existing `monetag_tag` position |
| `body_end` | before the `__BODA_*__` script block / `</body>` | |
| `banner_top` | after `<header class="app-header">` block | styled `.ad-slot` |
| `banner_bottom` | end of `.container` | where AdSDK mounts today |
| `interstitial` | `body_end` + `Boda.Ad` trigger hook | raw In-App Interstitial snippet |
| `bot_message` | **not HTML** — routes to `AdManager` (SmartLink/direct_link) | tracked via existing `adclick` flow |

---

## 12. Risks

| # | Risk | Mitigation |
|---|------|------------|
| R1 | `shutil.rmtree(webroot)` destroys markers on every rebuild (`build_mini_apps.py:366`) | Phase A1: generator becomes marker-aware and emits ads from the synced config (D7) + test "generator preserves ads" |
| R2 | `AdConfigWatcher` rebuilds ≤2 s after config mtime change → race with the injector | injector pauses the watcher (lock file) during apply, or routes writes through the builder; tests |
| R3 | Monetag snippet integrity | never modify the pasted code; wrap tracking **around** it (separate script/pixel), snippet stays byte-exact inside markers |
| R4 | Parallel session is live on `main` **now** (also added commits to our branch) | coordinate/freeze before Phase 1; branch the feature off `feature/control-center` |
| R5 | Pages deploys **only** from `main` | publisher design: commit on current branch; optional instant publish via temp worktree on `main`; manual fallback documented |
| R6 | Encoding / CRLF | UTF-8 LF preserved; atomic write (temp + replace); byte-identical idempotency test |
| R7 | Raw snippets are new data | migration 002 defines the schema; sync strategy defines how raw snippets map to legacy JSON fields |
| R8 | Secrets | snippet validator rejects bot-token-like strings; tokens/keys never logged or committed; admin routes behind existing auth |
| R9 | Precedence drift | resolver mirrors today's bot→global precedence and extends it with category level; UI shows effective ad per bot/slot |

---

## 13. Proposed Phased Plan (execute only after approval)

| Phase | Scope | Est. |
|-------|-------|------|
| **A1** | Migration 002 (`ads`, `ad_assignments`, `ad_events`) · `control_center/ads/` model+resolver+validator+injector · timestamped backups · rollback · dry-run diff · atomic writes · **generator marker-aware (D7)** · tests (insert/update/remove/idempotency/rollback/malformed/missing markers/resolution/generator-preserves-ads) | 8–10 h |
| **A2** | Panel UI: ad library CRUD, assignment, **Preview (unified diff)**, Save & Apply, Rollback, Disable/Remove + per-file result summary · Arabic RTL labels | 8–10 h |
| **A3** | Generator integration finalization + **Publish** (stage-only commit, clear message, push; no force; optional auto-publish default **OFF**; manual fallback list of commands) | 4–6 h |
| **A4** | Tracking: `ad_id` through `/api/track` (backward compatible) + wrapped trackers · per-ad/per-bot stats · audit wiring · "estimate per 1000 impressions" field (manual rate) | 4–6 h |
| **A5** | Hardening: validation rules, `docs/ADS_GUIDE.md` (Arabic), final regression | 3–4 h |

UI toolkit question for the owner (Phase A2): the web admin page served by
`api_server.py` (recommended — works everywhere, fits the Control Center API,
Arabic RTL) with the existing Tkinter Monetag dialog kept as-is, **or** upgrade
the Tkinter dialog instead.

---

## 14. Open Decisions (owner)

1. Approve the plan and start Phase A1?
2. Branch `feature/ad-code-manager` created from **`feature/control-center`**
   (recommended — the feature depends on the Control Center API/audit/migrations,
   and that branch is 502-green)?
3. Panel UI toolkit: web admin page (recommended) or Tkinter dialog upgrade?
4. How to handle the active parallel session on `main`?
