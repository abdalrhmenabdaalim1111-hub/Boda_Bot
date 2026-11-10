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
    python dev_tools.py tokens             ← جدول حالة التوكنات + اليوزرنيم المخطط لكل بوت
    python dev_tools.py import-tokens [file] ← إدخال توكنات بالجملة (new_tokens.txt أو stdin) مع فحص getMe
    python dev_tools.py tokens-verify      ← فحص صلاحية كل التوكنات الحالية عبر تيليجرام
"""
import os
import re
import sys
import json
import shutil
import py_compile
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

# حماية الترميز على Windows (cp1252 يفشل مع الإيموجي في المخرجات)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR    = Path(__file__).parent.resolve()
BOTS_DIR    = BASE_DIR / "Bots_Folder"
if str(BOTS_DIR) not in sys.path:
    sys.path.insert(0, str(BOTS_DIR))
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
    db_file = DATA_DIR / "boda_bot.db"
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


def cmd_bots_check() -> int:
    """فحص جودة شامل لكل البوتات (7 فحوصات لكل بوت) — بلا إنترنت ومناسب لـ CI

    الفحوصات: الملف | الصياغة | النظام الموحد | التوكن | السجل | صفحة الويب | تطبيق تيليجرام
    لا يطبع التوكنات أبداً ويعيد 0 فقط إذا نجحت كل الفحوصات.
    """
    import ast

    print("🔬 فحص الجودة الشامل — 7 فحوصات لكل بوت...")
    if not REGISTRY.exists():
        print("❌ bots_registry.json غير موجود!")
        return 1

    with open(REGISTRY, "r", encoding="utf-8") as f:
        data = json.load(f)
    bots = data if isinstance(data, list) else data.get("bots", [])

    # قراءة .env يدوياً (فحص فقط — لا تُطبع القيم أبداً)
    env_lines: Dict[str, str] = {}
    if ENV_FILE.exists():
        for ln in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if "=" in ln and not ln.strip().startswith("#"):
                k, _, v = ln.partition("=")
                env_lines[k.strip()] = v.strip()

    webroot = BASE_DIR / "webroot"
    checks = ["ملف", "صياغة", "نظام_موحد", "توكن", "سجل", "صفحة", "web.app"]
    token_re = re.compile(r"^\d{5,}:[\w-]{20,}$")
    problems: List[Tuple[str, str]] = []
    rows: List[Tuple[str, List[bool]]] = []

    for b in bots:
        b_id = str(b.get("id") or "?")
        fname = b.get("file", f"bot_{b_id}.py")
        fpath = BOTS_DIR / fname
        src = ""

        # 1) الملف موجود ومقروء بترميز UTF-8
        exists = fpath.exists()
        if exists:
            try:
                src = fpath.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                problems.append((b_id, f"الملف {fname} بترميز غير UTF-8"))
        else:
            problems.append((b_id, f"ملف البوت مفقود: {fname}"))
        row = [exists]

        # 2) الصياغة سليمة (تحليل ast — دون تنفيذ أي كود)
        syntax_ok = False
        if src:
            try:
                ast.parse(src, filename=str(fpath))
                syntax_ok = True
            except SyntaxError as e:
                problems.append((b_id, f"خطأ صياغة {fname} سطر {getattr(e, 'lineno', '?')}"))
        row.append(bool(src) and syntax_ok)

        # 3) يتبع النظام الموحد (get_token / start_bot / unified_middleware)
        unified_ok = bool(src) and ("get_token" in src or "start_bot" in src
                                    or "unified_middleware" in src)
        if src and not unified_ok:
            problems.append((b_id, "لا يستخدم النظام الموحد (get_token/start_bot)"))
        row.append(unified_ok)

        # 4) التوكن موجود بصيغة تيليجرام الصحيحة داخل .env (لا يُطبع)
        token_key = f"BOT_{b_id.upper()}_TOKEN"
        token_ok = bool(token_re.match(env_lines.get(token_key, "")))
        if not token_ok:
            problems.append((b_id, f"توكن مفقود أو بصيغة خاطئة ({token_key}) في .env"))
        row.append(token_ok)

        # 5) السجل مكتمل (اسم + يوزرنيم)
        reg_ok = bool(b.get("name")) and bool(b.get("username"))
        if not reg_ok:
            problems.append((b_id, "سجل ناقص: name أو username فارغ"))
        row.append(reg_ok)

        # 6) صفحة الويب موجودة في webroot
        page = webroot / b_id / "index.html"
        page_ok = page.exists()
        if not page_ok:
            problems.append((b_id, f"صفحة العرض مفقودة: webroot/{b_id}/index.html"))
        row.append(page_ok)

        # 7) الصفحة تطبيق تيليجرام حقيقي (سكربت telegram-web-app.js)
        webapp_ok = False
        if page_ok:
            try:
                webapp_ok = "telegram.org/js/telegram-web-app.js" in page.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                pass
        if page_ok and not webapp_ok:
            problems.append((b_id, "الصفحة لا تحمّل telegram-web-app.js"))
        row.append(webapp_ok)

        rows.append((b_id, row))

    # الطباعة: مصفوفة علامات لكل بوت + نسبة الجودة
    header = "  " + f"{'البوت':<24}" + " | ".join(checks) + " | النتيجة"
    print(header)
    print("  " + "-" * max(len(header) - 2, 40))
    total = 0
    passed = 0
    for b_id, row in rows:
        marks = " ".join("✅" if ok else "❌" for ok in row)
        n_ok = sum(1 for ok in row if ok)
        total += len(row)
        passed += n_ok
        print(f"  {b_id:<24} {marks}  {n_ok}/{len(row)}")

    perfect = sum(1 for _, row in rows if all(row))
    pct = int(100 * passed / total) if total else 0
    print()
    print(f"📊 الجودة الإجمالية: {passed}/{total} فحص ناجح ({pct}%)  ·  بوتات مثالية: {perfect}/{len(rows)}")
    if problems:
        print(f"\n⚠️ تفاصيل الملاحظات (أول {min(len(problems), 30)}):")
        for bid, msg in problems[:30]:
            print(f"   - {bid}: {msg}")
    if rows and passed == total:
        print("✅ جودة ممتازة — كل الفحوصات ناجحة")
        return 0
    print("❌ فشل فحص الجودة — عالج الملاحظات أعلاه")
    return 1


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


# ── أدوات مساعدة للتعامل مع التوكنات بالجملة ──────────────────────────────────

# نمط توكن تيليجرام القياسي: 123456789:AAHxxx...
_TOKEN_RE = re.compile(r"(\d{6,}:[A-Za-z0-9_-]{15,})")
_USERNAME_RE = re.compile(r"@([A-Za-z0-9_]{4,})")
_PLACEHOLDER = "ضع_التوكن_هنا"


def _is_token_format(value: str) -> bool:
    """التأكد أن القيمة تبدو توكن تيليجرام صالح الشكل"""
    v = (value or "").strip().strip("'\"")
    return bool(v) and v != _PLACEHOLDER and ":" in v and len(v) > 20


def _load_registry_bots() -> list:
    """قراءة قائمة البوتات من bots_registry.json (قائمة أو dict.bots)"""
    if not REGISTRY.exists():
        return []
    try:
        with open(REGISTRY, "r", encoding="utf-8") as f:
            reg_data = json.load(f)
        return reg_data if isinstance(reg_data, list) else reg_data.get("bots", [])
    except Exception:
        return []


def _read_env_tokens() -> dict:
    """قراءة كل توكنات البوتات الفعّالة من .env بصيغة {BOT_X_TOKEN: token}"""
    tokens = {}
    if not ENV_FILE.exists():
        return tokens
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip("'\"")
        if k.upper().startswith("BOT_") and k.upper().endswith("_TOKEN") and _is_token_format(v):
            tokens[k] = v
    return tokens


def _verify_token_telegram(token: str, timeout: int = 8):
    """التحقق من التوكن عبر getMe — يعيد (ok, username, title)"""
    import urllib.request
    try:
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/getMe")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("ok"):
                result = data.get("result", {})
                return True, result.get("username"), result.get("first_name")
    except Exception:
        pass
    return False, None, None


def parse_token_entries(text: str, known_ids=None, username_map=None) -> list:
    """
    تحويل نص أسطر إلى قائمة (bot_id أو None, token أو None, السطر الأصلي).

    الصيغ المدعومة لكل سطر:
        @CryptoRateXBot 123456:ABC...        ← يوزرنيم + توكن
        BOT_CRYPTORATE_TOKEN=123456:ABC...   ← مفتاح env كامل
        cryptorate=123456:ABC...             ← معرف البوت مباشرة
        123456:ABC...                        ← توكن مجرد (يُعرَّف لاحقاً عبر getMe)
    """
    known_ids = known_ids or set()
    username_map = username_map or {}
    entries = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        m = _TOKEN_RE.search(line)
        if not m:
            entries.append((None, None, line))
            continue

        token = m.group(1)
        bot_id = None

        # صيغة key=value
        kv = re.match(r"^([A-Za-z0-9_]+)\s*=", line)
        if kv:
            key = kv.group(1)
            key_upper = key.upper()
            if key_upper.startswith("BOT_") and key_upper.endswith("_TOKEN"):
                bot_id = key[4:-6].lower()
            elif key.lower() in known_ids:
                bot_id = key.lower()
        else:
            # صيغة @username token
            rest = line.replace(token, " ", 1)
            um = _USERNAME_RE.search(rest)
            if um:
                bot_id = username_map.get(um.group(1).lower())

        entries.append((bot_id, token, line))

    return entries


def cmd_tokens() -> int:
    """جدول حالة التوكنات لكل بوت مع اليوزرنيم المخطط من الريجستري"""
    print_banner()
    bots = _load_registry_bots()
    if not bots:
        print("❌ bots_registry.json غير موجود أو فارغ!")
        return 1

    env_tokens = _read_env_tokens()

    print(f"{'#':<3} | {'المعرف':<18} | {'اليوزرنيم المخطط':<22} | {'الحالة':<12} | التوكن")
    print("─" * 85)

    active = 0
    missing = []
    for i, b in enumerate(bots, start=1):
        bid = b.get("id", "?")
        planned = (b.get("username") or "—").lstrip("@") or "—"
        key = f"BOT_{bid.upper()}_TOKEN"
        tok = env_tokens.get(key)
        if tok:
            hint = f"{tok.split(':')[0]}:…"
            status = "🟢 فعّال"
            active += 1
        else:
            hint = ""
            status = "🟡 بدون توكن"
            missing.append((bid, planned))
        print(f"{i:<3} | {bid:<18} | @{planned:<21} | {status:<12} | {hint}")

    print("─" * 85)
    print(f"الإجمالي: {len(bots)} بوت  |  🟢 فعّال: {active}  |  🟡 ينتظر توكن: {len(missing)}")

    if missing:
        print(f"\n💡 لتفعيل البوتات الناقصة:")
        print(f"  1. أنشئ كل بوت في @BotFather بنفس اليوزرنيم المخطط أعلاه (أو أي اسم ثم عدّل السجل)")
        print(f"  2. ضع التوكنات في ملف new_tokens.txt بالبيت واليوزرنيم أو المعرّف، سطر لكل بوت")
        print(f"  3. شغّل: python dev_tools.py import-tokens")
    return 0


def cmd_tokens_verify() -> int:
    """فحص صلاحية كل التوكنات الفعّالة في .env عبر getMe"""
    print_banner()
    tokens = _read_env_tokens()
    if not tokens:
        print("ℹ️ لا توجد توكنات فعّالة في .env بعد.")
        return 0

    bots = _load_registry_bots()
    expected = {b.get("id"): (b.get("username") or "").lstrip("@").lower()
                for b in bots if b.get("id")}

    print(f"🔎 جاري فحص {len(tokens)} توكن عبر خوادم تيليجرام...\n")
    valid = invalid = mismatched = 0
    for key, tok in tokens.items():
        bid = key[4:-6].lower()
        ok, username, title = _verify_token_telegram(tok)
        if not ok:
            print(f"  ❌ {bid:<18} التوكن مرفوض من تيليجرام (محجوب أو محذوف)")
            invalid += 1
            continue
        valid += 1
        note = ""
        exp = expected.get(bid)
        if exp and username and username.lower() != exp:
            note = f"  ⚠️ اليوزر الفعلي مختلف عن المخطط ({exp})"
            mismatched += 1
        print(f"  ✅ {bid:<18} @{username} — {title}{note}")

    print("─" * 60)
    print(f"النتيجة: ✅ {valid} سليم  |  ❌ {invalid} مرفوض  |  ⚠️ {mismatched} يوزر مختلف")
    return 0 if invalid == 0 else 1


def cmd_import_tokens(source: str = None) -> int:
    """
    إدخال توكنات بالجملة من ملف (new_tokens.txt افتراضياً) أو stdin.
    كل سطر: @username token  أو  BOT_X_TOKEN=token  أو  x=token  أو  token فقط.
    """
    print_banner()
    bots = _load_registry_bots()
    known_ids = {b.get("id") for b in bots if b.get("id")}
    username_map = {(b.get("username") or "").lstrip("@").lower(): b.get("id")
                    for b in bots if b.get("username")}

    # قراءة المصدر
    if source and source != "-":
        path = Path(source)
        if not path.exists():
            print(f"❌ الملف غير موجود: {path}")
            return 1
        text = path.read_text(encoding="utf-8")
        print(f"📂 تمت قراءة {path.name} ({len(text.splitlines())} سطر)")
    else:
        default = BASE_DIR / "new_tokens.txt"
        if default.exists():
            text = default.read_text(encoding="utf-8")
            print(f"📂 تمت قراءة {default.name} ({len(text.splitlines())} سطر)")
        else:
            print("📥 الصق أسطر التوكنات (سطر لكل بوت) واختم بـ Ctrl+Z ثم Enter في Windows أو Ctrl+D في Linux:")
            text = sys.stdin.read()

    entries = parse_token_entries(text, known_ids, username_map)
    if not entries:
        print("ℹ️ لا توجد أسطر للمعالجة.")
        return 0

    imported = skipped = 0
    print(f"\n🔑 معالجة {len(entries)} سطر...\n")
    for bot_id, token, line in entries:
        if token is None:
            print(f"  ⚠️ سطر بدون توكن صالح — تم تخطيه: {line[:60]}")
            skipped += 1
            continue

        # توكن مجرد بدون معرف → التعرف عليه عبر getMe ثم مطابقته بالريجستري
        if bot_id is None:
            ok, username, _ = _verify_token_telegram(token)
            if ok and username:
                bot_id = username_map.get(username.lower())
                if bot_id is None:
                    print(f"  ⚠️ التوكن يعود للبوت @{username} وهو غير مسجل في الريجستري — تم تخطيه")
                    skipped += 1
                    continue
            else:
                print(f"  ❌ تعذر التحقق من توكن مجرد (سطر: {line[:40]}…) — تم تخطيه")
                skipped += 1
                continue

        if bot_id not in known_ids:
            print(f"  ⚠️ معرف غير معروف في الريجستري: {bot_id} — تم تخطيه")
            skipped += 1
            continue

        print(f"\n▶ [{bot_id}]")
        cmd_set_token(bot_id, token)
        imported += 1

    print("─" * 60)
    print(f"النتيجة: ✅ تم إدخال {imported} توكن  |  ⚠️ تم تخطي {skipped} سطر")
    if imported:
        print("\n📋 خطوتك التالية: python dev_tools.py tokens  لعرض الحالة المحدثة، ثم شغّل البوتات من Manager.")
    return 0 if imported or not skipped else 1


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


def cmd_ads() -> int:
    """عرض جدول شامل بحالة شفرات إعلانات Monetag لجميع البوتات والتطبيقات"""
    print_banner()
    from ad_manager import get_ad_manager
    mgr = get_ad_manager()
    statuses = mgr.get_all_monetag_statuses()

    print(f"\n📢 حالة شفرات إعلانات Monetag لجميع التطبيقات الـ {len(statuses)}:")
    print("=" * 85)
    print(f"{'#':<3} | {'المعرف (ID)':<15} | {'حالة الإعلان':<14} | {'الصيغة':<12} | {'مشاهدات':<8} | {'نقرات':<6} | {'CTR %':<7} | {'اسم التطبيق'}")
    print("─" * 85)

    has_count = 0
    missing_count = 0
    for i, (bid, st) in enumerate(statuses.items(), 1):
        if st["has_ad"]:
            has_count += 1
            status_txt = "🟢 مخصّص" if st["is_custom"] else "🟢 عام"
        else:
            missing_count += 1
            status_txt = "⚠️ غير مركّب"

        fmt = st["format"]
        imp = st["impressions"]
        clk = st["clicks"]
        ctr = f"{st['ctr_percent']}%"
        title = st["bot_name"]
        print(f"{i:<3} | {bid:<15} | {status_txt:<14} | {fmt:<12} | {imp:<8} | {clk:<6} | {ctr:<7} | {title}")

    print("─" * 85)
    print(f"📊 الخلاصة: {has_count} تطبيق مجهّز بإعلانات Monetag  |  {missing_count} تطبيق ينقصه شفرات إعلانية.")
    return 0


def cmd_set_ad(bot_id: str, direct_link_or_zone: str, format_type: str = "direct_link") -> bool:
    """ضبط شفرة إعلانات Monetag لبوت معين وحقنها فوراً"""
    from ad_manager import get_ad_manager
    mgr = get_ad_manager()
    clean_id = bot_id.lower().strip().replace("bot_", "")

    val = direct_link_or_zone.strip()
    direct_link = val if val.startswith("http") else ""
    zone_id = val if val.isdigit() else ""
    script_url = val if (val.startswith("http") and "thubanoa" in val) else ""

    mgr.set_monetag_config(clean_id, direct_link=direct_link, zone_id=zone_id,
                           script_url=script_url, format_type=format_type, active=True)
    try:
        import subprocess
        subprocess.run([sys.executable, "tools/build_mini_apps.py"], capture_output=True)
    except Exception:
        pass

    print(f"✅ تم ضبط شفرة Monetag للبوت [{clean_id}] وحقنها في تطبيق الويب بنجاح!")
    return True


def cmd_errors(bot_id: Optional[str] = None) -> int:
    """استعراض سجل وتقرير الأخطاء الحديثة والتشخيص الذكي"""
    print_banner()
    from database import get_db
    db = get_db()
    if not db:
        print("❌ تعذر الاتصال بقاعدة البيانات.")
        return 1

    clean_bot = bot_id.replace("bot_", "") if bot_id else None
    errors = db.get_recent_errors(bot_name=clean_bot, limit=40)
    summary = db.get_error_summary(days=7)

    target_str = f"للبوت [{clean_bot}]" if clean_bot else "لجميع البوتات"
    print(f"\n🚨 مركز الأخطاء والتشخيص الذكي {target_str} (إجمالي أخطاء الأسبوع: {summary.get('total_errors', 0)}):")
    print("=" * 85)
    if not errors:
        print("🎉 رائع! لا توجد أخطاء مسجلة حالياً.")
        return 0

    print(f"{'الوقت':<19} | {'البوت':<12} | {'فئة الخطأ':<20} | {'رسالة الخطأ'}")
    print("─" * 85)
    for e in errors:
        t = e.get("occurred_at", "")[:19].replace("T", " ")
        b = e.get("bot_name", "")
        cat = e.get("error_type", "")
        msg = e.get("error_message", "")[:40].replace("\n", " ")
        print(f"{t:<19} | {b:<12} | {cat:<20} | {msg}")
    print("─" * 85)
    return 0


def collect_diagnostics(db=None, monetag_statuses: Optional[Dict[str, dict]] = None) -> Dict[str, Any]:
    """جمع بيانات التشخيص الشامل (بنية/توكنات/صفحات/إعلانات/أخطاء) — بلا شبكة وقابلة للفحص"""
    from collections import Counter

    # 1) السجل والتوكنات والصفحات
    bots: List[dict] = []
    if REGISTRY.exists():
        try:
            with open(REGISTRY, "r", encoding="utf-8") as f:
                data = json.load(f)
            bots = data if isinstance(data, list) else data.get("bots", [])
        except Exception:
            bots = []

    env_map: Dict[str, str] = {}
    if ENV_FILE.exists():
        try:
            for ln in ENV_FILE.read_text(encoding="utf-8").splitlines():
                if "=" in ln and not ln.strip().startswith("#"):
                    k, _, v = ln.partition("=")
                    env_map[k.strip()] = v.strip()
        except Exception:
            pass

    token_re = re.compile(r"^\d{5,}:[\w-]{20,}$")
    tokens_ok = sum(
        1 for b in bots
        if token_re.match(env_map.get(f"BOT_{str(b.get('id', '')).upper()}_TOKEN", "")))
    pages_ok = sum(
        1 for b in bots
        if (BASE_DIR / "webroot" / str(b.get("id", "")) / "index.html").exists())

    # 2) تغطية إعلانات Monetag
    if monetag_statuses is None:
        try:
            from ad_manager import get_ad_manager
            monetag_statuses = get_ad_manager().get_all_monetag_statuses()
        except Exception:
            monetag_statuses = {}
    ads_ready = sum(1 for st in monetag_statuses.values() if st.get("has_ad"))

    # 3) قاعدة البيانات: الأخطاء والإعلانات
    if db is None:
        try:
            from database import get_db
            db = get_db()
        except Exception:
            db = None

    errors_summary: Dict[str, Any] = {}
    recent_errors: List[dict] = []
    ad_summary: Dict[str, Any] = {}
    ad_top: List[dict] = []
    if db:
        try:
            errors_summary = db.get_error_summary(days=7) or {}
        except Exception:
            pass
        try:
            recent_errors = db.get_recent_errors(limit=300) or []
        except Exception:
            pass
        try:
            ad_summary = db.get_ad_summary() or {}
        except Exception:
            pass
        try:
            ad_top = db.get_ad_stats() or []
        except Exception:
            pass

    fp_counter = Counter(e.get("fingerprint", "") for e in recent_errors if e.get("fingerprint"))
    return {
        "bots_total": len(bots),
        "tokens_ok": tokens_ok,
        "pages_ok": pages_ok,
        "ads_ready": ads_ready,
        "ads_total": len(monetag_statuses),
        "errors_summary": errors_summary,
        "top_fingerprints": fp_counter.most_common(5),
        "recent_errors_count": len(recent_errors),
        "ad_summary": ad_summary,
        "ad_top": ad_top,
    }


def cmd_diagnose() -> int:
    """تشخيص ذكي شامل: البنية + التوكنات + الصفحات + إعلانات Monetag + الأخطاء + توصيات فورية"""
    print_banner()
    rep = collect_diagnostics()
    total = rep["bots_total"]
    err = rep["errors_summary"] or {}

    print("\n🩺 التشخيص الذكي الشامل — تقرير فوري")
    print("═" * 62)

    # ── البنية ──
    print("🧩 بنية النظام")
    print(f"   • البوتات المسجلة:             {total}")
    print(f"   • توكنات صالحة الصيغة:         {rep['tokens_ok']}/{total}")
    print(f"   • صفحات التطبيقات المبنية:     {rep['pages_ok']}/{total}")
    print(f"   • شفرات Monetag الجاهزة:       {rep['ads_ready']}/{rep['ads_total']}")

    # ── الأخطاء ──
    print("\n🚨 صحة الأخطاء (آخر 7 أيام)")
    total_errors = err.get("total_errors", 0)
    print(f"   • إجمالي الأخطاء: {total_errors}   (أحدث سجل محمّل: {rep['recent_errors_count']})")
    by_type = err.get("by_type") or {}
    if by_type:
        print("   • حسب النوع: " + " | ".join(f"{k}: {v}" for k, v in list(by_type.items())[:5]))
    by_bot = err.get("by_bot") or {}
    if by_bot:
        print("   • حسب البوت: " + " | ".join(f"{k}: {v}" for k, v in list(by_bot.items())[:5]))
    if rep["top_fingerprints"]:
        print("   • أكثر البصمات تكراراً: " +
              " | ".join(f"{fp}×{cnt}" for fp, cnt in rep["top_fingerprints"]))

    # ── الإعلانات ──
    ads = rep["ad_summary"] or {}
    print("\n📢 أداء إعلانات Monetag")
    print(f"   • الظهور الكلي: {ads.get('total_impressions', 0)}   |   النقرات: {ads.get('total_clicks', 0)}"
          f"   |   CTR: {ads.get('overall_ctr', 0.0)}%")
    print(f"   • اليوم: ظهور {ads.get('today_impressions', 0)} / نقرات {ads.get('today_clicks', 0)}")
    if rep["ad_top"]:
        tops = ", ".join(f"{r.get('bot_name', '?')} ({r.get('impressions', 0)})"
                         for r in rep["ad_top"][:5])
        print(f"   • الأكثر ظهوراً: {tops}")

    # ── التوصيات الذكية ──
    print("\n💡 التوصيات:")
    tips: List[str] = []
    if rep["tokens_ok"] < total:
        tips.append(f"🔑 {total - rep['tokens_ok']} بوت بلا توكن صالح — أضفه عبر: "
                    "python dev_tools.py import-tokens")
    if rep["pages_ok"] < total:
        tips.append("🛠 بعض صفحات التطبيقات مفقودة — أعد البناء: "
                    "python tools/build_mini_apps.py")
    if rep["ads_ready"] == 0:
        tips.append("📢 لم تُضبط شفرات Monetag بعد — اضبطها عبر: "
                    "python dev_tools.py set-ad <bot_id> <smartlink|zone_id>")
    dominant = max(by_type.items(), key=lambda kv: kv[1])[0] if by_type else ""
    if total_errors and dominant.startswith("AUTH_TOKEN"):
        tips.append("🔐 أخطاء توكن مسيطرة — تحقق فوراً: python dev_tools.py tokens-verify")
    if total_errors and dominant.startswith("TELEGRAM_RATE_LIMIT"):
        tips.append("⏳ أخطاء Rate Limit مسيطرة — ارفع فترات الانتظار أو فعّل rate_limiter")
    if not tips:
        tips.append("✅ كل شيء سليم — لا إجراءات مطلوبة الآن")
    for t in tips:
        print(f"   • {t}")

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("🔎 لمزيد من التفاصيل: python dev_tools.py errors  |  python dev_tools.py ads")
    return 0


def cmd_apm_stats() -> int:
    """عرض إحصائيات الأداء والمستخدمين والإعلانات الشاملة"""
    print_banner()
    from database import get_db
    from ad_manager import get_ad_manager
    db = get_db()
    mgr = get_ad_manager()

    user_counts = db.get_all_users_count() if db else {}
    err_summary = db.get_error_summary(days=7) if db else {}
    ad_summary = db.get_ad_summary() if db else {}
    ad_statuses = mgr.get_all_monetag_statuses()

    print("\n📊 تقرير مؤشرات الأداء الحيوية (Boda APM Analytics):")
    print("=" * 65)
    print(f"  🤖 إجمالي البوتات المسجلة:       {len(ad_statuses)}")
    print(f"  👥 إجمالي المستخدمين المسجلين:   {sum(user_counts.values())}")
    print(f"  📢 تطبيقات مجهزة بـ Monetag:     {sum(1 for s in ad_statuses.values() if s['has_ad'])}")
    print(f"  ⚠️ تطبيقات بدون إعلانات:         {sum(1 for s in ad_statuses.values() if not s['has_ad'])}")
    print(f"  👁️ مشاهدات إعلانات Monetag:     {ad_summary.get('total_impressions', 0)}")
    print(f"  🎯 نقرات إعلانات Monetag:       {ad_summary.get('total_clicks', 0)} (CTR: {ad_summary.get('overall_ctr', 0.0)}%)")
    print(f"  🚨 أخطاء مسجلة آخر 7 أيام:       {err_summary.get('total_errors', 0)}")
    print("=" * 65)
    return 0


def cmd_interactive_menu():
    """لوحة تحكم تفاعلية للمطور لإدارة البوتات دون الحاجة لكتابة أوامر كل مرة"""
    while True:
        print_banner()
        print("📌 القائمة التفاعلية لإدارة النظام:")
        print("  [1] 📋 استعراض جدول البوتات وحالة التوكنات")
        print("  [2] 🔑 إدخال أو تحديث توكن بوت والتحقق منه فوراً")
        print("  [3] 📢 استعراض وضبط إعلانات Monetag (شفرات الإعلانات)")
        print("  [4] 🚨 مركز الأخطاء والتشخيص الذكي (Error Center)")
        print("  [5] 📊 تقرير مؤشرات الأداء والإحصائيات الشاملة")
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
            cmd_ads()
            ask = input("\n🔹 هل تريد ضبط شفرة إعلان لبوت الآن؟ (y/n): ").strip().lower()
            if ask == "y":
                bid = input("🔹 معرّف البوت: ").strip()
                code = input("🔹 رابط Monetag Smartlink أو معرف الزون Zone ID: ").strip()
                if bid and code:
                    cmd_set_ad(bid, code)
        elif choice == "4":
            cmd_errors()
        elif choice == "5":
            cmd_apm_stats()
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


def cmd_backup_verify(path: Optional[str] = None) -> int:
    """اختبار استعادة فعلي لنسخة احتياطية (الأحدث افتراضياً)."""
    print_banner()
    import backup_manager
    report = backup_manager.verify_backup(Path(path) if path else None)

    print(f"\n🔎 اختبار الاستعادة: {report.get('backup', '?')}")
    if report.get("ok"):
        print(f"   ✅ قاعدة البيانات سليمة (integrity: {report.get('integrity')})")
        print(f"   📊 الجداول: {report.get('tables')}")
        print(f"   💾 الحجم بعد الاستعادة: {report.get('db_size_kb')} KB")
        print("   ✅ النسخة صالحة للاستعادة فعلياً.")
        return 0
    print(f"   ❌ فشل: {report.get('error')}")
    return 1


# ─────────────────────────────────────────────────────────────────────────────
# Control Center CLI (Phase 1) — كل ما تفعله الواجهة يمكن تنفيذه من الطرفية
# ─────────────────────────────────────────────────────────────────────────────
def _cc_api_base() -> str:
    """Base URL of a running Control Center API."""
    return os.getenv("BODA_CC_URL", "http://127.0.0.1:8080").rstrip("/")


def _cc_api_request(method: str, path: str, payload: dict | None = None,
                    timeout: float = 20.0):
    """
    Call the Control Center API.

    Returns ``(ok, data)``; ``ok`` is False when the server is unreachable.
    """
    import urllib.request
    import urllib.error
    url = _cc_api_base() + path
    data = json.dumps(payload or {}).encode("utf-8") if method != "GET" else None
    headers = {"Content-Type": "application/json"}
    key = os.getenv("API_SERVER_KEY", "").strip()
    if key:
        headers["X-API-Key"] = key
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return True, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8")
            return False, json.loads(body) if body else {"error": str(exc)}
        except Exception:
            return False, {"error": f"HTTP {exc.code}"}
    except Exception as exc:
        return False, {"error": str(exc)}


def cmd_cc_status() -> int:
    """حالة مركز التحكم: صحة الخدمة، الترحيلات، الإعدادات"""
    print_banner()
    print("🧭 مركز التحكم (Control Center):")
    ok, data = _cc_api_request("GET", "/api/v1/system/health")
    if not ok:
        print(f"  ❌ الخادم لا يستجيب على {_cc_api_base()} ({data.get('error')})")
        print("     شغّله بـ:  python api_server.py")
        return 1
    print(f"  • الخدمة: {data.get('service')} v{data.get('version')}")
    print(f"  • قاعدة البيانات: {'✅ جاهزة' if data.get('database_ready') else '❌ غير جاهزة'}")
    print(f"  • المسار: {data.get('database_path')}")
    print(f"  • تشفير التوكنات: {'✅ مفعّل' if data.get('encryption_available') else '⚠ التوكنات في .env'}")

    ok, mig = _cc_api_request("GET", "/api/v1/system/migrations")
    if ok:
        print(f"  • الترحيلات: الإصدار {mig.get('current_version')}"
              f" / {mig.get('latest_available')} — مطبّق {mig.get('applied_count')}")
        if mig.get("pending"):
            print(f"  ⚠️ معلّق: {', '.join(mig.get('pending', []))}")

    ok, ov = _cc_api_request("GET", "/api/v1/overview")
    if ok:
        bots = ov.get("bots", {})
        print(f"  • البوتات: {bots.get('running', 0)} يعمل / {bots.get('total', 0)} إجمالي")
        print(f"  • سجل التدقيق: {ov.get('audit', {}).get('total', 0)} عملية")
    return 0


def cmd_cc_bots() -> int:
    """قائمة البوتات مع حالتهم التشغيلية"""
    ok, data = _cc_api_request("GET", "/api/v1/bots")
    if not ok:
        print(f"❌ تعذر جلب البوتات: {data.get('error')}")
        return 1
    bots = data.get("bots", [])
    print(f"\n🤖 البوتات ({len(bots)}):")
    print(f"   {'المعرف':<18}{'الحالة':<10}{'مدة التشغيل':<14}{'أخطاء':<8}الاسم")
    print("   " + "-" * 78)
    for bot in bots:
        state = "يعمل" if bot.get("running") else "متوقف"
        if not bot.get("enabled"):
            state = "معطّل"
        uptime = bot.get("uptime_seconds", 0)
        up = f"{uptime // 3600}h {uptime % 3600 // 60}m" if uptime else "—"
        err = "✅" if not bot.get("last_error") else "⚠️"
        print(f"   {bot.get('bot_id', ''):<18}{state:<10}{up:<14}{err:<8}"
              f"{bot.get('display_name') or bot.get('name', '')}")
    return 0


def cmd_cc_lifecycle(action: str, bot_id: str) -> int:
    """تشغيل / إيقاف / إعادة تشغيل بوت"""
    if not bot_id:
        print("❌ الاستخدام: python dev_tools.py cc-<action> <bot_id>")
        return 1
    ok, data = _cc_api_request("POST", f"/api/v1/bots/{bot_id}/{action}")
    if ok and data.get("ok"):
        print(f"✅ {action} ناجح: {bot_id}")
        return 0
    print(f"❌ فشل {action} لـ {bot_id}: {data.get('error') or data}")
    if "server_runner" in str(data.get("error", "")):
        print("   💡 أوقف server_runner.py أولاً، أو شغّل مركز التحكم كمالك وحيد.")
    return 1


def cmd_cc_logs(bot_id: str = "", limit: int = 50) -> int:
    """آخر سجلات بوت (أو كل البوتات)"""
    path = f"/api/v1/bots/{bot_id}/logs?limit={limit}" if bot_id else \
           f"/api/v1/overview"
    if not bot_id:
        print("ℹ️  لعرض سجل بوت محدد استخدم: cc-logs <bot_id> [عدد]")
        return 0
    ok, data = _cc_api_request("GET", path)
    if not ok:
        print(f"❌ تعذر جلب السجلات: {data.get('error')}")
        return 1
    lines = data.get("lines", [])
    print(f"📄 آخر {len(lines)} سطر من سجل [{bot_id}]:")
    for line in lines:
        print(f"   [{line.get('level', 'info'):<7}] {line.get('line', '')}")
    return 0


def cmd_cc_migrate(rollback: bool = False) -> int:
    """تطبيق الترحيلات أو التراجع عن آخرها"""
    ok, data = _cc_api_request("GET", "/api/v1/system/migrations")
    if not ok:
        print(f"❌ الخادم لا يستجيب ({data.get('error')})")
        return 1
    print(f"📦 الحالة: الإصدار {data.get('current_version')} — مطبّق {data.get('applied_count')}")
    if data.get("pending"):
        print(f"   معلّق: {', '.join(data['pending'])}")
    if not rollback:
        print("   (الترحيلات تُطبَّق تلقائياً عند تشغيل api_server.py)")
    return 0


def cmd_cc_audit(limit: int = 30) -> int:
    """سجل التدقيق"""
    ok, data = _cc_api_request("GET", f"/api/v1/audit?limit={limit}")
    if not ok:
        print(f"❌ تعذر جلب سجل التدقيق: {data.get('error')}")
        return 1
    entries = data.get("entries", [])
    print(f"\n📋 سجل التدقيق (الإجمالي {data.get('total', 0)}):")
    for entry in entries:
        target = f"{entry.get('target_type', '')}:{entry.get('target_id', '')}".strip(":")
        print(f"   {entry.get('occurred_at', '')[:19]}  {entry.get('actor', ''):<10}"
              f" {entry.get('action', ''):<24} {target}")
    return 0


def main():
    if len(sys.argv) < 2:
        if sys.stdin.isatty():
            cmd_interactive_menu()
            return

        print_banner()
        print("الخيارات المتاحة:")
        print("  menu                         - فتح اللوحة التفاعلية لإدارة البوتات")
        print("  status                       - عرض تقرير شامل لحالة النظام")
        print("  stats                        - تقرير مؤشرات الأداء والقياس عن بُعد (APM)")
        print("  ads                          - جدول حالة شفرات إعلانات Monetag لجميع التطبيقات")
        print("  set-ad <id> <link|zone>      - ضبط شفرة Monetag لتطبيق معين وحقنها فوراً")
        print("  errors [bot_id]              - مركز تشخيص وسجل الأخطاء الحديثة")
        print("  diagnose                     - تشخيص ذكي شامل (بنية + توكنات + إعلانات + أخطاء + توصيات)")
        print("  list-bots                    - جدول بجميع البوتات ومعرفاتها وحالة توكناتها")
        print("  set-token <id> <token>       - إعداد توكن البوت والتحقق منه تلقائياً")
        print("  set-username <id> <username> - تحديث يوزر البوت في السجل")
        print("  tokens                       - جدول حالة التوكنات واليوزرنيم المخطط لكل بوت")
        print("  import-tokens [file|-]       - إدخال توكنات بالجملة مع الفحص (افتراضياً new_tokens.txt)")
        print("  tokens-verify                - فحص صلاحية كل التوكنات الحالية عبر تيليجرام")
        print("  test [args...]               - تشغيل الاختبارات التلقائية")
        print("  lint                         - فحص ملفات بايثون للتأكد من خلوها من الأخطاء")
        print("  clean                        - مسح ملفات الكاش والملفات المؤقتة")
        print("  health                       - فحص صحة وتكامل البوتات المسجلة")
        print("  bots-check                   - فحص جودة شامل (7 فحوصات لكل بوت، بلا إنترنت)")
        print("  repos-sync                   - رفع صفحات البوتات لكل مستودعاتها + تفعيل Pages + تحقق حي")
        print("  backup [--no-zip]            - إنشاء نسخة احتياطية فورية")
        print("  backup-verify [file]         - اختبار استعادة فعلي للنسخة (الأحدث افتراضياً)")
        print("  secret-scan [--cached|--history N] - فحص أسرار المستودع (توكِنات/مفاتيح)")
        print("  ab-report                    - تقرير اختبار A/B للإعلانات (مجموعات A/B وCTR)")
        print("  cc-status                    - حالة مركز التحكم (صحة + ترحيلات + إعدادات)")
        print("  cc-bots                      - جدول البوتات مع حالة التشغيل ومدة التشغيل")
        print("  cc-start <bot_id>            - تشغيل بوت عبر مركز التحكم")
        print("  cc-stop <bot_id>             - إيقاف بوت عبر مركز التحكم")
        print("  cc-restart <bot_id>          - إعادة تشغيل بوت (يحمّل آخر الكود)")
        print("  cc-logs <bot_id> [n]         - آخر أسطر سجل بوت")
        print("  cc-migrate                   - حالة ترحيلات قاعدة البيانات")
        print("  cc-audit [n]                 - سجل التدقيق (من فعل ماذا ومتى)")
        return

    cmd = sys.argv[1].lower()

    if cmd == "menu":
        cmd_interactive_menu()
    elif cmd in ("status", "sys"):
        cmd_status()
    elif cmd in ("stats", "apm", "analytics"):
        sys.exit(cmd_apm_stats())
    elif cmd in ("ads", "monetag", "ads-status"):
        sys.exit(cmd_ads())
    elif cmd == "set-ad":
        if len(sys.argv) < 4:
            print("❌ الاستخدام: python dev_tools.py set-ad <bot_id> <direct_link_or_zone_id> [format]")
            sys.exit(1)
        fmt = sys.argv[4] if len(sys.argv) > 4 else "direct_link"
        cmd_set_ad(sys.argv[2], sys.argv[3], fmt)
    elif cmd in ("errors", "err", "error-center"):
        bid = sys.argv[2] if len(sys.argv) > 2 else None
        sys.exit(cmd_errors(bid))
    elif cmd in ("diagnose", "doctor"):
        sys.exit(cmd_diagnose())
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
    elif cmd == "tokens":
        sys.exit(cmd_tokens())
    elif cmd == "import-tokens":
        src = sys.argv[2] if len(sys.argv) > 2 else None
        sys.exit(cmd_import_tokens(src))
    elif cmd == "tokens-verify":
        sys.exit(cmd_tokens_verify())
    elif cmd == "test":
        sys.exit(cmd_test(sys.argv[2:]))
    elif cmd == "lint":
        sys.exit(cmd_lint())
    elif cmd == "clean":
        sys.exit(cmd_clean())
    elif cmd == "health":
        sys.exit(cmd_health())
    elif cmd in ("bots-check", "quality", "audit"):
        sys.exit(cmd_bots_check())
    elif cmd in ("repos-sync", "repo-sync"):
        # مزامنة مستودعات البوتات (رفع القالب الجديد + Pages + تحقق حي) عبر tools/sync_bot_repos.py
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        rc = subprocess.call([sys.executable, str(BASE_DIR / "tools" / "sync_bot_repos.py")], env=env)
        sys.exit(rc)
    elif cmd == "backup":
        import backup_manager
        compress = "--no-zip" not in sys.argv
        p = backup_manager.create_backup(compress=compress)
        print(f"✅ تم النسخ الاحتياطي: {p.name}")
    elif cmd in ("backup-verify", "verify-backup"):
        sys.exit(cmd_backup_verify(sys.argv[2] if len(sys.argv) > 2 else None))
    elif cmd in ("secret-scan", "secrets"):
        sys.path.insert(0, str(BASE_DIR / "tools"))
        import secret_scan
        sys.exit(secret_scan.main(sys.argv[2:]))
    elif cmd in ("ab-report", "ab"):
        sys.path.insert(0, str(BASE_DIR / "Bots_Folder"))
        from database import get_db
        try:
            report = get_db().get_ab_report()
        except Exception as e:
            print(f"❌ تعذر توليد تقرير A/B: {e}")
            sys.exit(1)
        print("🧪 تقرير اختبار A/B للإعلانات — آخر 30 يوماً")
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif cmd in ("cc-status", "cc_status"):
        sys.exit(cmd_cc_status())
    elif cmd in ("cc-bots", "cc_bots"):
        sys.exit(cmd_cc_bots())
    elif cmd in ("cc-start", "cc_start"):
        sys.exit(cmd_cc_lifecycle("start", sys.argv[2] if len(sys.argv) > 2 else ""))
    elif cmd in ("cc-stop", "cc_stop"):
        sys.exit(cmd_cc_lifecycle("stop", sys.argv[2] if len(sys.argv) > 2 else ""))
    elif cmd in ("cc-restart", "cc_restart"):
        sys.exit(cmd_cc_lifecycle("restart", sys.argv[2] if len(sys.argv) > 2 else ""))
    elif cmd in ("cc-logs", "cc_logs"):
        bot = sys.argv[2] if len(sys.argv) > 2 else ""
        try:
            n = int(sys.argv[3]) if len(sys.argv) > 3 else 50
        except ValueError:
            n = 50
        sys.exit(cmd_cc_logs(bot, n))
    elif cmd in ("cc-migrate", "cc_migrate"):
        sys.exit(cmd_cc_migrate())
    elif cmd in ("cc-audit", "cc_audit"):
        try:
            n = int(sys.argv[2]) if len(sys.argv) > 2 else 30
        except ValueError:
            n = 30
        sys.exit(cmd_cc_audit(n))
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
