# Telegram Bot API Capabilities & Limits

**Source:** [core.telegram.org/bots/api](https://core.telegram.org/bots/api) (accessed 2026-11-11)
**Purpose:** Authoritative reference for Phase 1–6 implementation. Do not hardcode limits from memory.

---

## 1. Bot Profile Methods (Bot Profile Manager)

| Method | Parameters | Limits | Notes |
|--------|------------|--------|-------|
| `setMyName` | `name` (0–64 chars), `language_code` (ISO 639-1, optional) | **Name: 64 chars max** | Empty string removes dedicated name for language. |
| `setMyDescription` | `description` (0–512 chars), `language_code` (optional) | **Description: 512 chars max** | Shown in empty chat. Empty string removes for language. |
| `setMyShortDescription` | `short_description` (0–120 chars), `language_code` (optional) | **Short description: 120 chars max** | Shown on profile page & share link. Empty string removes. |
| `setMyCommands` | `commands` (Array\<BotCommand\>, **max 100**), `scope` (optional), `language_code` (optional) | **100 commands max**; each `command` 1–32 chars (a-z, 0-9, `_`); `description` 1–256 chars | Scope: default, all private chats, all group chats, specific chat, chat member, chat administrators. Per-language overrides supported. |
| `setChatMenuButton` | `chat_id` (optional), `menu_button` (MenuButton object, optional) | MenuButton types: `default`, `commands`, `web_app` (requires `url`) | `chat_id` omitted → changes **default** menu button. WebApp URL must be HTTPS. |
| `setMyProfilePhoto` | `photo` (InputProfilePhoto) | Photo: JPEG/PNG, **max 10 MB** (via multipart), or `file_id`/`URL` | **Available** per Bot API. InputProfilePhoto can be `InputProfilePhotoStatic` (file), `InputProfilePhotoAnimated` (animation). |

### Corresponding `get*` Methods (for live diff)
- `getMyName(language_code?)` → current name
- `getMyDescription(language_code?)` → current description
- `getMyShortDescription(language_code?)` → current short description
- `getMyCommands(scope?, language_code?)` → current commands
- `getChatMenuButton(chat_id?)` → current menu button

---

## 2. Subscription Gate Methods (Central Checker Bot)

| Method | Parameters | Limits | Critical Notes |
|--------|------------|--------|----------------|
| `getChatMember` | `chat_id` (int or `@username`), `user_id` (int) | **Bot MUST be administrator** in the target chat. Works for channels, supergroups, groups. | Returns `ChatMember` with `status`: `creator`, `administrator`, `member`, `restricted`, `left`, `kicked`. **Only guaranteed to work for other users if bot is admin.** |
| `createChatInviteLink` | `chat_id`, `name` (0–32 chars), `expire_date` (Unix ts), `member_limit` (1–99999), `creates_join_request` (bool) | Bot must be admin with **invite link** rights. `member_limit` and `creates_join_request` are mutually exclusive. | Use to generate per-slot invite links for gate UI. |
| `getChat` | `chat_id` (int or `@username`) | Bot must be member (admin not strictly required but recommended). | Returns `ChatFullInfo` — verify chat exists, type, title, username, member count. |
| `exportChatInviteLink` | `chat_id` | Bot must be admin. | Creates **primary** invite link (revokes previous primary). |

### ChatMember Status Values
| Status | Meaning | Gate Decision |
|--------|---------|---------------|
| `creator` | Owner | ✅ Member |
| `administrator` | Admin | ✅ Member |
| `member` | Regular member | ✅ Member |
| `restricted` | Restricted (may have limited rights) | ✅ Member (usually) |
| `left` | Left the chat | ❌ Not member |
| `kicked` | Banned | ❌ Not member |

---

## 3. Managed Bots (Optional "Add Bot" Wizard Path)

| Method | Parameters | Availability | Notes |
|--------|------------|--------------|-------|
| `getManagedBotToken` | `user_id` (managed bot's user id) | ✅ Available | Returns bot token as string. Requires the calling bot to be the **manager** (created via BotFather "Manage Bots"). |
| `replaceManagedBotToken` | `user_id` | ✅ Available | Revokes current token, generates new one. |
| `getManagedBotAccessSettings` | `user_id` | ✅ Available | Returns access settings (can_join_groups, can_read_all_group_messages, etc.). |
| `setManagedBotAccessSettings` | `user_id`, `access_settings` | ✅ Available | Modify managed bot permissions. |

**Managed bots** are created via @BotFather → "Manage Bots" → "Create New Bot". The manager bot receives the token and can configure the managed bot programmatically. This is an **optional** path for the Add Bot wizard; the primary path remains "paste token from BotFather".

---

## 4. Rate Limits (Critical for Gate & Bulk Operations)

| Context | Limit | Error | Mitigation |
|---------|-------|-------|------------|
| Single private chat | ~1 msg/sec (short bursts OK) | 429 Too Many Requests | Queue, exponential backoff, respect `Retry-After`. |
| Group/Supergroup | 20 msg/min | 429 | Batch, throttle. |
| Bulk notifications (broadcast) | ~30 msg/sec (free), 1000 msg/sec (paid, Stars) | 429 | Spread over 8–12 hrs; enable Paid Broadcasts if needed. |
| `getChatMember` / `getChat` | Undocumented; treat as ~30/sec | 429 | **Cache aggressively** (TTL hours/days). Queue re-checks. |
| Profile methods (`setMy*`) | Low frequency expected | 429 | Sync with delay (configurable, default 200–500 ms between bots). |

**Fail-open rule:** Any Telegram API error during membership check → **allow access**, log alert, notify admin chat.

---

## 5. BotCommand Object Limits

| Field | Limit |
|-------|-------|
| `command` | 1–32 chars, lowercase a-z, 0-9, underscore only |
| `description` | 1–256 chars |
| `is_ephemeral` | Optional boolean |

**Max 100 commands per scope/language combination.**

---

## 6. MenuButton Types

| Type | Fields | Use Case |
|------|--------|----------|
| `MenuButtonDefault` | — | Reset to default (commands). |
| `MenuButtonCommands` | — | Show commands list. |
| `MenuButtonWebApp` | `text` (1–16 chars), `web_app` (WebAppInfo with `url`) | **Mini App entry point** — primary for this project. |

**WebApp URL must be HTTPS.** Text max 16 chars (Arabic counts as 1 char each).

---

## 7. InputProfilePhoto (for `setMyProfilePhoto`)

| Sub-type | Fields |
|----------|--------|
| `InputProfilePhotoStatic` | `photo` (InputFile or String file_id/URL), `sticker_area` (optional) |
| `InputProfilePhotoAnimated` | `animation` (InputFile or String file_id/URL), `main_frame_timestamp` (optional), `sticker_area` (optional) |

---

## 8. Implementation Checklist for This Project

- [ ] **Profile Manager:** Validate lengths client-side (64/512/120) before API call.
- [ ] **Profile Manager:** Per-language support (ar, en) via `language_code`.
- [ ] **Profile Manager:** Live diff using `getMy*` methods before apply.
- [ ] **Profile Manager:** Rate-limit sync (configurable delay, retry/backoff on 429).
- [ ] **Gate Checker:** Dedicated bot added as **admin** in all gate channels.
- [ ] **Gate Checker:** `getChatMember` cache with TTL (configurable, default 24h).
- [ ] **Gate Checker:** Fail-open on any Telegram error + admin alert.
- [ ] **Gate Checker:** `createChatInviteLink` for per-slot join buttons.
- [ ] **Gate Checker:** `getChat` validation on channel add (verify reachable, bot is admin).
- [ ] **Add Bot Wizard:** Offer managed bot path (optional) + manual token path.
- [ ] **Bulk Operations:** Respect 30 msg/sec broadcast limit; queue with backoff.

---

## 9. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Checker bot loses admin in a channel | Medium | Gate breaks for that channel | Dashboard health check (`getChat` + `getChatAdministrators`), auto-alert. |
| `getChatMember` rate limit hit | High (34 bots × users) | Gate delays/fail-open | Shared cache across all bots, TTL 24h+, background re-validation queue. |
| Profile sync hits 429 on bulk apply | Medium | Partial apply | Configurable inter-bot delay (default 300 ms), retry with exponential backoff. |
| Managed bot API changes | Low | Optional wizard path breaks | Keep manual token path as primary; managed path optional. |
| Channel username changes | Low | Invite links break | Store `chat_id` (int) as primary key; username as display only. |
| Telegram reduces free broadcast limit | Low | Store publish notifications delayed | Spread notifications; paid broadcasts not needed for this scale. |

---

## 10. Quick Reference: Method → Project Feature Mapping

| Feature | Methods Used |
|---------|--------------|
| Bot Profile Manager (name/desc/short_desc/commands/menu) | `setMyName`, `setMyDescription`, `setMyShortDescription`, `setMyCommands`, `setChatMenuButton`, `setMyProfilePhoto` (+ `getMy*` for diff) |
| Add Bot Wizard (managed) | `getManagedBotToken`, `setManagedBotAccessSettings` (optional) |
| Gate: Channel Validation | `getChat`, `getChatAdministrators` |
| Gate: Invite Links | `createChatInviteLink` |
| Gate: Membership Check | `getChatMember` (via checker bot) |
| Gate: Health Monitoring | `getChat`, `getChatAdministrators` (periodic) |

---

*Document generated during Phase 0 Discovery. Update if Telegram API changes.*