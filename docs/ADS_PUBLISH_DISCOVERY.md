# Ad Code Manager & GitHub Pages Publisher — Phase 0 Discovery Report

**Document:** `docs/ADS_PUBLISH_DISCOVERY.md`  
**Date:** November 11, 2026  
**Status:** Complete — Awaiting Owner Approval before Phase 1  
**Target Branch:** `feature/ad-publish`  

---

## 1. Executive Summary & Verification of Claims

A previous project report made several claims regarding Monetag integration and ad management. Each claim was rigorously audited and tested in the codebase:

| Claim | Status | What Actually Happens (Code & Test Evidence) |
| :--- | :---: | :--- |
| **1. Per-bot Monetag scalar config with global fallback** | **VERIFIED** | `Data/monetag_config.json` stores 34 bot entries + `global_default`. `ad_manager.py:get_monetag_config(bot_id)` properly falls back to `global_default` when `has_custom_ads` is false. |
| **2. Ad watcher daemon re-injects ads within ~0.2s** | **PARTIALLY VERIFIED** | `Bots_Folder/ad_watcher.py` detects file modifications and calls `build_mini_apps.py`. However, it does NOT inject markers directly; it triggers a **full rebuild of all 35 apps via `shutil.rmtree(webroot)`**. |
| **3. 📢 Dialog in `Manager.py`** | **VERIFIED** | `Manager.py:669-802` (`_open_monetag_dialog`) provides a Tkinter popup for per-bot direct_link, zone_id, script_url, format, frequency, and a "generalize to all" button. On save, it spawns `build_mini_apps.py`. |
| **4. `dev_tools.py set-ad` CLI command** | **VERIFIED (with limitations)** | `dev_tools.py:937` implements `cmd_set_ad(bot_id, direct_link_or_zone, format_type)`. It takes a single positional argument for link/zone, saves to `monetag_config.json`, and triggers `build_mini_apps.py`. It does NOT accept raw HTML/JS snippets. |
| **5. Impression/click tracking** | **VERIFIED** | `POST /api/track` (`api_server.py:497`) appends client events to `Data/events.jsonl`. `AdManager.record_ad_view/record_ad_click` records into `monetag_ad_stats` table in `Data/boda_bot.db`. Clicks are routed via the store bot (`/start adclick_<bot_id>`). |
| **6. Raw custom snippet support** | **NOT PRESENT** | The current schema only stores scalar fields (`direct_link`, `zone_id`, `script_url`). Pasting an arbitrary Monetag JS tag or rewarded interstitial code is not supported. |
| **7. Safe marker blocks & rollback** | **NOT PRESENT (in baseline)** | The baseline generator overwrites files without marker blocks. No automated diff preview, backup, or rollback exists in the UI. |
| **8. One-click GitHub Pages publishing** | **NOT PRESENT** | No publish command or button exists in `Manager.py` or `dev_tools.py`. Publishing requires manual `git push origin main`. |

---

## 2. Technical Findings & Discovery Q&A

### 3.a. Which folder is published to GitHub Pages, and where is the configuration?
* **Published Folder:** `webroot/` (NOT `webapps/`).
* **Configuration / Workflow File:** [`.github/workflows/pages.yml`](file:///d:/بودة/@Boda_Bot/.github/workflows/pages.yml#L32-L37)
  ```yaml
  - name: Upload webroot artifact
    uses: actions/upload-pages-artifact@v3
    with:
      path: webroot
  - name: Deploy to GitHub Pages
    id: deployment
    uses: actions/deploy-pages@v4
  ```
* **Trigger Branch:** `main` (line 6: `branches: [main]` and `workflow_dispatch`).
* **Base URL:**
  * Defined in `.env`: `MINIAPPS_BASE_URL=https://abdalrhmenabdaalim1111-hub.github.io/Boda_Bot`
  * Set in `tools/build_mini_apps.py:47-48`: `PAGES_BASE = (MINIAPPS_BASE or "https://abdalrhmenabdaalim1111-hub.github.io/Boda_Bot").rstrip("/")`.

### 3.b. How does `ad_watcher` inject ads? Markers vs String Replacement? Idempotency & Malformed HTML
* **Mechanism:** `ad_watcher.py` does **NOT** perform in-place marker injection or regex replacement. Instead, `sync_mini_apps()` invokes `tools/build_mini_apps.py:main()`.
* **Generator Behavior:** `tools/build_mini_apps.py:366` executes `shutil.rmtree(out_dir)`. It deletes the entire `webroot/` directory and reconstructs every HTML file from Python f-strings in `tools/app_template.py:build_html()`.
* **Idempotency:** Re-running the generator with unchanged configuration produces identical output. However, any manual edit or external file injection in `webroot/` is wiped out immediately.
* **Malformed HTML / Missing Markers:** In the baseline, no marker blocks existed. If the template f-string or app defs fail, the builder crashes and leaves an incomplete `webroot`.

### 3.c. Config Format & Supported Monetag Formats
* **Config Storage:** [`Data/monetag_config.json`](file:///d:/بودة/@Boda_Bot/Data/monetag_config.json) stores only:
  `bot_name`, `has_custom_ads`, `direct_link`, `zone_id`, `script_url`, `format`, `frequency`, `active`, `last_updated`.
  It does **not** store raw snippets or arbitrary HTML/JS blocks.
* **Currently Supported Monetag Formats:**
  1. **Direct SmartLink:** Supported in Telegram bot messages via `AdManager.build_ad_click_url()` and in Mini Apps via `Ad.maybeSponsor()` overlay card.
  2. **Zone ID Script Loader:** Injected in `<head>` as `<script src="https://thubanoa.com/1?z={zone_id}"></script>`.
  3. **Rewarded Popup / Rewarded Interstitial / In-App Interstitial:** **NOT supported.** No slot or event hooks exist for SDK initialization or trigger calls.

### 3.d. Backup, Diff Preview, and Rollback
* **Baseline Status:** **None.**
* Saving in `Manager.py` or running `dev_tools.py set-ad` immediately overwrites files. There is no timestamped backup directory, no unified diff preview, and no rollback action in the baseline.

### 3.e. Does regenerating the mini-apps keep injected ads?
* **In the baseline: NO.** Any ad directly written to `webroot/<bot_id>/index.html` is erased upon the next run of `build_mini_apps.py` due to `shutil.rmtree()`.
* **Solution required:** The generator (`tools/build_mini_apps.py` and `tools/app_template.py`) must be made **marker-aware**, querying the centralized ad model during generation so that rebuilding always emits the exact same protected ad blocks.

### 3.f. Secret Hygiene & Git History Scan
* **`.gitignore` Audit:** [`.gitignore`](file:///d:/بودة/@Boda_Bot/.gitignore) correctly ignores `.env`, `.env.local`, `Data/`, `Backups/`, `*.db`, `*.sqlite`, `tokens.py`, `secrets.py`, `SECURITY_AUDIT_TOKENS.md`, and `stats.json`.
* **Git History Scan:** A regex audit across `git log -p --all` revealed that early historical commits (`9a9fcd60`, `9d2a29e0`, `5e80b5ae`, `ebaae96c`) contained bot tokens before commit `9d2a29e` extracted them to `.env`. Current working tree and recent commits are free of plaintext secrets.

### 3.g. Git Remote, Current Branch, and Current Publishing Workflow
* **Remote:** `origin` -> `https://github.com/abdalrhmenabdaalim1111-hub/Boda_Bot.git`
* **Current Working Branch:** `feature/ad-publish`
* **Current Publishing Method:** Manual push to `main` (`git push origin main`), which triggers `.github/workflows/pages.yml` in GitHub Actions to build and deploy to GitHub Pages.

---

## 3. Architecture Gaps & Risks

1. **Risk R1: Generator Overwrites Injected Files (`shutil.rmtree`)**
   * *Impact:* High. If an ad injector writes directly to `webroot/currency/index.html`, any subsequent rebuild by `ad_watcher` or `Manager.py` wipes it out.
   * *Mitigation:* The ad engine must be the single source of truth (SQLite + synced JSON), and the generator in `tools/build_mini_apps.py` must query the ad resolver and emit the same marker blocks.
2. **Risk R2: Watcher Race Condition**
   * *Impact:* Medium. `AdConfigWatcher` polls every 2 seconds. If a file is partially written or being injected, a race condition could trigger a rebuild mid-write.
   * *Mitigation:* Atomic writes using temporary files (`tempfile.NamedTemporaryFile` + `os.replace`), coupled with process file locks.
3. **Risk R3: GitHub Pages CDN Caching Delay**
   * *Impact:* Medium. GitHub Pages uses Fastly CDN caches. Even after a successful deploy, users may see cached HTML for 5 to 10 minutes.
   * *Mitigation:* Cache-busting query parameter `?v=<timestamp>` or `<ad_version>` on external script references and assets, along with clear user messaging in the UI.
4. **Risk R4: Malformed Snippets & Security**
   * *Impact:* High. Pasting unvalidated third-party scripts could break HTML structure or introduce unwanted redirects.
   * *Mitigation:* Pre-save validation checking tag balance, maximum size limit (e.g. 64 KB), disallowed patterns (`document.write` to external resources, `eval()`), and domain warnings.

---

## 4. Design Decision & Recommendation for Owner

### The Trade-off: Runtime JSON Config vs Static In-File Marker Injection

We evaluated two architectural approaches for delivering ads to the mini-apps:

#### Option A: Central Runtime Config (`ads-config.json` fetched client-side)
* **How it works:** Mini-apps make an HTTP fetch to `data/ads-config.json` on load and dynamically insert banners or execute SDK calls.
* **Pros:** Updating ads requires changing only one JSON file without touching 35 HTML files.
* **Cons:** Raw Monetag snippets (which contain `<script>` tags, inline initialization functions, and external SDK loaders) cannot be cleanly evaluated via standard JSON parsing. Browsers block `<script>` tags injected via `element.innerHTML` for security reasons, requiring fragile `eval()` or dynamic script tag insertion workarounds.

#### Option B: Static In-File Marker Injection (Recommended Hybrid)
* **How it works:** Ads are injected directly into HTML files between strict idempotent marker comments:
  ```html
  <!-- AD:BEGIN slot=head id=monetag_interstitial -->
  <script src="https://.../sdk.js"></script>
  <!-- AD:END slot=head -->
  ```
  The generator (`tools/build_mini_apps.py`) is taught to emit these exact markers from the ad store.
* **Pros:**
  1. Full compatibility with any Monetag snippet (In-App Interstitial, Rewarded, Banners, SmartLinks).
  2. Byte-for-byte idempotent: saving once or 100 times yields the exact same file.
  3. Supports instant dry-run diffs, file backups, and one-click rollback.
  4. Works completely offline and on GitHub Pages with zero runtime dependency on an external API.

> **Recommendation:** **Option B (Hybrid Static Marker Injection with Generator Awareness)** is strongly recommended. It is robust, preserves Monetag snippet integrity, allows full diff previews, and ensures that rebuilding mini-apps never loses configured ads.

---

## 5. Phased Implementation Plan

| Phase | Scope & Deliverables |
| :---: | :--- |
| **Phase 1: Safe Injection & Storage Engine** | • SQLite schema migration for ads, assignments, and audit events.<br>• Snippet validator (size, balanced tags, security check, domain allowlist).<br>• Marker-based injector (`<!-- AD:BEGIN -->` ... `<!-- AD:END -->`) with atomic file writes.<br>• Automated timestamped backups before writes, unified diff preview, and rollback engine.<br>• Update `tools/app_template.py` and `tools/build_mini_apps.py` to preserve and emit markers.<br>• Unit & integration tests for injection, rollback, idempotency, and generator persistence. |
| **Phase 2: Assignment & Targeting Model** | • Multi-slot support (`head`, `body_end`, `banner_top`, `banner_bottom`, `interstitial`).<br>• Precedence resolution: Bot-specific > Category > Global default.<br>• Effective ad map resolver returning the active ad for each bot/slot. |
| **Phase 3: Manager UI & CLI Integration** | • Upgrade 📢 dialog in `Manager.py`: Ad library (CRUD), Slot picker, Bot selector, **Unified Diff Preview**, Save & Apply, and Rollback button.<br>• Upgrade `dev_tools.py` with `set-ad`, `diff-ad`, `rollback-ad`, and `list-ads`.<br>• Clean Arabic RTL labels adhering to Tkinter conventions. |
| **Phase 4: GitHub Pages One-Click Publisher** | • "Publish to GitHub Pages" action in `Manager.py` and `dev_tools.py publish`.<br>• Staging **only** ad-modified files in `webroot/`, generating a clean commit message, and pushing to `main` without `--force`.<br>• Manual fallback command generator in case of network/git credential issues.<br>• Cache-busting version queries (`?v=<timestamp>`) for fast CDN updates. |
| **Phase 5: Tracking, Audit & Documentation** | • Audit log integration (user, timestamp, action, affected files).<br>• Impression & click tracking linking `ad_id` to `bot_id`.<br>• Full test suite execution across all 600+ tests.<br>• Complete user guide: `docs/ADS_GUIDE.md` in Arabic. |

---

*Phase 0 discovery completed. No application code has been modified. Awaiting owner review and approval.*

