"""
bot_store.py — Boda Store | متجر بودة v5.1
@BodaStoreeBot
"""

import time
import os, sys, json
import telebot
from telebot.types import (InlineKeyboardMarkup, InlineKeyboardButton, ForceReply)
from pathlib import Path

# ── تحميل .env ────────
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

# ── إعداد Logging ───────────
try:
    from logger_config import get_logger, configure_windows_encoding
    configure_windows_encoding()
    log = get_logger("store")
except ImportError:
    import logging
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    logging.basicConfig(level=logging.INFO,
                        format="[Store] %(asctime)s %(message)s",
                        datefmt="%H:%M:%S")
    log = logging.getLogger("store")

# ── الإعدادات من .env ────────
# 🔒 أمان: التوكن وكلمة المرور من .env فقط — ممنوع وضع قيم افتراضية في الكود
from bot_base import get_token
TOKEN          = get_token("BOT_STORE_TOKEN")
_here          = os.path.dirname(os.path.abspath(__file__))
REGISTRY       = os.path.normpath(os.path.join(_here, "..", "bots_registry.json"))
ADMIN_PASSWORD = os.getenv("STORE_ADMIN_PASSWORD", "")
# معرفات حسابات الأدمن (يمكن إضافتها في .env كـ STORE_ADMIN_IDS=123,456)
_admin_ids_raw = os.getenv("STORE_ADMIN_IDS", "")
PRE_APPROVED_ADMINS = {int(x) for x in _admin_ids_raw.split(",") if x.strip().isdigit()}
ADMIN_USERS    = set(PRE_APPROVED_ADMINS)  # يبدأ بالمعتمدين مسبقاً
edit_state     = {}

if not TOKEN or TOKEN == "ضع_التوكن_هنا":
    log.error("❌ BOT_STORE_TOKEN غير محدد في .env")
    sys.exit(1)

if not ADMIN_PASSWORD:
    log.warning("⚠️ STORE_ADMIN_PASSWORD غير محدد في .env — لوحة الأدمن عبر كلمة المرور معطّلة (استخدم STORE_ADMIN_IDS)")

bot = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True)

# ── Registry ───────────
def load_apps():
    try:
        with open(REGISTRY, encoding="utf-8") as f:
            apps = json.load(f)
        visible = [a for a in apps if not a.get("hidden")]
        log.info(f"Registry: {len(apps)} total, {len(visible)} visible")
        return apps
    except Exception as e:
        log.error(f"Registry error: {e}")
        return []

def save_apps(apps):
    with open(REGISTRY, "w", encoding="utf-8") as f:
        json.dump(apps, f, ensure_ascii=False, indent=2)

def _esc(s: str) -> str:
    return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

# ── بادج "🆕 جديد" ───────────
NEW_DAYS = 30  # نعتبر البوت "جديداً" إذا أضيف في آخر 30 يوماً

def _is_new(app: dict) -> bool:
    """True إذا أضيف البوت في آخر NEW_DAYS يوماً"""
    added = app.get("added_date", "")
    if not added:
        return False
    try:
        from datetime import datetime, timedelta
        dt = datetime.strptime(added, "%Y-%m-%d")
        return (datetime.now() - dt).days <= NEW_DAYS
    except Exception:
        return False

# ── إحصائيات المتجر (للأدمن) ──────────
_store_stats = {
    "start_count":    0,   # عدد /start
    "unique_users":   set(),
    "popular_bots":   {},  # bot_id -> click_count
}


# ── Store message builder v5.0 ───────
def build_store_text(apps: list) -> str:
    visible = [a for a in apps if not a.get("hidden")]
    count   = len(visible)

    lines = [
        "╔══════════════════════════╗",
        "  🏪  <b>مـتـجـر بـودة</b>",
        "╚══════════════════════════╝",
        "",
        f"<b>✨ {count} بوت مجاني</b> — كل أدواتك في مكان واحد!",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    for i, app in enumerate(visible, 1):
        em      = app.get("emoji", "🤖")
        name    = _esc(app.get("name", ""))
        sdesc   = _esc(app.get("short_desc", ""))
        tag     = _esc(app.get("tag", "مجاني"))
        lines.append(f"{i}. {em} <b>{name}</b>")
        lines.append(f"    ┗ <i>{sdesc}</i>")
        lines.append(f"    <code>#{tag}</code>")
        lines.append("")

    lines += [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "👆 <i>اضغط على البوت لفتحه مباشرة</i>",
        "",
        "🤖 <i>Powered by Boda Bot System</i>",
    ]
    return "\n".join(lines)

def build_store_kb(apps: list) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    for app in apps:
        if app.get("hidden") or not app.get("url","").startswith("http"):
            continue
        kb.add(InlineKeyboardButton(
            text=f"{app.get('emoji','🤖')}  {app.get('name','')}",
            url=app["url"],
        ))
    kb.add(InlineKeyboardButton("🔗  شارك المتجر مع أصدقائك",
                                switch_inline_query="Boda Store"))
    return kb

# ── Commands ──────────────────────────────────────────────────────────────────
@bot.message_handler(commands=["start","store","apps","help","بوتات"])
def cmd_start(message):
    uid = message.from_user.id
    _store_stats["start_count"] += 1
    _store_stats["unique_users"].add(uid)
    log.info(f"/start from {uid} (@{message.from_user.username})")
    apps = load_apps()
    if not apps:
        bot.send_message(message.chat.id, "⚠️ خطأ في تحميل البوتات.")
        return
    try:
        sent = bot.send_message(message.chat.id,
                                build_store_text(apps),
                                reply_markup=build_store_kb(apps))
        if message.chat.type in ("group","supergroup"):
            try: bot.pin_chat_message(message.chat.id, sent.message_id,
                                      disable_notification=True)
            except: pass
    except Exception as e:
        log.error(f"Send HTML error: {e}")
        try:
            visible = [a for a in apps if not a.get("hidden")]
            text    = "🎪 Boda Store\n\n" + "\n".join(
                f"{a.get('emoji','')} {a.get('name','')}: {a.get('url','')}"
                for a in visible)
            bot.send_message(message.chat.id, text,
                             reply_markup=build_store_kb(apps), parse_mode=None)
        except Exception as e2:
            log.error(f"Fallback error: {e2}")
@bot.message_handler(commands=["refresh"])
def cmd_refresh(message):
    """Force refresh the store message."""
    cmd_start(message)

# ── Admin ──────────────
@bot.message_handler(commands=["admin"])
def cmd_admin(message):
    uid = message.from_user.id
    if uid in ADMIN_USERS:
        bot.send_message(message.chat.id,
                         "🛠️ <b>لوحة التحكم — متجر بودة</b>",
                         reply_markup=_admin_main_kb())
    else:
        bot.send_message(message.chat.id,
                         "🔐 <b>منطقة محمية</b>\n"
                         "<i>أرسل كلمة المرور للوصول:</i>")

def _admin_main_kb():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("📋  عرض ويتحكم في البوتات", callback_data="adm:list"),
        InlineKeyboardButton("➕  إضافة بوت جديد",        callback_data="adm:add"),
        InlineKeyboardButton("🔄  تحديث المتجر",           callback_data="adm:reload"),
        InlineKeyboardButton("🚪  تسجيل الخروج",           callback_data="adm:logout"),
    )
    return kb

def _admin_list_kb(apps):
    kb = InlineKeyboardMarkup(row_width=1)
    for app in apps:
        h   = " 🔴" if app.get("hidden") else " 🟢"
        kb.add(InlineKeyboardButton(
            f"{app.get('emoji','')} {app.get('name','')}{h}",
            callback_data=f"adm:edit:{app['id']}"))
    kb.add(InlineKeyboardButton("🔙 رجوع", callback_data="adm:back"))
    return kb

def _admin_edit_kb(app_id, hidden):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✏️ الاسم",       callback_data=f"adm:set:name:{app_id}"),
        InlineKeyboardButton("📝 الوصف القصير", callback_data=f"adm:set:short_desc:{app_id}"),
        InlineKeyboardButton("📖 الوصف الكامل", callback_data=f"adm:set:description:{app_id}"),
        InlineKeyboardButton("🔗 الرابط",       callback_data=f"adm:set:url:{app_id}"),
        InlineKeyboardButton("😀 الإيموجي",     callback_data=f"adm:set:emoji:{app_id}"),
        InlineKeyboardButton("🏷️ التصنيف",     callback_data=f"adm:set:tag:{app_id}"),
    )
    hide_lbl = "👁️ إظهار في المتجر" if hidden else "🙈 إخفاء من المتجر"
    kb.row(InlineKeyboardButton(hide_lbl, callback_data=f"adm:toggle:{app_id}"),
           InlineKeyboardButton("🗑️ حذف نهائي", callback_data=f"adm:delete:{app_id}"))
    kb.add(InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="adm:list"))
    return kb

@bot.callback_query_handler(func=lambda c: c.data.startswith("adm:"))
def cb_admin(call):
    uid   = call.from_user.id
    cid   = call.message.chat.id
    mid   = call.message.message_id
    parts = call.data.split(":")
    act   = parts[1]

    if uid not in ADMIN_USERS and act not in ("logout","back"):
        bot.answer_callback_query(call.id, "⛔ غير مصرح!"); return

    if act == "list":
        apps = load_apps()
        visible = sum(1 for a in apps if not a.get("hidden"))
        bot.edit_message_text(
            f"📋 <b>البوتات المسجلة:</b> {len(apps)} بوت | 🟢 {visible} ظاهر\n",
            cid, mid, reply_markup=_admin_list_kb(apps))

    elif act == "back":
        bot.edit_message_text("🛠️ <b>لوحة التحكم — متجر بودة</b>",
                              cid, mid, reply_markup=_admin_main_kb())

    elif act == "reload":
        apps    = load_apps()
        visible = sum(1 for a in apps if not a.get("hidden"))
        bot.answer_callback_query(call.id, f"✅ تم التحديث — {visible} بوت ظاهر")
        bot.edit_message_text(
            f"🔄 تم تحديث البيانات.\n🟢 <b>{visible}</b> بوت ظاهر من أصل {len(apps)}.",
            cid, mid, reply_markup=_admin_main_kb())

    elif act == "logout":
        ADMIN_USERS.discard(uid); edit_state.pop(uid, None)
        bot.edit_message_text("🚪 تم تسجيل الخروج بنجاح.", cid, mid)

    elif act == "edit" and len(parts) >= 3:
        app_id = parts[2]
        apps   = load_apps()
        app    = next((a for a in apps if a["id"] == app_id), None)
        if not app: bot.answer_callback_query(call.id,"؟"); return
        status  = "🔴 مخفي" if app.get("hidden") else "🟢 ظاهر"
        info = (f"{app.get('emoji','')} <b>{_esc(app.get('name',''))}</b>\n"
                f"─────\n"
                f"📝 <i>{_esc(app.get('short_desc',''))}</i>\n"
                f"🔗 <code>{_esc(app.get('url',''))}</code>\n"
                f"🏷️ {_esc(app.get('tag',''))}\n"
                f"حالة: {status}")
        bot.edit_message_text(info, cid, mid,
                              reply_markup=_admin_edit_kb(app_id, app.get("hidden",False)))

    elif act == "set" and len(parts) >= 4:
        field, app_id = parts[2], parts[3]
        edit_state[uid] = {"step":"set_field","app_id":app_id,"field":field}
        bot.answer_callback_query(call.id)
        field_names = {"name":"الاسم","short_desc":"الوصف القصير",
                       "description":"الوصف الكامل","url":"الرابط",
                       "emoji":"الإيموجي","tag":"التصنيف"}
        bot.send_message(cid, f"✏️ أرسل <b>{field_names.get(field,field)}</b> الجديد:",
                         reply_markup=ForceReply(selective=True))
        return

    elif act == "toggle" and len(parts) >= 3:
        app_id = parts[2]; apps = load_apps()
        for a in apps:
            if a["id"] == app_id:
                a["hidden"] = not a.get("hidden", False)
                save_apps(apps)
                status = "🔴 مخفي" if a["hidden"] else "🟢 ظاهر"
                bot.answer_callback_query(call.id, f"✅ {status}")
                info = (f"{a.get('emoji','')} <b>{_esc(a.get('name',''))}</b>\n"
                        f"الحالة الجديدة: {status}")
                bot.edit_message_text(info, cid, mid,
                                      reply_markup=_admin_edit_kb(app_id, a.get("hidden",False)))
                return

    elif act == "delete" and len(parts) >= 3:
        app_id = parts[2]
        apps   = [a for a in load_apps() if a["id"] != app_id]
        save_apps(apps)
        bot.answer_callback_query(call.id, "🗑️ تم الحذف النهائي")
        visible = sum(1 for a in apps if not a.get("hidden"))
        bot.edit_message_text(
            f"📋 <b>البوتات المسجلة:</b> {len(apps)} بوت | 🟢 {visible} ظاهر",
            cid, mid, reply_markup=_admin_list_kb(apps))
        return

    elif act == "add":
        edit_state[uid] = {"step":"add_id"}
        bot.answer_callback_query(call.id)
        bot.send_message(cid, "➕ أرسل <b>ID فريد</b> للبوت الجديد:\n"
                         "<i>مثال: <code>my_new_bot</code></i>",
                         reply_markup=ForceReply(selective=True))
        return

    bot.answer_callback_query(call.id)

# ── Text handler (admin input + password) ─────────
@bot.message_handler(func=lambda m: True, content_types=["text"])
def handle_text(message):
    uid  = message.from_user.id
    text = (message.text or "").strip()

    if uid in edit_state:
        _handle_admin_input(message, text)
        return

    if ADMIN_PASSWORD and text == ADMIN_PASSWORD:
        ADMIN_USERS.add(uid)
        bot.send_message(message.chat.id,
                         "✅ <b>مرحباً يا أدمن!</b>\n"
                         "أنت الآن في لوحة التحكم.",
                         reply_markup=_admin_main_kb())
        return

    # Default: show store
    cmd_start(message)

def _handle_admin_input(message, text):
    uid   = message.from_user.id
    state = edit_state[uid]
    step  = state.get("step")
    cid   = message.chat.id

    if step == "set_field":
        apps = load_apps()
        for a in apps:
            if a["id"] == state["app_id"]:
                a[state["field"]] = text
                save_apps(apps)
                del edit_state[uid]
                bot.send_message(cid, f"✅ تم التحديث بنجاح!",
                                 reply_markup=_admin_main_kb())
                return

    elif step == "add_id":
        apps = load_apps()
        if any(a["id"] == text for a in apps):
            bot.send_message(cid, "⚠️ هذا الـ ID موجود! اختر آخر:"); return
        edit_state[uid] = {"step":"add_name","data":{"id":text}}
        bot.send_message(cid, "أرسل <b>اسم البوت</b>:",
                         reply_markup=ForceReply(selective=True))

    elif step == "add_name":
        edit_state[uid]["data"]["name"] = text
        edit_state[uid]["step"] = "add_emoji"
        bot.send_message(cid, "أرسل <b>الإيموجي</b> (مثال: 🤖):",
                         reply_markup=ForceReply(selective=True))

    elif step == "add_emoji":
        edit_state[uid]["data"]["emoji"] = text
        edit_state[uid]["step"] = "add_desc"
        bot.send_message(cid, "أرسل <b>الوصف القصير</b>:",
                         reply_markup=ForceReply(selective=True))

    elif step == "add_desc":
        edit_state[uid]["data"]["short_desc"] = text
        edit_state[uid]["data"]["description"] = text
        edit_state[uid]["step"] = "add_url"
        bot.send_message(cid, "أرسل <b>رابط البوت</b> (https://t.me/...):",
                         reply_markup=ForceReply(selective=True))

    elif step == "add_url":
        data = edit_state[uid]["data"]
        data.update({"url": text, "tag": "مجاني", "hidden": False})
        apps = load_apps()
        apps.append(data)
        save_apps(apps)
        del edit_state[uid]
        bot.send_message(cid,
                         f"✅ <b>تمت إضافة {_esc(data.get('name',''))} بنجاح!</b>\n"
                         f"🟢 البوت ظاهر الآن في المتجر.",
                         reply_markup=_admin_main_kb())

# ── Entry ──────────────
if __name__ == "__main__":
    log.info("Boda Store Bot v5.0 starting...")
    log.info(f"Registry: {REGISTRY} | exists={os.path.exists(REGISTRY)}")
    apps    = load_apps()
    visible = [a for a in apps if not a.get("hidden")]
    log.info(f"Visible bots ({len(visible)}): {[a['name'] for a in visible]}")
    try:
        me = bot.get_me()
        log.info(f"Authenticated: @{me.username}")
    except Exception as e:
        log.error(f"Auth failed: {e}"); sys.exit(1)
    try:
        bot.delete_webhook(drop_pending_updates=True)
        time.sleep(2)  # Wait for Telegram to release previous session
        log.info("Polling started...")
        bot.infinity_polling(skip_pending=True, timeout=10,
                             long_polling_timeout=20,
                             allowed_updates=["message","callback_query","inline_query"])
    except Exception as e:
        log.error(f"Fatal: {e}"); raise
