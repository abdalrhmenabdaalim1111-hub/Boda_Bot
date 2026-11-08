"""
bot_memoryvault.py — MemoryVault | بوت الذكريات والملاحظات
الاسم العربي: بوت الذكريات
English Name: MemoryVault
Username: @MemoryVaultXBot
الوصف: احفظ ملاحظاتك وأفكارك المهمة وادرس قائمتك في أي وقت. خزّان ذاكرتك الرقمي!

TOKEN = "ضع_التوكن_هنا"
"""
import sys, logging, json, os
from datetime import datetime
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="[MemoryVault] %(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("memoryvault")

TOKEN     = "ضع_التوكن_هنا"
STORE_URL = "https://t.me/BodaStoreeBot"
BOT_NAME  = "بوت الذكريات"
bot       = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True)

# Storage — in-memory (resets on restart; for persistence use a JSON file)
_VAULT_FILE = os.path.join(os.path.dirname(__file__), "memoryvault_data.json")
vault: dict[str, list] = {}

def _save():
    try:
        with open(_VAULT_FILE, "w", encoding="utf-8") as f:
            json.dump(vault, f, ensure_ascii=False, indent=2)
    except: pass

def _load():
    global vault
    try:
        if os.path.exists(_VAULT_FILE):
            with open(_VAULT_FILE, encoding="utf-8") as f:
                vault = json.load(f)
    except: vault = {}

_load()

def get_notes(uid: str) -> list:
    return vault.get(str(uid), [])

def add_note(uid: str, text: str):
    key = str(uid)
    if key not in vault: vault[key] = []
    vault[key].append({"text": text, "date": datetime.now().strftime("%Y-%m-%d %H:%M")})
    if len(vault[key]) > 50: vault[key] = vault[key][-50:]
    _save()

def delete_note(uid: str, index: int):
    key = str(uid)
    if key in vault and 0 <= index < len(vault[key]):
        vault[key].pop(index)
        _save()

def home_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📋 عرض الملاحظات", callback_data="mv:list"),
        InlineKeyboardButton("➕ إضافة ملاحظة",  callback_data="mv:add"),
        InlineKeyboardButton("🗑 حذف الكل",       callback_data="mv:clear"),
        InlineKeyboardButton("🏪 متجر Boda",      url=STORE_URL),
    )
    return kb

def notes_kb(uid):
    notes = get_notes(str(uid))
    kb    = InlineKeyboardMarkup(row_width=1)
    for i, n in enumerate(notes[:20]):
        short = n["text"][:30] + ("..." if len(n["text"]) > 30 else "")
        kb.add(InlineKeyboardButton(f"🗑 {i+1}. {short}", callback_data=f"mv:del:{i}"))
    kb.add(
        InlineKeyboardButton("➕ إضافة جديدة", callback_data="mv:add"),
        InlineKeyboardButton("🏠 رجوع",         callback_data="mv:home"),
        InlineKeyboardButton("🏪 متجر Boda",    url=STORE_URL),
    )
    return kb

user_mode = {}  # uid → "adding"

@bot.message_handler(commands=["start", "help"])
def cmd_start(msg):
    uid = msg.from_user.id
    user_mode.pop(uid, None)
    count = len(get_notes(str(uid)))
    bot.send_message(msg.chat.id,
        f"📔 <b>أهلاً في {BOT_NAME}!</b>\n\n"
        f"خزّن ملاحظاتك وأفكارك المهمة في مكان آمن!\n\n"
        f"📊 لديك <b>{count}</b> ملاحظة محفوظة.\n\n"
        "👇 <b>اختر ما تريد:</b>",
        reply_markup=home_kb())

@bot.callback_query_handler(func=lambda c: c.data.startswith("mv:"))
def handle_mv(call):
    uid      = call.from_user.id
    parts    = call.data.split(":")
    act      = parts[1]
    cid, mid = call.message.chat.id, call.message.message_id
    bot.answer_callback_query(call.id)

    if act == "home":
        count = len(get_notes(str(uid)))
        user_mode.pop(uid, None)
        bot.edit_message_text(
            f"📔 <b>{BOT_NAME}</b>\n\n📊 لديك <b>{count}</b> ملاحظة.\n\n👇 اختر:",
            cid, mid, reply_markup=home_kb())

    elif act == "list":
        notes = get_notes(str(uid))
        if not notes:
            bot.edit_message_text(
                "📭 <b>لا توجد ملاحظات بعد!</b>\n\nاضغط ➕ لإضافة أول ملاحظة.",
                cid, mid, reply_markup=home_kb())
            return
        lines = [f"📔 <b>ملاحظاتك ({len(notes)}):</b>\n━━━━━━━━━━━━━━"]
        for i, n in enumerate(notes, 1):
            lines.append(f"\n<b>{i}.</b> {n['text']}\n     <i>🕐 {n['date']}</i>")
        bot.edit_message_text("\n".join(lines)[:4000], cid, mid, reply_markup=notes_kb(uid))

    elif act == "add":
        user_mode[uid] = "adding"
        bot.edit_message_text(
            "✏️ <b>أرسل الملاحظة التي تريد حفظها:</b>\n\n"
            "<i>يمكنك إرسال أي نص — أفكار، مهام، معلومات...</i>",
            cid, mid, reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("❌ إلغاء", callback_data="mv:home")))

    elif act == "del" and len(parts) > 2:
        index = int(parts[2])
        notes = get_notes(str(uid))
        if 0 <= index < len(notes):
            deleted = notes[index]["text"][:30]
            delete_note(str(uid), index)
            bot.answer_callback_query(call.id, f"تم حذف: {deleted}...", show_alert=True)
            notes2 = get_notes(str(uid))
            if not notes2:
                bot.edit_message_text("📭 القائمة فارغة الآن.", cid, mid, reply_markup=home_kb())
            else:
                bot.edit_message_text(
                    f"📔 <b>ملاحظاتك ({len(notes2)}):</b>",
                    cid, mid, reply_markup=notes_kb(uid))

    elif act == "clear":
        vault.pop(str(uid), None); _save()
        bot.edit_message_text("🗑 <b>تم حذف جميع ملاحظاتك!</b>", cid, mid, reply_markup=home_kb())

@bot.message_handler(func=lambda m: True)
def handle_text(msg):
    uid  = msg.from_user.id
    mode = user_mode.get(uid, "")
    if mode == "adding":
        text = (msg.text or "").strip()
        if text:
            add_note(str(uid), text)
            user_mode.pop(uid, None)
            count = len(get_notes(str(uid)))
            bot.reply_to(msg,
                f"✅ <b>تم حفظ ملاحظتك!</b>\n\n"
                f"📊 إجمالي الملاحظات: <b>{count}</b>",
                reply_markup=home_kb())
        else:
            bot.reply_to(msg, "⚠️ الملاحظة فارغة! أرسل نصاً.")
    else:
        cmd_start(msg)

if __name__ == "__main__":
    log.info(f"🚀 {BOT_NAME} starting...")
    bot.delete_webhook(drop_pending_updates=True)
    bot.infinity_polling(skip_pending=True, timeout=10, long_polling_timeout=20,
                         allowed_updates=["message", "callback_query"])
