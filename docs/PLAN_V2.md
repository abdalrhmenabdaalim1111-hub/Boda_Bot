# Boda Bot System — Phase 2 Plan (Bot Management & Subscription Gate)

**Status:** DRAFT — awaiting approval before Phase 1 branch creation
**Branch:** `feature/bot-management-and-gate` (to be created)
**Baseline tag:** `pre-gate-baseline` (to be created at commit `ced4b96`)
**Test baseline:** 621 passed, 0 failed

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        BROWSER CONTROL CENTER (control_center/)             │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
│  │ Bots Page   │ │ Bot Detail  │ │ Store Mgr   │ │ Gate Pages  │           │
│  │ (grid/table)│ │ (tabs)      │ │ (CRUD/CSV)  │ │ (channels,  │           │
│  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘ │ profiles)   │           │
│         │               │               │         └──────┬──────┘           │
│         └───────────────┼───────────────┼────────────────┘                  │
│                         ▼               ▼                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    CONTROL CENTER API (/api/v1)                     │   │
│  │  Bots CRUD │ Bot Config │ Audit │ Migrations │ Auth (roles/CSRF)    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│         │               │               │                                   │
│         ▼               ▼               ▼                                   │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                           │
│  │ botconfig.py│ │ migrations  │ │ crypto.py   │                           │
│  │ (runtime    │ │ (reversible,│ │ (Fernet     │                           │
│  │  config)    │ │  numbered)  │ │  tokens)    │                           │
│  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘                           │
│         │               │               │                                   │
│         ▼               ▼               ▼                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    SHARED SQLITE (Data/boda_bot.db)                 │   │
│  │  Existing: users, referrals, network_activations, network_assign-   │   │
│  │  ments, bot_config, audit_log, cc_users, cc_sessions, ad_*        │   │
│  │  NEW (Phase 1–4): sub_channels, gate_profiles, gate_slots,         │   │
│  │  membership_cache, gate_events, store_items, bot_templates        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
         │                                       │
         ▼                                       ▼
┌─────────────────────────┐         ┌─────────────────────────┐
│   34 BOT PROCESSES      │         │   CHECKER BOT (1)       │
│   (Bots_Folder/*.py)    │         │   (gate membership)     │
│   • unified_middleware  │         │   • getChatMember       │
│   • growth_engine       │◄───────►│   • shared cache        │
│   • ad_manager          │  cache  │   • fail-open + alert   │
│   • bot_base            │         └─────────────────────────┘
└─────────────────────────┘
```

### Key Design Decisions (from Phase 0)

| Decision | Rationale |
|----------|-----------|
| `bots_registry.json` remains **catalogue** (source of truth for Store) | Decision D4; runtime config in `bot_config` table |
| `growth_gate` feature flag exists, **DISABLED by default** | Backward compatible; enable per-bot from dashboard |
| **One checker bot** for all 34 bots | Avoids 34× admin requirements; `getChatMember` requires admin |
| **Shared membership cache** across all bots | User verifies once, not re-prompted across bots until TTL expires |
| **Fail-open** on Telegram errors | Never lock all users out; alert admin instead |
| All schema via **reversible migrations** | Rollback safety; backup before each run |
| **Encrypted tokens at rest** (Fernet, `crypto.py`) | Secrets never in plaintext; masked in UI |

---

## 2. Data Model (New Tables)

### 2.1 `sub_channels` — Gate Channels Library
```sql
CREATE TABLE sub_channels (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,                    -- Display name
    chat_type       TEXT NOT NULL CHECK(chat_type IN ('channel','group','supergroup')),
    chat_id         INTEGER NOT NULL UNIQUE,          -- Numeric ID (primary key)
    username        TEXT,                             -- @username if public
    invite_link     TEXT,                             -- Generated invite link (cached)
    language        TEXT NOT NULL DEFAULT 'ar',       -- ar, en, both
    is_active       INTEGER NOT NULL DEFAULT 1,       -- Soft disable
    checker_bot_admin INTEGER NOT NULL DEFAULT 0,     -- Verified: checker bot is admin
    last_validated  TEXT,                             -- ISO timestamp of last getChat success
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_sub_channels_active ON sub_channels(is_active);
```

### 2.2 `gate_profiles` — Gate Configuration Profiles
```sql
CREATE TABLE gate_profiles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE,             -- 'global_default', 'bot_<id>', 'cat_<cat>'
    scope_type      TEXT NOT NULL CHECK(scope_type IN ('global','bot','category')),
    scope_value     TEXT,                             -- bot_id or category name (NULL for global)
    mode            TEXT NOT NULL DEFAULT 'all',      -- 'all', 'at_least_n', 'soft'
    required_count  INTEGER NOT NULL DEFAULT 5,       -- For 'at_least_n'
    soft_free_uses  INTEGER NOT NULL DEFAULT 0,       -- For 'soft' mode
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
-- One global default profile (scope_type='global', scope_value=NULL)
-- Per-bot overrides (scope_type='bot', scope_value='currency')
-- Per-category overrides (scope_type='category', scope_value='أدوات')
```

### 2.3 `gate_slots` — 5-Slot Channel Assignments per Profile
```sql
CREATE TABLE gate_slots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id      INTEGER NOT NULL REFERENCES gate_profiles(id) ON DELETE CASCADE,
    position        INTEGER NOT NULL CHECK(position BETWEEN 1 AND 5),  -- 1..5
    channel_id      INTEGER NOT NULL REFERENCES sub_channels(id),
    is_required     INTEGER NOT NULL DEFAULT 1,       -- This slot must be satisfied
    is_pinned       INTEGER NOT NULL DEFAULT 0,       -- Slot 1: Store channel (always shown)
    display_order   INTEGER NOT NULL DEFAULT 0,       -- UI ordering within position
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(profile_id, position)
);
```

### 2.4 `membership_cache` — Shared Cross-Bot Cache
```sql
CREATE TABLE membership_cache (
    user_id         INTEGER NOT NULL,
    channel_id      INTEGER NOT NULL REFERENCES sub_channels(id) ON DELETE CASCADE,
    status          TEXT NOT NULL CHECK(status IN ('member','not_member','unknown')),
    checked_at      TEXT NOT NULL,                    -- ISO timestamp
    expires_at      TEXT NOT NULL,                    -- ISO timestamp (TTL from config)
    PRIMARY KEY (user_id, channel_id)
);
CREATE INDEX idx_membership_expires ON membership_cache(expires_at);
```

### 2.5 `gate_events` — Audit & Funnel Analytics
```sql
CREATE TABLE gate_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id          TEXT NOT NULL,                    -- Registry bot id
    user_id_hash    TEXT NOT NULL,                    -- SHA256(user_id || salt) for privacy
    event           TEXT NOT NULL CHECK(event IN (
        'gate_shown', 'join_clicked', 'verify_clicked', 'verified', 'failed_open', 'skipped_admin'
    )),
    channel_id      INTEGER,                          -- Relevant channel (nullable)
    profile_id      INTEGER,                          -- Gate profile used
    metadata        TEXT,                             -- JSON: {missing_slots, mode, ...}
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_gate_events_bot_time ON gate_events(bot_id, created_at);
CREATE INDEX idx_gate_events_user_time ON gate_events(user_id_hash, created_at);
```

### 2.6 `store_items` — Store Catalog (extends registry fields)
```sql
CREATE TABLE store_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id          TEXT NOT NULL UNIQUE REFERENCES bot_config(bot_id) ON DELETE CASCADE,
    title_ar        TEXT NOT NULL,
    title_en        TEXT,
    short_desc_ar   TEXT,
    short_desc_en   TEXT,
    long_desc_ar    TEXT,
    long_desc_en    TEXT,
    icon_url        TEXT,                             -- Custom icon (optional, fallback to emoji)
    cover_url       TEXT,                             -- Cover image for featured
    category        TEXT NOT NULL DEFAULT 'أخرى',
    tags            TEXT,                             -- CSV: 'جديد,شائع,أدوات'
    badges          TEXT,                             -- CSV: 'New,Popular,Featured'
    display_order   INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'live' CHECK(status IN ('live','hidden','coming_soon')),
    deep_link       TEXT,                             -- t.me/botusername
    miniapp_url     TEXT,                             -- Full Mini App URL
    views           INTEGER NOT NULL DEFAULT 0,
    opens           INTEGER NOT NULL DEFAULT 0,
    clicks          INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### 2.7 `bot_templates` — Add Bot Wizard Templates
```sql
CREATE TABLE bot_templates (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE,             -- 'base', 'miniapp', 'store_promo', etc.
    description     TEXT,
    base_class      TEXT NOT NULL DEFAULT 'BotBase',  -- Python base class
    features        TEXT NOT NULL DEFAULT '[]',       -- JSON array: ['ads','growth_gate','miniapp']
    template_files  TEXT NOT NULL,                    -- JSON: {dest: source_template}
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### 2.8 Migration Sequence
| Version | Name | Tables Created |
|---------|------|----------------|
| 3 | `gate_foundation` | `sub_channels`, `gate_profiles`, `gate_slots`, `membership_cache`, `gate_events` |
| 4 | `store_manager` | `store_items` |
| 5 | `bot_templates` | `bot_templates` |
| 6 | `bot_profile_fields` | Add `profile_name_ar`, `profile_name_en`, `profile_desc_ar`, `profile_desc_en`, `profile_short_ar`, `profile_short_en`, `profile_commands_ar`, `profile_commands_en`, `profile_menu_ar`, `profile_menu_en` to `bot_config` |

---

## 3. Gap Table: Current → Target

| Area | Current State | Target State | Gap |
|------|---------------|--------------|-----|
| **Bot Registry** | `bots_registry.json` (34 bots, 11 fields) | CRUD via Control Center; wizard generates files, registers, starts | Add/Edit/Archive/Delete/Restore UI + API; file generation; token validation |
| **Bot Profile** | None (hardcoded in bot files / BotFather) | Per-bot, per-language (ar/en): name, desc, short_desc, commands, menu button; live diff; apply via API | `bot_config` profile fields; Profile Manager UI; Telegram API sync with validation |
| **Store Catalog** | Generated from `bots_registry.json` via `build_mini_apps.py` | CRUD in dashboard; drag-drop order; featured carousel; stats; build & publish to GitHub Pages | `store_items` table; Store Manager UI; publish pipeline; stats tracking |
| **Subscription Gate** | `growth_engine`: 5-bot assignment, DB `has_user_started` check, TTL 7d, fixed store bot | Up to 5 channels/groups per bot; central checker bot (`getChatMember`); shared cache; profiles (global/bot/category); pinned Store slot; modes (all/at_least_n/soft); fail-open; funnel stats | **Complete rewrite** of gate logic; new tables; checker bot integration; dashboard |
| **Gate UX** | Sends new message with inline keyboard per bot | Edit existing message; one URL button per missing slot + single "Verify"; Arabic/English; success animation | Middleware integration; message edit logic; i18n |
| **Checker Bot** | None (bot-to-bot via DB) | Dedicated bot (admin in all gate channels); health checks; per-bot fallback | Checker bot token in env; admin validation API; health panel |
| **Caching** | In-memory `_activation_cache` (per bot, TTL 7d) | Shared SQLite `membership_cache` (TTL configurable, default 24h); cross-bot | New table; cache invalidation; background re-validation job |
| **Stats/Funnel** | None | Gate funnel per bot (shown, clicked, verified, drop-off); joins per channel; CSV/JSON export | `gate_events` table; Statistics page; export API |
| **Add Bot Wizard** | Manual: create file, add to registry, add token to .env | Wizard: name, token (live `getMe`), category, tier, template, language, miniapp URL, store visibility; generates files, registers, starts | Multi-step wizard; file templates; `getMe` validation; duplicate detection |
| **Archive/Delete** | None | Archive (soft: stop, hide, keep data, restore); Delete (backup, confirm, remove files/registry) | API endpoints; UI confirmations; backup automation |
| **Auth/Roles** | Basic (hashed pw, sessions, CSRF) | Roles: admin/editor/viewer; token encryption; audit log for all actions | Extend `cc_users` with `role`; RBAC in API; audit on all mutations |
| **CLI Parity** | `dev_tools.py` has some commands | `gate-status`, `gate-set`, `channel-add`, `bot-add`, `bot-archive`, `profile-sync`, `store-publish` | Extend `dev_tools.py` |

---

## 4. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **Checker bot loses admin** in a gate channel | Medium | Gate silently breaks for that channel | Dashboard health check (`getChat` + `getChatAdministrators`); periodic job; admin alert on failure |
| **`getChatMember` rate limit** (34 bots × users) | High | Fail-open triggers, users bypass gate | Shared cache (TTL 24h+); batch re-validation queue; exponential backoff; per-bot fallback checker |
| **Channel username changes** | Low | Invite links break | Store `chat_id` (int) as PK; username display only; re-validate on edit |
| **Profile sync hits 429 on bulk apply** | Medium | Partial apply, inconsistent state | Configurable inter-bot delay (default 300ms); retry with backoff; idempotent apply; progress UI |
| **Managed bot API changes/removed** | Low | Optional wizard path breaks | Keep manual token path primary; managed path behind feature flag |
| **Migration data loss** | Low | Irreversible corruption | Timestamped backup before every migration; reversible `down` scripts; test on copy first |
| **Secrets in logs/commits** | Medium | Token leakage | `crypto.py` masks tokens; audit log sanitizes; `.gitignore` for `.env`; pre-commit hooks |
| **Gate blocks /start, /help, admins** | Medium | User frustration, support load | Middleware: skip gate for `/start`, `/help`, language switch, admin user IDs (configurable) |
| **Store publish breaks GitHub Pages** | Low | Downtime | Commit only changed files; never force-push; manual fallback commands shown; propagation time reported |

---

## 5. Phased Implementation Plan

### Phase 1: Foundation — Migrations, Registry Management, Bot Profile Manager
**Duration:** ~3–4 days  
**Branch:** `feature/bot-management-and-gate` (from `ced4b96`, tag `pre-gate-baseline`)

| Task | Files | Verification |
|------|-------|--------------|
| Create migrations 3–6 (gate_foundation, store_manager, bot_templates, bot_profile_fields) | `control_center/migrations.py` | `python -m control_center.migrations up`; `down` restores schema |
| Backup script (timestamped SQLite copy) | `control_center/backup.py` (new) | Run before Phase 1; verify restore |
| Bot Registry CRUD API (`POST/GET/PATCH/DELETE /api/v1/bots`) | `control_center/api.py`, `control_center/botconfig.py` | Swagger UI: add bot → appears in list; edit → persists; archive → hidden; restore → visible |
| Add Bot Wizard (multi-step): token `getMe` validation, duplicate detection, template selection, file generation, registry entry, start bot | `control_center/api.py`, `tools/bot_wizard.py` (new), templates in `Bots_Folder/templates/` | Wizard completes → bot responds to `/start` in Telegram |
| Bot Profile Manager: per-bot, per-language fields in `bot_config`; live diff via `getMy*`; apply with validation (lengths from TELEGRAM_CAPABILITIES.md) | `control_center/botconfig.py`, `control_center/api.py`, `Bots_Folder/bot_profile.py` (new) | Dashboard: edit name/desc/commands/menu → "Preview Diff" shows current vs stored → "Apply" succeeds → verified via `getMy*` |
| Archive/Delete: soft delete (stop, disable webhook, hide from store, keep data); hard delete (backup, typed confirmation, remove files/registry) | `control_center/api.py`, `control_center/supervisor.py` | Archive → bot stopped, hidden, data intact; Restore → bot running; Delete → backup exists, files removed, registry entry gone |
| Clone bot from template; bulk enable/disable; drag-drop ordering | `control_center/api.py`, frontend | UI: clone → new bot with suffix; bulk toggle → all change; drag → order persists |

**Visible Result:** Control Center Bots page + Bot Detail → Profile tab: edit name/description/commands/menu button per language, live diff, apply to Telegram. Add Bot wizard creates a working bot.

**Test Gate:** Full pytest suite (621+ tests) passes. New tests for migrations up/down, registry CRUD, profile apply (success, rate limit, invalid token, over-limit text).

---

### Phase 2: Store Manager + Build & Publish
**Duration:** ~2–3 days

| Task | Files | Verification |
|------|-------|--------------|
| `store_items` CRUD API (`/api/v1/store`) | `control_center/api.py`, `control_center/store.py` (new) | Swagger: create/edit/delete store item; linked to bot_id |
| Store Manager UI: grid/table, drag-drop order, featured carousel, categories, tags, badges, status, preview | `webroot/dashboard/store.html` (new), JS modules | UI: reorder → order persists; toggle featured → carousel updates; preview matches user view |
| Build & Publish: regenerate `catalog.json` + Mini App pages from `store_items`; preserve ad markers; commit changed files only; push to GitHub Pages (no force-push); report propagation time | `tools/build_mini_apps.py` (extend), `tools/publish_store.py` (new) | Click "Publish" → `webroot/data/catalog.json` updated → GitHub Pages shows new order within reported time |
| Store Stats: views, opens, clicks, conversion (from `gate_events` + Mini App tracking) | `control_center/api.py`, `gate_events` table | Dashboard: stats panel shows funnel per item |

**Visible Result:** Store Manager page: CRUD items, drag-drop, preview, "Build & Publish" button with live propagation report.

**Test Gate:** Full pytest + new tests for store CRUD, publish (temp git repo), stats aggregation.

---

### Phase 3: Subscription Gate Core
**Duration:** ~4–5 days

| Task | Files | Verification |
|------|-------|--------------|
| Checker Bot integration: token from env (`BOT_GATE_CHECKER_TOKEN`); `getChatMember` wrapper with cache; fail-open + admin alert | `Bots_Folder/gate_checker.py` (new), `control_center/gate.py` (new) | Unit test: checker returns `member`/`not_member`; on 429/error → fail-open + log |
| Channel Library API (`/api/v1/gate/channels`): add/edit/test/disable; validate `getChat` + admin check | `control_center/api.py`, `control_center/gate.py` | Dashboard: add channel → "Test" button shows ✅ reachable, ✅ checker is admin |
| Gate Profiles API (`/api/v1/gate/profiles`): global default + per-bot + per-category; 5-slot visual editor | `control_center/api.py`, `control_center/gate.py` | UI: create profile → assign 5 channels → set mode (all/at_least_n/soft) → save |
| Gate Slots: position 1 pinned to Store channel (configurable); required/optional per slot | `gate_slots` table, API | Slot 1 locked to Store; other slots editable |
| Bot-side Middleware: integrate gate check into `unified_middleware` / `growth_engine`; **disabled by default** (`growth_gate` flag); checks cache → checker → shows gate message | `Bots_Folder/unified_middleware.py`, `Bots_Folder/growth_engine.py`, `Bots_Folder/gate_middleware.py` (new) | Enable flag for test bot → user sees gate message with join buttons + Verify |
| Gate Message UX: edit existing message (not new); one URL button per missing slot + single "✅ Verify"; Arabic/English; success animation | `Bots_Folder/gate_middleware.py` | User joins missing → clicks Verify → message edits to success → bot unlocked |
| Shared Membership Cache: `membership_cache` table; TTL configurable (default 24h); cross-bot | `control_center/gate.py`, `Bots_Folder/gate_middleware.py` | User verifies in bot A → opens bot B → no gate shown (until TTL expires) |
| Background Re-validation Job: periodic (configurable) re-check of cached memberships; handle left/kicked | `Bots_Folder/gate_scheduler.py` (new), APScheduler or threading.Timer | Wait TTL → user re-checked → gate shown if left |

**Visible Result:** Gate health panel shows all channels ✅/❌; enable gate on test bot → user flow works; verify once → skip across bots.

**Test Gate:** Full pytest + new gate tests: all/at_least_n/soft modes, pinned slot, cache sharing, TTL expiry, fail-open on Telegram errors, checker not admin, channel unreachable.

---

### Phase 4: Gate Dashboard, Previews, Stats, Pilot
**Duration:** ~3–4 days

| Task | Files | Verification |
|------|-------|--------------|
| Gate Dashboard: Channels library, Profiles editor (visual 5-slot), Per-bot preview (exact user view), Bulk apply to bots/categories | `webroot/dashboard/gate.html` (new), JS modules | UI: edit profile → preview shows exact message → "Apply to selected bots" → flags updated |
| Gate Health Panel: per-channel status (reachable, checker admin, member count), error rate, last check | `control_center/api.py`, `control_center/gate.py` | Dashboard: red/yellow/green indicators; click → diagnostics in Arabic |
| Gate Funnel Stats: per bot (shown, clicked, verified, drop-off), per channel (joins), conversion by category/day, CSV/JSON export | `control_center/api.py`, `gate_events` table | Dashboard: charts + export button → CSV opens in Excel |
| Alerts: admin chat notification on checker not admin, channel unreachable, high fail-open rate | `Bots_Folder/gate_alerts.py` (new), `control_center/alerts.py` (new) | Simulate checker demotion → alert received in admin chat |
| Compliance Guardrails: honest-copy warnings (medical/financial/guarantee claims) in Profile Manager & Gate message editor; `docs/GATE_POLICY.md` | `control_center/botconfig.py`, `docs/GATE_POLICY.md` (new) | Type "guaranteed cure" → warning shown with neutral suggestion |
| **Pilot on 3 bots** (STOP for owner review on real Telegram account) | — | Owner tests: gate flow, cache sharing, stats, alerts |

**Visible Result:** Complete Gate dashboard; pilot on 3 bots verified by owner.

**Test Gate:** Full pytest + Playwright smoke tests (desktop + mobile viewports).

---

### Phase 5: Rollout, Bulk Tools, CLI Parity, Docs, Performance
**Duration:** ~2–3 days

| Task | Files | Verification |
|------|-------|--------------|
| Rollout to all bots in groups (by category/tier); bulk enable/disable gate | `control_center/api.py`, `Bots_Folder/gate_middleware.py` | Dashboard: "Enable Gate for Category: أدوات" → all bots in category get flag |
| CLI Parity (`dev_tools.py`): `gate-status`, `gate-set`, `channel-add`, `bot-add`, `bot-archive`, `profile-sync`, `store-publish` | `dev_tools.py` (extend) | `python dev_tools.py gate-status` → table; `profile-sync` → all bots synced |
| Arabic User Guide: `docs/GATE_GUIDE_AR.md`, `docs/STORE_GUIDE_AR.md` | `docs/` | Owner reads → can operate independently |
| Performance: cache hit rate >90%; gate check <50ms p99; bulk sync <30s for 34 bots | Load test script | Metrics logged; no regressions |
| Regression Pass: full test suite, Playwright, manual smoke on 5 bots | — | All green |

**Visible Result:** All 34 bots manageable from dashboard; gate configurable per bot/category; CLI parity; Arabic docs.

**Definition of Done:**
- [ ] From browser: edit any bot's name/desc/commands/menu → applied to Telegram
- [ ] Add/archive/restore/delete bots from system
- [ ] Manage & publish Store catalog
- [ ] Configure up to 5 gate channels per bot (Store pinned) with global defaults + overrides
- [ ] Preview exact user view
- [ ] Watch gate funnel stats
- [ ] Users verify once → not re-prompted across bots until cache expires
- [ ] Gate failures fail open + alert admin
- [ ] All tests pass (pytest + Playwright)
- [ ] No secrets in repo
- [ ] Docs updated

---

## 6. Estimate Summary

| Phase | Duration | Cumulative |
|-------|----------|------------|
| Phase 1: Foundation + Profile Manager | 3–4 days | 3–4 days |
| Phase 2: Store Manager + Publish | 2–3 days | 5–7 days |
| Phase 3: Gate Core | 4–5 days | 9–12 days |
| Phase 4: Gate Dashboard + Pilot | 3–4 days | 12–16 days |
| Phase 5: Rollout + CLI + Docs | 2–3 days | 14–19 days |
| **Total** | **14–19 working days** | |

---

## 7. Approval Checklist

Before creating branch and starting Phase 1, please confirm:

- [ ] `docs/TELEGRAM_CAPABILITIES.md` limits match your expectations
- [ ] Data model (7 new tables) covers all requirements
- [ ] Gap table accurately reflects current vs target
- [ ] Risks are acknowledged; fail-open + checker bot pattern accepted
- [ ] Phased estimates are acceptable
- [ ] Pilot on 3 bots (Phase 4) is the correct gate before full rollout
- [ ] Arabic RTL dashboard, dark/light, responsive — design system in `docs/DESIGN_SYSTEM.md` to be followed

**Reply "go" to approve and proceed with Phase 1.**