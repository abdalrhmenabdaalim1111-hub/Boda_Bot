"""
dev_tools.py — أداة المطور والصيانة الشاملة لنظام Boda Bot System
توفر واجهة سطر أوامر قوية (CLI) لإدارة واختبار وصيانة المشروع.

الاستخدام:
    python dev_tools.py status             ← فحص شامل لحالة النظام، التوكنات، وقاعدة البيانات
    python dev_tools.py test               ← تشغيل كافة الاختبارات التلقائية (pytest)
    python dev_tools.py lint               ← فحص الأخطاء النحوية والـ Syntax في كل ملفات المشروع
    python dev_tools.py clean              ← تنظيف ملفات الكاش (pycache, pytest_cache, tmp)
    python dev_tools.py backup             ← إنشاء نسخة احتياطية مضغوطة فوراً
    python dev_tools.py health             ← فحص صحة وتكامل البوتات المسجلة
    python dev_tools.py new-bot <id> <name> [category] ← إنشاء وتوليد بوت جديد وتسجيله تلقائياً
"""
import os
import sys
import json
import shutil
import py_compile
import subprocess
from pathlib import Path
from datetime import datetime

BASE_DIR    = Path(__file__).parent.resolve()
BOTS_DIR    = BASE_DIR / "Bots_Folder"
DATA_DIR    = BASE_DIR / "Data"
LOGS_DIR    = BASE_DIR / "Logs"
REGISTRY    = BASE_DIR / "bots_registry.json"
ENV_FILE    = BASE_DIR / ".env"
CONFIG_FILE = BASE_DIR / "config.py"


def _colored(text: str, color_code: str) -> str:
    """إرجاع نص بألوان ANSI إذا كانت مدعومة"""
    return f"\033[{color_code}m{text}\033[0m"


def print_banner():
    banner = """
╔═══════════════════════════════════════════════════════════╗
║            🤖 BODA BOT SYSTEM — DEV TOOLS v4.5            ║
║              أداة المطور والصيانة الشاملة                ║
╚═══════════════════════════════════════════════════════════╝
"""
    print(banner)


def cmd_status() -> dict:
    """فحص شامل لحالة النظام والملفات وقاعدة البيانات"""
    print_banner()
    print("📊 [1/5] معلومات البيئة والنظام:")
    print(f"  • مسار المشروع: {BASE_DIR}")
    print(f"  • إصدار بايثون: {sys.version.split()[0]} ({sys.platform})")

    # فحص .env
    print("\n🔐 [2/5] حالة ملف الإعدادات (.env):")
    env_exists = ENV_FILE.exists()
    configured_tokens = 0
    total_tokens = 0
    if env_exists:
        try:
            with open(ENV_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        if "TOKEN" in k.upper():
                            total_tokens += 1
                            v_clean = v.strip().strip("'\"")
                            if v_clean and v_clean != "ضع_التوكن_هنا" and len(v_clean) > 15:
                                configured_tokens += 1
            print(f"  • ملف .env: موجود ✅")
            print(f"  • التوكنات المجهزة: {configured_tokens}/{total_tokens}")
        except Exception as e:
            print(f"  • خطأ في قراءة .env: {e}")
    else:
        print("  • ملف .env: غير موجود ❌ (يرجى نسخه من .env.example)")

    # فحص البوتات والـ Registry
    print("\n🤖 [3/5] سجل البوتات (Registry):")
    total_bots = 0
    categories = {}
    if REGISTRY.exists():
        try:
            with open(REGISTRY, "r", encoding="utf-8") as f:
                reg_data = json.load(f)
            bots = reg_data if isinstance(reg_data, list) else reg_data.get("bots", [])
            total_bots = len(bots)
            for b in bots:
                cat = b.get("category") or b.get("tag", "عام")
                categories[cat] = categories.get(cat, 0) + 1
            print(f"  • إجمالي البوتات المسجلة: {total_bots}")
            cat_str = ", ".join([f"{k}: {v}" for k, v in categories.items()])
            print(f"  • الفئات: {cat_str}")
        except Exception as e:
            print(f"  • خطأ في قراءة bots_registry.json: {e}")
    else:
        print("  • bots_registry.json غير موجود ❌")

    # فحص قاعدة البيانات SQLite
    print("\n🗄️ [4/5] قاعدة البيانات:")
    db_file = DATA_DIR / "boda_bots.db"
    db_info = {"exists": False, "users": 0, "size": 0}
    if db_file.exists():
        db_size_kb = db_file.stat().st_size / 1024
        db_info["exists"] = True
        db_info["size"] = db_size_kb
        try:
            sys.path.insert(0, str(BOTS_DIR))
            from database import get_db
            db = get_db()
            db_users = db.get_all_users_count()
            stats_list = db.get_stats_summary()
            total_msgs = sum(s.get("total_messages", 0) for s in stats_list)
            db_info["users"] = db_users
            print(f"  • حالة قاعدة البيانات: متصلة ✅ ({db_size_kb:.1f} KB)")
            print(f"  • إجمالي المستخدمين المسجلين: {db_users}")
            print(f"  • إجمالي الرسائل: {total_msgs}")
        except Exception as e:
            print(f"  • قاعدة البيانات موجودة ({db_size_kb:.1f} KB) لكن تعذر جلب الإحصائيات: {e}")
    else:
        print("  • قاعدة البيانات: لم تُنشأ بعد (سيتم إنشاؤها تلقائياً عند أول تشغيل)")

    # فحص النسخ الاحتياطية
    print("\n💾 [5/5] النسخ الاحتياطية:")
    import backup_manager
    backups = backup_manager.list_backups()
    print(f"  • عدد النسخ المحفوظة: {len(backups)}")
    if backups:
        print(f"  • أحدث نسخة: {backups[0].name}")

    print("\n" + "=" * 60)
    return {
        "env_exists": env_exists,
        "configured_tokens": configured_tokens,
        "total_bots": total_bots,
        "db_info": db_info,
        "backups_count": len(backups)
    }


def cmd_test(extra_args: list = None) -> int:
    """تشغيل جميع الاختبارات التلقائية"""
    print("🧪 جاري تشغيل الاختبارات التلقائية بواسطة pytest...")
    args = [sys.executable, "-m", "pytest"]
    if extra_args:
        args.extend(extra_args)
    else:
        args.extend(["-v"])
    res = subprocess.run(args, cwd=str(BASE_DIR))
    return res.returncode


def cmd_lint() -> int:
    """فحص بناء الجملة والأخطاء النحوية في كافة ملفات بايثون"""
    print("🔍 جاري فحص ملفات المشروع (Syntax Verification)...")
    errors = 0
    checked = 0

    scan_dirs = [BASE_DIR, BOTS_DIR, BASE_DIR / "ui", BASE_DIR / "tests"]
    for d in scan_dirs:
        if not d.exists():
            continue
        for py_file in d.glob("*.py"):
            checked += 1
            try:
                py_compile.compile(str(py_file), doraise=True)
            except py_compile.PyCompileError as e:
                print(f"  ❌ خطأ في {py_file.name}: {e.msg}")
                errors += 1

    if errors == 0:
        print(f"✅ فحص سليم! تم تدقيق {checked} ملف بدون أي أخطاء syntax.")
        return 0
    else:
        print(f"❌ تم العثور على {errors} أخطاء في الكود من أصل {checked} ملف.")
        return 1


def cmd_clean() -> int:
    """تنظيف ملفات الكاش والملفات المؤقتة"""
    print("🧹 جاري تنظيف مخلفات الكاش والملفات المؤقتة...")
    deleted_files = 0
    deleted_dirs = 0

    # حذف مجلدات الكاش
    for p in BASE_DIR.rglob("__pycache__"):
        if p.is_dir():
            try:
                shutil.rmtree(p)
                deleted_dirs += 1
            except Exception:
                pass

    for p in BASE_DIR.rglob(".pytest_cache"):
        if p.is_dir():
            try:
                shutil.rmtree(p)
                deleted_dirs += 1
            except Exception:
                pass

    # حذف الملفات المؤقتة
    for ext in ("*.pyc", "*.pyo", "*.tmp", "*-journal"):
        for f in BASE_DIR.rglob(ext):
            if f.is_file():
                try:
                    f.unlink()
                    deleted_files += 1
                except Exception:
                    pass

    print(f"✅ اكتمل التنظيف: تم حذف {deleted_dirs} مجلدات كاش و {deleted_files} ملفات مؤقتة.")
    return 0


def cmd_health() -> int:
    """فحص تكامل البوتات المسجلة في bots_registry.json وتأكيد وجود ملفاتها"""
    print("🏥 جاري فحص صحة وتكامل البوتات المسجلة...")
    if not REGISTRY.exists():
        print("❌ bots_registry.json غير موجود!")
        return 1

    with open(REGISTRY, "r", encoding="utf-8") as f:
        data = json.load(f)

    bots = data if isinstance(data, list) else data.get("bots", [])
    missing_files = []
    missing_tokens = []

    # قراءة .env
    env_content = ""
    if ENV_FILE.exists():
        env_content = ENV_FILE.read_text(encoding="utf-8")

    for b in bots:
        b_id = b.get("id")
        fname = b.get("file", f"bot_{b_id}.py")
        fpath = BOTS_DIR / fname
        if not fpath.exists():
            missing_files.append((b_id, fname))

        token_key = f"BOT_{b_id.upper()}_TOKEN"
        if token_key not in env_content:
            missing_tokens.append((b_id, token_key))

    print(f"  • تم فحص {len(bots)} بوت مسجل.")
    if missing_files:
        print(f"  ⚠️ هناك {len(missing_files)} ملفات بوت غير موجودة في Bots_Folder/:")
        for b_id, fname in missing_files:
            print(f"    - {b_id}: {fname}")
    else:
        print("  ✅ جميع ملفات البوتات المسجلة متوفرة على القرص.")

    if missing_tokens:
        print(f"  ℹ️ هناك {len(missing_tokens)} بوتات لا تملك مفتاح توكن في .env.")
    else:
        print("  ✅ جميع البوتات لها مفاتيح توكن في .env.")

    return 0 if not missing_files else 1


def cmd_new_bot(bot_id: str, bot_title: str, category: str = "أدوات") -> bool:
    """توليد قالب بوت جديد وتسجيله تلقائياً في السجل وملف الإعدادات"""
    bot_id = bot_id.lower().strip().replace(" ", "_").replace("-", "_")
    if bot_id.startswith("bot_"):
        bot_id = bot_id[4:]

    file_name = f"bot_{bot_id}.py"
    target_path = BOTS_DIR / file_name

    if target_path.exists():
        print(f"❌ الملف موجود مسبقاً: {file_name}")
        return False

    env_var_name = f"BOT_{bot_id.upper()}_TOKEN"

    code_template = f'''"""
{file_name} — {bot_title}
تم توليده تلقائياً عبر dev_tools
"""
import telebot
from bot_base import get_token, start_polling, track_user, record_error

BOT_NAME = "{bot_id}"
TOKEN = get_token("{env_var_name}")
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")


@bot.message_handler(commands=["start"])
def cmd_start(message):
    try:
        track_user(BOT_NAME, message.from_user.id,
                   message.from_user.full_name,
                   message.from_user.username or "")
        welcome_text = (
            "👋 <b>مرحباً بك في {bot_title}!</b>\\n\\n"
            "هذا البوت جاهز لخدمتك. اكتب /help للاطلاع على التعليمات."
        )
        bot.reply_to(message, welcome_text)
    except Exception as e:
        record_error(BOT_NAME, e, message.from_user.id)


@bot.message_handler(commands=["help"])
def cmd_help(message):
    bot.reply_to(message, "ℹ️ <b>قائمة الأوامر:</b>\\n/start — بدء التشغيل\\n/help — المساعدة")


@bot.message_handler(func=lambda m: True)
def handle_all_messages(message):
    try:
        track_user(BOT_NAME, message.from_user.id,
                   message.from_user.full_name,
                   message.from_user.username or "")
        bot.reply_to(message, f"📩 استلمت رسالتك: {{message.text}}")
    except Exception as e:
        record_error(BOT_NAME, e, message.from_user.id)


if __name__ == "__main__":
    start_polling(bot, BOT_NAME)
'''
    target_path.write_text(code_template, encoding="utf-8")
    print(f"✅ تم إنشاء كود البوت: {target_path.name}")

    # إضافة التوكن إلى .env إذا لم يكن موجوداً
    if ENV_FILE.exists():
        content = ENV_FILE.read_text(encoding="utf-8")
        if env_var_name not in content:
            with open(ENV_FILE, "a", encoding="utf-8") as f:
                f.write(f"\n{env_var_name}=ضع_التوكن_هنا\n")
            print(f"✅ تمت إضافة المتغير {env_var_name} إلى ملف .env")

    # تسجيل البوت في bots_registry.json
    if REGISTRY.exists():
        try:
            with open(REGISTRY, "r", encoding="utf-8") as f:
                registry = json.load(f)

            is_list = isinstance(registry, list)
            bots = registry if is_list else registry.get("bots", [])
            # التحقق إذا كان مسجلاً بالفعل
            if not any(b.get("id") == bot_id for b in bots):
                new_entry = {
                    "id": bot_id,
                    "name": bot_title,
                    "description": f"بوت {bot_title}",
                    "file": file_name,
                    "category": category,
                    "version": "1.0.0",
                    "created_at": datetime.now().strftime("%Y-%m-%d"),
                    "url": f"https://t.me/{bot_id}_bot",
                    "hidden": False
                }
                bots.append(new_entry)
                final_data = bots if is_list else registry
                with open(REGISTRY, "w", encoding="utf-8") as f:
                    json.dump(final_data, f, ensure_ascii=False, indent=2)
                print(f"✅ تم تسجيل البوت في bots_registry.json (الفئة: {category})")
        except Exception as e:
            print(f"⚠️ خطأ أثناء تحديث bots_registry.json: {e}")

    print(f"\n🎉 تم إنشاء بوت [{bot_title}] بنجاح! يمكنك الآن إضافة التوكن وتشغيله.")
    return True


def cmd_set_token(bot_id: str, token: str) -> bool:
    """إعداد أو تحديث توكن بوت معين مع الفحص التلقائي وجلب المعرف من تيليجرام"""
    import urllib.request
    bot_id = bot_id.lower().strip().replace("bot_", "")
    token = token.strip().strip("'\"")

    if not token or len(token) < 20 or ":" not in token:
        print("❌ تنسيق التوكن غير صالح! يجب أن يكون بالشكل 123456789:ABCDEF...")
        return False

    print(f"🔄 جاري التحقق من التوكن عبر خوادم تيليجرام...")
    verified_username = None
    bot_title = None

    try:
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/getMe")
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("ok"):
                result = data.get("result", {})
                verified_username = result.get("username")
                bot_title = result.get("first_name")
                print(f"  ✅ التوكن سليم! تم التعرف على: @{verified_username} ({bot_title})")
    except Exception as e:
        print(f"  ⚠️ تعذر الاتصال بتيليجرام للتحقق ({e})، سيتم حفظ التوكن محلياً.")

    # 1. تحديث أو إضافة التوكن في .env
    token_key = f"BOT_{bot_id.upper()}_TOKEN"
    env_lines = []
    found = False

    if ENV_FILE.exists():
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            env_lines = f.readlines()

    new_env_lines = []
    for line in env_lines:
        if line.strip().startswith(f"{token_key}=") or line.strip().startswith(f"BOT_{bot_id.upper()}="):
            new_env_lines.append(f"{token_key}={token}\n")
            found = True
        else:
            new_env_lines.append(line)

    if not found:
        new_env_lines.append(f"\n{token_key}={token}\n")

    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(new_env_lines)
    print(f"  ✅ تم حفظ التوكن في ملف .env: {token_key}")

    # 2. تحديث معرف البوت في bots_registry.json
    if REGISTRY.exists():
        try:
            with open(REGISTRY, "r", encoding="utf-8") as f:
                reg_data = json.load(f)

            is_list = isinstance(reg_data, list)
            bots = reg_data if is_list else reg_data.get("bots", [])

            for b in bots:
                if b.get("id") == bot_id or b.get("id") == f"bot_{bot_id}":
                    if verified_username:
                        b["username"] = f"@{verified_username}"
                        b["url"] = f"https://t.me/{verified_username}"
                    if bot_title and not b.get("name"):
                        b["name"] = bot_title
                    break

            with open(REGISTRY, "w", encoding="utf-8") as f:
                json.dump(reg_data, f, ensure_ascii=False, indent=2)
            print(f"  ✅ تم تحديث بيانات البوت في bots_registry.json")
        except Exception as e:
            print(f"  ⚠️ خطأ في تحديث السجل: {e}")

    print(f"\n🎉 تم تفعيل التوكن للبوت [{bot_id}] بنجاح! البوت جاهز للتشغيل الآن.")
    return True


def cmd_set_username(bot_id: str, username: str) -> bool:
    """تحديث معرف البوت (يوزر تيليجرام) في السجل"""
    bot_id = bot_id.lower().strip().replace("bot_", "")
    username = username.strip().lstrip("@")

    if not REGISTRY.exists():
        print("❌ bots_registry.json غير موجود!")
        return False

    with open(REGISTRY, "r", encoding="utf-8") as f:
        reg_data = json.load(f)

    is_list = isinstance(reg_data, list)
    bots = reg_data if is_list else reg_data.get("bots", [])
    found = False

    for b in bots:
        if b.get("id") == bot_id or b.get("id") == f"bot_{bot_id}":
            b["username"] = f"@{username}"
            b["url"] = f"https://t.me/{username}"
            found = True
            break

    if found:
        with open(REGISTRY, "w", encoding="utf-8") as f:
            json.dump(reg_data, f, ensure_ascii=False, indent=2)
        print(f"✅ تم تحديث معرف البوت [{bot_id}] إلى: @{username}")
        return True
    else:
        print(f"❌ لم يتم العثور على بوت بالمعرف: {bot_id}")
        return False


def cmd_list_bots():
    """عرض قائمة جدولية احترافية بجميع البوتات وحالة توكناتها ومعرفاتها"""
    print_banner()
    if not REGISTRY.exists():
        print("❌ bots_registry.json غير موجود!")
        return

    with open(REGISTRY, "r", encoding="utf-8") as f:
        reg_data = json.load(f)

    bots = reg_data if isinstance(reg_data, list) else reg_data.get("bots", [])

    env_content = ""
    if ENV_FILE.exists():
        env_content = ENV_FILE.read_text(encoding="utf-8")

    print(f"{'#':<3} | {'المعرف (ID)':<15} | {'يوزر تيليجرام':<22} | {'الحالة':<10} | {'اسم البوت'}")
    print("─" * 75)

    for i, b in enumerate(bots, start=1):
        bid = b.get("id")
        user = b.get("username", "غير محدد")
        title = b.get("name", "")
        token_key = f"BOT_{bid.upper()}_TOKEN"
        has_token = f"{token_key}=" in env_content and f"{token_key}=ضع_التوكن_هنا" not in env_content
        status_icon = "🟢 جاهز" if has_token else "🟡 ينتظر"
        print(f"{i:<3} | {bid:<15} | {user:<22} | {status_icon:<10} | {title}")

    print("─" * 75)
    print(f"إجمالي البوتات: {len(bots)}")


def cmd_interactive_menu():
    """لوحة تحكم تفاعلية للمطور لإدارة البوتات دون الحاجة لكتابة أوامر كل مرة"""
    while True:
        print_banner()
        print("📌 القائمة التفاعلية لإدارة النظام:")
        print("  [1] 📋 استعراض جدول البوتات وحالة التوكنات")
        print("  [2] 🔑 إدخال أو تحديث توكن بوت والتحقق منه فوراً")
        print("  [3] 🏷️ تحديث معرف (يوزر) البوت في السجل")
        print("  [4] ➕ إنشاء وتوليد بوت جديد في ثوانٍ")
        print("  [5] 📊 فحص شامل لحالة النظام وقاعدة البيانات")
        print("  [6] 🏥 فحص صحة وتكامل ملفات البوتات على القرص")
        print("  [7] 🧪 تشغيل الاختبارات التلقائية (pytest)")
        print("  [8] 💾 إنشاء نسخة احتياطية مضغوطة (ZIP)")
        print("  [9] 🧹 تنظيف الكاش والملفات المؤقتة")
        print("  [0] 🚪 خروج")
        print("─" * 60)

        try:
            choice = input("👉 اختر رقم العملية (0-9): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 إلى اللقاء!")
            break

        if choice == "1":
            cmd_list_bots()
        elif choice == "2":
            bid = input("🔹 أدخل معرّف البوت (مثال: currency أو fitcheck): ").strip()
            tok = input("🔹 الصق توكن البوت من @BotFather: ").strip()
            if bid and tok:
                cmd_set_token(bid, tok)
            else:
                print("❌ لم يتم إدخال المعرف أو التوكن!")
        elif choice == "3":
            bid = input("🔹 أدخل معرّف البوت (ID): ").strip()
            usr = input("🔹 أدخل اليوزر الجديد (مثال: @MyNewBot): ").strip()
            if bid and usr:
                cmd_set_username(bid, usr)
        elif choice == "4":
            bid = input("🔹 معرّف البوت الجديد (ID بالإنجليزية): ").strip()
            title = input("🔹 اسم البوت بالعربي: ").strip()
            cat = input("🔹 التصنيف (أدوات/ترفيه/تحميل/ترجمة/صحة): ").strip() or "أدوات"
            if bid and title:
                cmd_new_bot(bid, title, cat)
                ask_tok = input("🔹 هل تريد إضافة التوكن الآن؟ (y/n): ").strip().lower()
                if ask_tok == "y":
                    tok = input("🔹 الصق التوكن: ").strip()
                    if tok:
                        cmd_set_token(bid, tok)
        elif choice == "5":
            cmd_status()
        elif choice == "6":
            cmd_health()
        elif choice == "7":
            cmd_test()
        elif choice == "8":
            import backup_manager
            backup_manager.create_backup(compress=True)
        elif choice == "9":
            cmd_clean()
        elif choice == "0":
            print("👋 تم إنهاء الأداة بنجاح.")
            break
        else:
            print("❌ خيار غير صالح!")

        try:
            input("\nاضغط Enter للمتابعة...")
        except (EOFError, KeyboardInterrupt):
            break


def main():
    if len(sys.argv) < 2:
        if sys.stdin.isatty():
            cmd_interactive_menu()
            return

        print_banner()
        print("الخيارات المتاحة:")
        print("  menu                         - فتح اللوحة التفاعلية لإدارة البوتات")
        print("  status                       - عرض تقرير شامل لحالة النظام")
        print("  list-bots                    - جدول بجميع البوتات ومعرفاتها وحالة توكناتها")
        print("  set-token <id> <token>       - إعداد توكن البوت والتحقق منه تلقائياً")
        print("  set-username <id> <username> - تحديث يوزر البوت في السجل")
        print("  test [args...]               - تشغيل الاختبارات التلقائية")
        print("  lint                         - فحص ملفات بايثون للتأكد من خلوها من الأخطاء")
        print("  clean                        - مسح ملفات الكاش والملفات المؤقتة")
        print("  health                       - فحص صحة وتكامل البوتات المسجلة")
        print("  backup [--no-zip]            - إنشاء نسخة احتياطية فورية")
        print("  new-bot <id> <name> [cat]    - توليد قالب بوت جديد")
        return

    cmd = sys.argv[1].lower()

    if cmd == "menu":
        cmd_interactive_menu()
    elif cmd == "status":
        cmd_status()
    elif cmd in ("list-bots", "list", "bots"):
        cmd_list_bots()
    elif cmd == "set-token":
        if len(sys.argv) < 4:
            print("❌ الاستخدام: python dev_tools.py set-token <bot_id> <token>")
            sys.exit(1)
        cmd_set_token(sys.argv[2], sys.argv[3])
    elif cmd == "set-username":
        if len(sys.argv) < 4:
            print("❌ الاستخدام: python dev_tools.py set-username <bot_id> <username>")
            sys.exit(1)
        cmd_set_username(sys.argv[2], sys.argv[3])
    elif cmd == "test":
        sys.exit(cmd_test(sys.argv[2:]))
    elif cmd == "lint":
        sys.exit(cmd_lint())
    elif cmd == "clean":
        sys.exit(cmd_clean())
    elif cmd == "health":
        sys.exit(cmd_health())
    elif cmd == "backup":
        import backup_manager
        compress = "--no-zip" not in sys.argv
        p = backup_manager.create_backup(compress=compress)
        print(f"✅ تم النسخ الاحتياطي: {p.name}")
    elif cmd == "new-bot":
        if len(sys.argv) < 4:
            print("❌ الاستخدام: python dev_tools.py new-bot <bot_id> <bot_name> [category]")
            sys.exit(1)
        b_id = sys.argv[2]
        b_name = sys.argv[3]
        cat = sys.argv[4] if len(sys.argv) > 4 else "أدوات"
        cmd_new_bot(b_id, b_name, cat)
    else:
        print(f"❌ أمر غير معروف: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
