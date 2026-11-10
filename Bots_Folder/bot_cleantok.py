"""
bot_cleantok.py — CleanTok Bot | تيك توك بدون علامة مائية — تحميل فوري
التوكن يُقرأ من .env عبر get_token("BOT_CLEANTOK_TOKEN")
@CleanTokVidBot
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
                    format="[CleanTok] %(asctime)s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("cleantok")

TOKEN = get_token("BOT_CLEANTOK_TOKEN")
STORE_URL = "https://t.me/BodaStoreeBot"
FFMPEG    = r"C:\ffmpeg-7.1.1-essentials_build\bin"
MAX_BYTES = 45 * 1024 * 1024
URL_RE    = re.compile(r'https?://[^\s]+', re.IGNORECASE)

bot = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True)
_sessions: dict = {}   # uid → url

def fmt_size(b: int) -> str:
    return f"{b/1024/1024:.1f} MB" if b >= 1024*1024 else f"{b/1024:.0f} KB"

def fmt_dur(s) -> str:
    if not s: return "?"
    m, sec = divmod(int(s), 60)
    return f"{m}:{sec:02d}"

def after_video_kb():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("🎵  تحميل الصوت MP3", callback_data="ct:audio"))
    kb.add(InlineKeyboardButton("🏪  متجر تطبيقات Boda", url=STORE_URL))
    return kb

def app_kb():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("🏪  متجر تطبيقات Boda", url=STORE_URL))
    return kb

def _do_download(url: str, chat_id: int, wait_mid: int, audio_only=False):
    import yt_dlp
    with tempfile.TemporaryDirectory() as tmp:
        outtmpl = os.path.join(tmp, "file.%(ext)s")

        if audio_only:
            fmt  = "bestaudio/best"
            post = [{"key": "FFmpegExtractAudio",
                     "preferredcodec": "mp3", "preferredquality": "192"}]
        else:
            fmt  = ("bestvideo[ext=mp4]+bestaudio[ext=m4a]"
                    "/bestvideo+bestaudio/best[ext=mp4]/best")
            post = []

        opts = {
            "format": fmt,
            "outtmpl": outtmpl,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "ffmpeg_location": FFMPEG,
            "merge_output_format": "mp4" if not audio_only else None,
            "postprocessors": post,
            "extractor_args": {
                "tiktok": {"webpage_download": ["1"]}
            },
        }

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)

            files = [f for f in os.listdir(tmp)
                     if not f.endswith((".part", ".ytdl"))]
            if not files:
                raise FileNotFoundError("لم يُحمَّل أي ملف")

            path   = os.path.join(tmp, files[0])
            size   = os.path.getsize(path)
            title  = (info.get("description") or info.get("title") or "فيديو")[:80]
            author = info.get("uploader") or info.get("creator") or ""
            dur    = fmt_dur(info.get("duration"))
            likes  = info.get("like_count") or 0
            ext    = os.path.splitext(files[0])[1].lower()

            if size > MAX_BYTES:
                bot.edit_message_text(
                    f"⚠️ الفيديو كبير جداً ({fmt_size(size)}) — يتجاوز 45 MB",
                    chat_id, wait_mid)
                return

            try: bot.delete_message(chat_id, wait_mid)
            except: pass

            if audio_only or ext in (".mp3", ".m4a"):
                cap = f"🎵 <b>{title[:60]}</b>\n📦 {fmt_size(size)}\n\n<b>بواسطة:</b> متجر تطبيقات Boda 🏪"
                with open(path, "rb") as f:
                    bot.send_audio(chat_id, f, caption=cap, reply_markup=app_kb())
            else:
                cap = (f"✅ <b>بدون علامة مائية!</b>\n"
                       f"📝 {title[:60]}\n"
                       f"👤 {author}  |  ⏱️ {dur}  |  ❤️ {likes:,}\n"
                       f"📦 {fmt_size(size)}\n\n<b>بواسطة:</b> متجر تطبيقات Boda 🏪")
                with open(path, "rb") as f:
                    bot.send_video(chat_id, f, caption=cap,
                                   supports_streaming=True,
                                   reply_markup=after_video_kb())

        except Exception as e:
            log.error(f"Download error: {e}")
            bot.edit_message_text(
                f"❌ <b>فشل التحميل</b>\n<code>{str(e)[:250]}</code>",
                chat_id, wait_mid)

@bot.message_handler(commands=["start", "help"])
def cmd_start(message):
    welcome_text = (
        "📱 <b>CleanTok Bot</b>\n"
        "<i>تيك توك بدون علامة مائية — تحميل فوري!</i>\n"
        "───────────────────────\n\n"
        "🔗 <b>أرسل رابط تيك توك للتحميل:</b>"
    )
    if not is_subscribed(bot, message.from_user.id):
        bot.send_message(message.chat.id, welcome_text, reply_markup=app_kb())
        send_subscription_prompt(bot, message.chat.id)
        return
    bot.send_message(message.chat.id, welcome_text, reply_markup=app_kb())

@bot.callback_query_handler(func=lambda c: c.data == "ct:audio")
def handle_audio(call):
    uid = call.from_user.id
    url = _sessions.get(uid)
    if not url:
        bot.answer_callback_query(call.id, "⚠️ الجلسة انتهت! أرسل الرابط مجدداً.")
        return
    bot.answer_callback_query(call.id, "⏳ جاري استخراج الصوت...")
    wait = bot.send_message(call.message.chat.id,
                            "🎵 <b>جاري استخراج الصوت...</b>")
    threading.Thread(
        target=_do_download,
        args=(url, call.message.chat.id, wait.message_id, True),
        daemon=True
    ).start()

@bot.message_handler(func=lambda m: True)
def handle_other(message):
    if not is_subscribed(bot, message.from_user.id):
        send_subscription_prompt(bot, message.chat.id)
        return
    url_match = URL_RE.search(message.text or "")
    if url_match:
        url = url_match.group()
        _sessions[message.from_user.id] = url
        wait = bot.send_message(message.chat.id, "⬇️ <b>جاري التحميل...</b>")
        threading.Thread(target=_do_download, args=(url, message.chat.id, wait.message_id, False), daemon=True).start()
    else:
        bot.send_message(message.chat.id, "❌ <b>الرابط غير صالح!</b>\nأرسل رابط فيديو تيك توك.")

if __name__ == "__main__":
    from bot_base import start_bot
    start_bot(bot, "cleantok")
