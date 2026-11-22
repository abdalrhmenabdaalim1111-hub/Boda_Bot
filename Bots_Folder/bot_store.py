# -*- coding: utf-8 -*-
import telebot
from telebot import types
import json
from Bots_Folder.bot_base import get_token, start_bot
from Bots_Folder.gate_middleware import GateMiddleware

# إعداد البوت
TOKEN = get_token("BOT_STORE_TOKEN")
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
gate = GateMiddleware(bot, "store")

# تحميل قائمة البوتات
with open("bots_registry.json", "r", encoding="utf-8") as f:
    BOTS = json.load(f)

def get_categories():
    cats = sorted(list(set(b["category"] for b in BOTS if b["category"])))
    return cats

@bot.message_handler(commands=['start'])
def send_welcome(message):
    # فحص الاشتراك الإجباري
    if gate.check_and_show_gate(message):
        return
        
    welcome_text = (
        "🏪 <b>أهلاً بك في متجر تطبيقات بودة (Boda Store)</b>\n\n"
        "أكثر من 34 بوت وتطبيق مصغر في مكان واحد!\n"
        "اختر الفئة التي تهمك واستكشف الأدوات الذكية."
    )
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    for cat in get_categories():
        markup.add(types.InlineKeyboardButton(f"📂 {cat}", callback_data=f"cat_{cat}"))
    
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("cat_"))
def show_category(call):
    cat = call.data.split("_")[1]
    filtered = [b for b in BOTS if b["category"] == cat]
    
    text = f"📂 فئة: <b>{cat}</b>\n\nاختر البوت لبدء الاستخدام:"
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    for b in filtered:
        markup.add(types.InlineKeyboardButton(f"{b['emoji']} {b['name']}", url=b['url']))
    
    markup.add(types.InlineKeyboardButton("🔙 العودة للمتجر", callback_data="back_main"))
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "back_main")
def back_main(call):
    send_welcome(call.message)

@bot.callback_query_handler(func=lambda call: call.data.startswith("gate_verify:"))
def verify_sub(call):
    gate.handle_verify_callback(call)

def register_handlers(bot_instance):
    # لا حاجة لشيء هنا لأننا نستخدم bot مباشرة
    pass

if __name__ == "__main__":
    start_bot(bot, "store")
