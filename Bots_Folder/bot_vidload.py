"""
bot_vidload.py — VidLoad | محمّل الفيديوهات
@VidLoadXBot
"""
import time
import os, sys, re, tempfile, threading, logging
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils import is_subscribed, send_subscription_prompt
from bot_base import get_token

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO,
                    format="[VidLoad] %(asctime)s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("vidload")

TOKEN = get_token("BOT_VIDLOAD_TOKEN")
STORE_URL = "https://t.me/BodaStoreeBot"
FFMPEG    = r"C:\ffmpeg-7.1.1-essentials_build\bin"
MAX_BYTES = 45 * 1024 * 1024
URL_RE    = re.compile(r'https?://[^\s]+', re.IGNORECASE)

bot = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True)
_sessions: dict = {}

def format_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("🎬 تحميل فيديو", callback_data="vl_fmt:video"),
           InlineKeyboardButton("🎵 تحميل صوت", callback_data="vl_fmt:audio"))
    kb.add(InlineKeyboardButton("🏪  متجر تطبيقات Boda", url=STORE_URL))
    return kb

def app_kb():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("🏪  متجر تطبيقات Boda", url=STORE_URL))
    return kb
    pass

def fmt_size(b): return f"{b/1024/1024:.1f} MB" if b >= 1024*1024 else f"{b/1024:.0f} KB"
def fmt_dur(s):
    if not s: return "?"
    m, sec = divmod(int(s), 60); h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"

def _do_download(url: str, chat_id: int, wait_mid: int, audio_only=False):
    import yt_dlp
    with tempfile.TemporaryDirectory() as tmp:
        outtmpl = os.path.join(tmp, "file.%(ext)s")
        if audio_only:
            fmt  = "bestaudio/best"
            post = [{"key":"FFmpegExtractAudio","preferredcodec":"mp3","preferredquality":"192"}]
        else:
            fmt  = ("bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]"
                    "/bestvideo[height<=1080]+bestaudio/best[ext=mp4]/best")
            post = []
        opts = {
            "format": fmt, "outtmpl": outtmpl,
            "quiet": True, "no_warnings": True,
            "noplaylist": True,
            "ffmpeg_location": FFMPEG,
            "merge_output_format": "mp4" if not audio_only else None,
            "postprocessors": post,
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
            files = [f for f in os.listdir(tmp) if not f.endswith((".part", ".ytdl"))]
            if not files: raise FileNotFoundError("لم يُحمَّل أي ملف")
            path  = os.path.join(tmp, files[0])
            size  = os.path.getsize(path)
            title = (info.get("title") or "فيديو")[:60]
            dur   = fmt_dur(info.get("duration"))
            ext   = os.path.splitext(files[0])[1].lower()
            if size > MAX_BYTES:
                bot.edit_message_text(
                    f"⚠️ <b>الملف كبير جداً</b> ({fmt_size(size)})\n"
                    "جرّب رابطاً أقصر أو فيديو بجودة أقل.",
                    chat_id, wait_mid)
                return
            try: bot.delete_message(chat_id, wait_mid)
            except: pass
            cap = f"✅ <b>{title}</b>\n⏱️ {dur}  •  📦 {fmt_size(size)}"
            with open(path, "rb") as f:
                if audio_only or ext in (".mp3", ".m4a", ".ogg"):
                    bot.send_audio(chat_id, f, caption=cap, reply_markup=app_kb())
                else:
                    bot.send_video(chat_id, f, caption=cap,
                                   supports_streaming=True, reply_markup=app_kb())
            try:
                _sessions.pop(chat_id, None)
            except: pass
        except Exception as e:
            log.error(f"Download error: {e}")
            bot.edit_message_text(
                f"❌ <b>فشل التحميل</b>\n<code>{str(e)[:200]}</code>",
                chat_id, wait_mid)

@bot.message_handler(commands=["start", "help"])
def cmd_start(message):
    welcome_text = (
        "👋 <b>أهلاً في VidLoad!</b>\n\n"
        "حمّل فيديوهات من يوتيوب، تيك توك،\n"
        "إنستجرام، فيسبوك وأكثر!\n\n"
        "⬇️ <b>أرسل أي رابط لتحميله فوراً:</b>"
    )
    if not is_subscribed(bot, message.from_user.id):
        bot.send_message(message.chat.id, welcome_text, reply_markup=app_kb())
        send_subscription_prompt(bot, message.chat.id)
        return
    bot.send_message(message.chat.id, welcome_text, reply_markup=app_kb())

@bot.callback_query_handler(func=lambda c: c.data.startswith("vl_fmt:"))
def handle_format(call):
    fmt = call.data.split(":")[1]
    url = _sessions.get(call.from_user.id)
    if not url:
        bot.answer_callback_query(call.id, "⚠️ الجلسة انتهت! أرسل الرابط مجدداً.", show_alert=True)
        return
        
    audio_only = (fmt == "audio")
    bot.edit_message_text(f"⏳ <b>جاري بدء التحميل ({fmt})...</b>", call.message.chat.id, call.message.message_id)
    threading.Thread(target=_do_download,
        args=(url, call.message.chat.id, call.message.message_id, audio_only),
        daemon=True).start()

@bot.message_handler(func=lambda m: True)
def guide(message):
    if not is_subscribed(bot, message.from_user.id):
        send_subscription_prompt(bot, message.chat.id)
        return
    url_match = URL_RE.search(message.text or "")
    if url_match:
        url = url_match.group()
        _sessions[message.from_user.id] = url
        bot.send_message(message.chat.id, "🎬 <b>اختر صيغة التحميل:</b>", reply_markup=format_kb())
    else:
        bot.send_message(message.chat.id, "❌ <b>رابط غير صالح!</b> أرسل رابط فيديو صحيح.", reply_markup=app_kb())

if __name__ == "__main__":
    from bot_base import start_bot
    start_bot(bot, "vidload")
