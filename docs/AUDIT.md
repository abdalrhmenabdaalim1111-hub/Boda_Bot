# Phase 0 Audit — Boda Bot System (Ad Studio + Mini Apps Upgrade)

**Date:** 2026-11-12 · **Branch:** `feature/ad-studio-and-apps` (created from `feature/bot-management-and-gate` @ `3da610a`) · **Tag:** `pre-ad-studio`
**Scope:** read-only audit required by the Phase-0 gate. No code was modified. This document and `docs/PLAN_V3.md` are the only files written.

> Method: every number below was measured with a real command (outputs shown inline or summarized). Sub-claims are cited as `file:line`. Zone IDs and tokens are masked.

---

## 1. Tests & coverage — real numbers

Command (run 2026-11-12, Windows, Python 3.13.6):

```
$env:PYTHONIOENCODING='utf-8'; python -m pytest tests/ -q --cov=Bots_Folder --cov=control_center --cov-report=term --cov-report=json:coverage.json
```

Result: **705 passed, 0 failed in 433.50 s** (1,443 warnings — all `ResourceWarning: unclosed sqlite3.Connection` in tests).

| Area | Coverage | Note |
|---|---|---|
| `Bots_Folder/database.py` | 89% | core gate ✅ (min 80%) |
| `Bots_Folder/ad_manager.py` | 96% | core gate ✅ |
| `Bots_Folder/growth_engine.py` | 99% | core gate ✅ |
| `Bots_Folder/unified_middleware.py` | 87% | core gate ✅ |
| `Bots_Folder/bot_base.py` | 92% | core gate ✅ |
| `Bots_Folder/gate_core.py` / `gate_middleware.py` | 79% / 88% | not gated |
| `control_center/api.py` | **37%** | ⚠ Ad Studio routes land here |
| `control_center/ads/injector.py` | 76% | injection engine |
| `control_center/ads/sync.py` | **18%** | ⚠ riskiest |
| `control_center/ads/model.py` | 68% | ⚠ |
| `control_center/store.py` | 69% | publish flow |
| `control_center/botconfig.py` / `db.py` | 59% / 60% | ⚠ |
| `Bots_Folder/bot_*.py` (34 files) | 0% | entry-point scripts, excluded from the CI gate by design (`tools/check_coverage.py:6-7`) |
| **TOTAL** | **49%** (9,414 stmts, 4,833 missed) | |

Coverage gate check (`python tools/check_coverage.py`): all 10 gated core modules pass their 80% minimum.

Corrections to prior claims in the architecture doc:
- "620+ tests" → real count today: **705**.
- "100% core coverage" → real: core modules are **80–99%**, not 100%.
- CI runs Python 3.11/3.12 on ubuntu; local dev runs 3.13.6/win32 — a drift risk for `reconfigure`/encoding-sensitive code.

**Environment note:** piping pytest through PowerShell re-encodes output to cp1252 and can surface *phantom* failures/errors (`UnicodeEncodeError: 'charmap' codec`). With `PYTHONIOENCODING=utf-8` the suite is fully green (705/0). Always run tests with that env var on this machine.

---

## 2. (a) What exactly gets published to GitHub Pages

Evidence: `.github/workflows/pages.yml:32-36` — `actions/upload-pages-artifact@v3` with **`path: webroot`**, triggered on push to `main`. There is **no exclusion filter** in the workflow.

Verified contents of `webroot/` (47 files, ~1.6 MB):
- `webroot/<bot_id>/index.html` ×34 (the mini apps), `store/index.html` (59,771 B), `data/{stats,catalog}.json`, `assets/fonts/*.woff2` ×2, `sitemap.xml`, `robots.txt`, `.nojekyll`, root redirect.
- ⚠ **`webroot/dashboard/index.html` (99,234 B) is tracked in git and IS published.** Verified with `git ls-files webroot/dashboard` → `webroot/dashboard/index.html`.
  - It is the full admin Control Center UI: bot-token editor modal (placeholder `123456789:ABCdefGHI…`, `POST /api/v1/bots/<id>/config`, `/api/v1/system/verify-token`), live log stream (SSE with an inert `?token=` param, `index.html:1006`), store import/export/`upload-image` with an API key stored in `localStorage['boda_api_key']` (`index.html:681`).
  - Mitigation today: the page is built with `API_BASE = ""` so every admin call targets the same origin (github.io) and fails — no data leaks. But the admin console itself is publicly served, and it is the exact file the Ad Studio will extend.
  - `webroot/data/*` are **untracked** (gitignored, `.gitignore:41,78`) so Pages never publishes them; pages have a built-in fallback (`pages.yml:35` comment).
- Stray: `webroot/currency/.ads_backup_index.html/…bak` (untracked injector backup inside the published tree) and 3 identical placeholder `assets/store/*.webp`.

**Verdict:** the dashboard and any admin-only artifacts must be excluded from the Pages artifact (Phase 1 fix, with a test).

---

## 3. (b) "Localhost trust" — verdict: REAL exploitable CSRF + DNS-rebinding gap

Evidence chain:

| Fact | Evidence |
|---|---|
| Server binds `127.0.0.1` by default | `api_server.py:562,597`; `start_boda.py:158,173` |
| Docker profile binds `0.0.0.0` | `docker-compose.yml:54` |
| Any request from loopback = full **admin**, zero credentials | `control_center/auth.py:30-32` (`is_local`), `:68-70` (`actor="local"` bypasses **all** role checks, incl. `roles=("admin",)`) |
| Legacy endpoints: same loopback bypass, else `X-API-Key` (plain `==`) | `api_server.py:296-304` |
| Every response carries `Access-Control-Allow-Origin: *` | `api_server.py:283,292,317` |
| Preflight explicitly allows `Content-Type, X-API-Key, Authorization` + `DELETE` | `api_server.py:368-375` |
| No Origin / Referer / Sec-Fetch-Site / Host / CSRF checks anywhere | repo-wide grep: 0 matches in `api_server.py`, `control_center/*` |
| Session system is a stub (`session_user()` always `None`) | `control_center/auth.py:44-46` |
| No cookies exist at all | repo-wide `Set-Cookie`: 0 matches |

Attack path (no exploit needed to reason): a page on `https://evil.example.com` visited in the operator's browser can issue **cross-origin, credentialess "simple requests"** (no preflight) to `http://127.0.0.1:8080/api/v1/...`. The server sees `client_ip == 127.0.0.1` and authorizes as admin. `Content-Type: application/json` POSTs also pass because the server *answers the preflight* (`ACAO: *` + allowed headers). And since every response is `ACAO: *` with no credentials, the attacker page can also **read** responses (bot list, masked tokens, logs, audit log, store export).

Highest-impact state-changing endpoints reachable this way (route table `control_center/api.py:1681-1852`):
- `POST /api/v1/bots/<id>/config {"token": …}` → **bot hijack** (`allowed` includes `token`, `api.py:298-299`)
- `POST /api/v1/bots/actions/stop-all`, `POST /api/v1/bots/<id>/start|stop|restart`
- `DELETE /api/v1/bots/<id>` → hard delete (registry + bot file + webroot + DB rows, `api.py:619-665`)
- `POST /api/v1/store/publish` → runs `git push origin HEAD` (`control_center/store.py:469,498`) → attacker-controlled content on GitHub Pages
- Gate channels/profiles CRUD, migrations, verify-token.

DNS rebinding: **unmitigated** (no `Host` validation; source-IP-only auth would then be bypassed to same-origin).

Additional exposure findings:
- SSE bot-log stream route has **no auth guard** (`control_center/api.py:321-357`); raw bot stdout is served unredacted (`supervisor.py:502-531`, `GET /api/logs` at `api_server.py:248-272`).
- 500 errors return raw `traceback.format_exc()[-1200:]` to the client (`api_server.py:359-362`).
- Token hygiene is otherwise good: `crypto.mask_token` (`control_center/crypto.py:106-124`), DB strips `token_enc` (`botconfig.py:41`), API returns only `token_masked` (`api.py:208,234,308`), audit logs store field names only (`api.py:304-305,537`).
- Latent defect: `request.headers.get(...)` at `control_center/api.py:1138,1374` — `Request` exposes only `.header()` (`http.py:64-66`), so multipart paths (upload-image / import) raise `AttributeError` → 500 (swallowed by try/except).

**Phase-1 fixes (planned, not applied):** Origin/Sec-Fetch-Site rejection for non-GET, strict `Host` validation, a generated local admin token required for state-changing requests (auto-injected into the dashboard), CSRF defense via custom header requirement (server stops answering permissive preflights), auth guard on the SSE route, log redaction, and tests proving a cross-origin POST is rejected.

---

## 4. (c) `webapps/` vs `webroot/` duplication

- `tools/build_mini_apps.py` writes **both** from the same rendered string: `webroot/<id>/index.html` (`:455`) and `webapps/<id>.html` (`:457`). `webroot/` additionally gets `store/`, `dashboard/`, `data/`, `sitemap.xml`, etc.
- MD5 comparison of all 34 pairs: **32/34 byte-identical**. The two diffs:
  - `store` — by design (flat landing variant vs full store with embedded catalog).
  - `currency` — divergence created by the ad injector mid-run (webapps copy carries an `<!-- AD:BEGIN slot=body_end id=gen_test_ad -->` block; the webroot copy does not; injector backed up the marked version to `webroot/currency/.ads_backup_…/…bak`).
- **They are two copies of one output, not two sources.** But the injector mutates the two copies **independently** (split-brain), and the build's marker carry-over reads **only the webroot copy** (`build_mini_apps.py:388`) and swallows all read/inject errors (`:405-406,453-454`) — injected blocks in `webapps/` are silently lost on the next rebuild (manual, ad-watcher 2 s poll `ad_watcher.py:61-103`, or `POST /api/ads/set` `api_server.py:543-544`).
- Counts: `bots_registry.json` = **34 bots**; `tools/app_defs.py` `APPS` = **33** entries (verified: `python -c "…print(len(app_defs.APPS))"` → 33). Consequences:
  - `cashier` has no `APPS` entry → renders as a generic **landing page** (`build_mini_apps.py:187-191`), smallest file (39,286 B).
  - `APPS['memory']` ("لعبة الذاكرة") is **orphaned** — no registry bot with id `memory`, never built.

**Decision needed (in PLAN_V3):** make `webroot/` the single published truth, treat `webapps/` as a deprecated mirror (or drop it), and fix carry-over to read both or stop writing `webapps/`.

---

## 5. (d) How ads are injected today

**Bot side** (`Bots_Folder/ad_manager.py`, 541 lines; wired for every bot from `bot_base.py:124-125`):
- Per-bot Monetag config with global fallback (`:116-135`), source `Data/monetag_config.json` + `Data/ads_config.json` (loaded `:22-24`).
- Surfaces: force-subscribe gate (`:341-396`), footer text ad with frequency gating (`:398-416`), sponsor inline button (`:423-446`); `attach_unified_ads` monkey-patches `bot.send_message` (`:477-512`).
- Click attribution: deep-link `https://t.me/BodaStoreeBot?start=adclick_<id>` (`:288-296`), resolved in `bot_store.py:155-172`; stats in SQLite `monetag_ad_stats` (`database.py:141-204,515-537`).
- Hot-sync: `Bots_Folder/ad_watcher.py` polls both JSON configs every 2 s and **re-runs the whole mini-apps build** (`:23-44`).

**Mini-app side** (all 34 pages):
- `window.__BODA_ADS__ = {…}` baked at build (`tools/app_template.py:102`) + Monetag `<script src>` in `<head>` (`app_template.py:41-42,76`).
- Zone loader is **hardcoded**: `script_url = f"https://thubanoa.com/1?z={zone_id}"` (`build_mini_apps.py:106`; also `dev_tools.py:946`). Repo-wide: `libtl` → 0 matches, `data-zone` → 0 matches, `alwingulla` → tests/docs only. **The exact Monetag snippet format you gave (`//libtl.com/sdk.js data-zone data-sdk`) cannot be parsed today.**
- Runtime SDK is shared, not copy-pasted: `tools/ds_sdk.py` — bottom banner (`:237-273`), interstitial auto-triggered after a result (`afterResult :276-289` watching `.result.show` mutations, 90 s throttle, `showInterstitial :291-343`), tracking via `Boda.track()` → `POST /api/track` (`:74-96`).
- `window.__BODA_ADS__` **survives rebuilds** (regenerated from Data JSON each build — persistence lives in `Data/`, correct design). The stray `AD:BEGIN` block in `webapps/currency.html` does **not** survive (see §4).

**Existing injector** (`control_center/ads/injector.py`, 170 stmts, 76% cov) is well-engineered and reusable: idempotent `<!-- AD:BEGIN slot=… id=… -->` markers (`:36-44`), same-slot replace / anchor insert (`:47-54,107-135`), validation, timestamped backups to `.ads_backup_<name>/`, atomic temp+replace, auto-restore on failure, rollback + dry-run (`:173-186,208-328`).

**Gaps vs your 7 quality rules (all currently MISSING):**
1. Rewarded always starts from a user tap — no rewarded format exists at all; the current interstitial is **auto-triggered** by DOM mutation.
2. Core function never blocked by ad failure — SDK is best-effort today but has no `reward(cb)`-only-on-resolve contract, no double-tap guard, no `{ok:false, reason}` protocol.
3. No ads on the subscription-gate screen or during processing — no exclusion concept exists (only frequency throttling).
4. In-App soft defaults + measurement — no In-App format support (`{type:'inApp', inAppSettings:{frequency, capping, interval, timeout, everyPage}}`), nothing to measure.
5. Pasted-snippet validation — no snippet parsing (zone/sdk extraction), no domain allow-list, no eval/`document.write`/forced-redirect detection (validator exists for other checks, `validator.py` 95% cov).
- No Monetag call formats supported (rewarded / popup / inApp). Only `direct_link` + banner + auto-interstitial.
- Tracking split-brain: mini apps → `Data/events.jsonl` (`ad_view`/`ad_click` via open `POST /api/track`, `api_server.py:497,506-515`) vs bots → SQLite `monetag_ad_stats`. Not reconciled; `ad_shown`/`ad_reward`/`ad_error`/`sdk_unavailable` don't exist anywhere yet.
- `Data/monetag_config.json` today: `global_default` + 34 bot entries; **only `bots.currency`** is `has_custom_ads:true` with a placeholder direct link (`monetag.example.com/test_click`) and one zone (masked).
- No per-app "ad points" concept in `app_defs.py` (no ad fields at all — verified by grep).

---

## 6. (e) Secrets / .gitignore / git history

- Tracked-files scan: **clean** — real output: `✅ فحص الأسرار نظيف — لا توكنات أو مفاتيح حقيقية في الشجرة`.
- History scan (report-only, last 50 commits, masked output): **`⚠ التاريخ يحتوي 11 سراً مسرّباً — التدوير من BotFather إلزامي`**. Matches `docs/PROJECT_PROFILE.md:140`. Deletion from history is not enough; tokens must be rotated via BotFather.
- `.gitignore` covers: `.env`, `.env.local`, `Data/`, `Backups/`, `Logs/`, `*.db/sqlite*`, `*_token.py`, `tokens.py`, `secrets.py`, `new_tokens.txt`, `coverage.xml/json`, `SECURITY_AUDIT_TOKENS.md`, `.ads_backup_*/`. ✅ adequate.
- `SECURITY_AUDIT_TOKENS.md` exists locally (gitignored). Not read during this audit (avoids handling real tokens).

---

## 7. (f) Per-app size / dependencies / load

| Metric | Value (measured) |
|---|---|
| Mini-app HTML size | 39,286 B (cashier) … 43,805 B (iqtest); all inline (HTML+CSS+JS single file) |
| `webroot/` total | ~1.6 MB (47 files incl. fonts 30/34 KB self-hosted woff2, dashboard 99 KB, store 60 KB) |
| External dependencies | **exactly one**: `https://telegram.org/js/telegram-web-app.js` loaded **synchronously in `<head>`** of every app (line 16) — the only CDN hit; everything else is inline/self-hosted |
| Network calls | fetch only for tracking (`/api/track`, best-effort, dead on Pages since `API_BASE=""`) and a few public APIs (§8); `XMLHttpRequest`: 0 |

Estimated first load ≈ **40–80 KB** per app (fonts cached/shared) → already inside the ~150 KB budget with ~70 KB headroom for the upgrade. Real device timing hasn't been measured — Phase 4 adds Playwright mobile-viewport smoke tests with a <2 s first-paint target.

---

## 8. (g) Static / public-API / bot-backend classification (34 apps)

| Class | Apps | External domains |
|---|---|---|
| (a) Pure static/local computation | birth_age, braintwist, caltrack, cashier, cleantok*, colorpick, cvbuilder, fitcheck, formatfix, fun_name, lovecalculator, luckybox, logotext, memoryvault, mentalage, personalityanalyzer, photoboost*, safepass, alarmbot | none (t.me links only) |
| (b) Public APIs | currency (`api.exchangerate-api.com`), cryptorate (`api.coingecko.com`), transbot, doctrans (`api.mymemory.translated.net`), shortlink (`is.gd`), weathernow (`wttr.in`), qrgen (`api.qrserver.com` via `<img>`) | as listed |
| (c) Bot handoff (page collects input → opens bot chat) | vidload, textspeak, backdrop, stickerx, silentcut, cleantok, photoboost (partial) | none |
| (d) Ad integration | all 34 carry `window.__BODA_ADS__`; only `currency` has an injected `AD:BEGIN` block (webapps copy only — divergent residue) | monetag zone loader (`thubanoa.com`, hardcoded) |

*Note: `cashier` is currently a generated landing page, not a real tool (no `APPS` entry) — decision needed whether to build it as app #33 or leave as landing.

---

## 9. Latent defects found during audit (to fix during Phases 1–4)

1. `control_center/api.py:1138,1374` — `request.headers.get()` → `AttributeError` (multipart upload-image/import paths) → 500.
2. Marker carry-over reads webroot only + silent `except: pass` (`build_mini_apps.py:388,405-406,453-454`) — ad blocks in `webapps/` lost on rebuild.
3. `APPS['memory']` orphaned; `cashier` landing-only; counts 33 vs 34 inconsistent.
4. SSE `?token=` param is inert (server never reads it) but would leak a key into browser history (`dashboard/index.html:1006`).
5. Test hygiene: 1,443 `ResourceWarning` (unclosed sqlite connections) — noise that hides real issues.
6. Windows console encoding (cp1252) breaks piped test output — always `PYTHONIOENCODING=utf-8`.
7. Dashboard published to Pages (§2) — the file Ad Studio will extend is publicly served today.

---

## 10. Bottom line

| Audit item | Status |
|---|---|
| Tests green | ✅ 705 passed / 0 failed (with utf-8 console) |
| Core coverage gate | ✅ passes (all ≥80%) |
| Dashboard published to Pages | 🔴 yes — must exclude (Phase 1) |
| Localhost CSRF / DNS-rebinding | 🔴 real and exploitable — fix first (Phase 1) |
| webapps/webroot split-brain | 🟡 real — consolidate to single source (Phase 2) |
| Monetag snippet parsing (zone/sdk) | 🔴 absent — required for your exact snippet (Phase 2) |
| Rewarded/Popup/In-App formats | 🔴 absent (Phase 2) |
| Reward hooks / gate-screen exclusion / user-initiated-only | 🔴 absent (Phases 2–4) |
| Injection engine + rollback | ✅ exists (`control_center/ads/injector.py`) — extend, don't rewrite |
| Size budget | ✅ ~40–80 KB/app, headroom for upgrade |
| Secrets in tracked tree | ✅ clean |
| Secrets in history | 🔴 11 leaked (rotation mandatory — owner action) |

Proceed to `docs/PLAN_V3.md` for the fix plan, estimates, and stop points. **No code changed in Phase 0.**
