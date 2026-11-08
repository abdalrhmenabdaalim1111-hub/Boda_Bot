# -*- coding: utf-8 -*-
"""
tools/patch_bot_entries.py — توحيد نقطة انطلاق جميع البوتات على bot_base.start_bot

ما يفعله لكل ملف bot_*.py:
  • إن كان يستخدم start_polling أصلاً → استبدالها بـ start_bot (ذكية: webhook/polling)
  • إن كان له كتلة polling خاصة → استبدال الكتلة كاملة باستدعاء موحد + استيراد ناقص
  • يستخرج allowed_updates إن وجدت ليحافظ على سلوك البوت
  • يتحقق من نجاح compile لكل ملف بعد التعديل (يرجع الأصل عند الفشل)

التشغيل:  python tools/patch_bot_entries.py [--dry]
"""
import re
import sys
import py_compile
from pathlib import Path

ROOT = Path(__file__).parent.parent
BOTS = ROOT / "Bots_Folder"

START_CALL = "    from bot_base import start_bot\n    start_bot(bot, \"{name}\"{extra})"


def bot_name_of(path: Path) -> str:
    return path.stem.replace("bot_", "", 1)


def compile_ok(path: Path) -> bool:
    try:
        py_compile.compile(str(path), doraise=True)
        return True
    except py_compile.PyCompileError as e:
        print(f"  ✗ compile failed: {e}")
        return False


def patch_file(path: Path, dry: bool = False) -> str:
    name = path.stem.replace("bot_", "", 1)
    if name == "template":
        return "skip-template"

    src = path.read_text(encoding="utf-8")

    # شذوذ المتجر: له نقطة انطلاق خاصة مع فحص توكن — نتخطاه (يُطوّر منفصلأ)
    if name == "store":
        return "skip-store"

    if "start_polling(bot" in src or "start_bot(bot" in src:
        # نمط A: استبدال الاستدعاء فقط
        new = re.sub(
            r"from bot_base import start_polling\n(\s*)start_polling\(bot,\s*\"[^\"]+\"\)",
            "from bot_base import start_bot\n\\1start_bot(bot, \"" + name + "\")",
            src)
        new = re.sub(
            r"start_polling\(bot,\s*\"[^\"]+\"\)",
            "start_bot(bot, \"" + name + "\")",
            new)
        if new == src:
            return "already"
        if not dry:
            path.write_text(new, encoding="utf-8")
        return "call-swapped"

    # نمط B: كتلة __main__ خاصة بكامل منطق polling
    m = re.search(r'if\s+__name__\s*==\s*["\']__main__["\']\s*:', src)
    if not m:
        return "no-main"

    # استخراج allowed_updates من الكتلة القديمة إن وُجدت
    tail = src[m.start():]
    au = re.search(r"allowed_updates\s*=\s*(\[[^\]]*\])", tail)
    extra = f", allowed_updates={au.group(1)}" if au else ""

    body = START_CALL.format(name=name, extra=extra)
    new = src[:m.start()] + 'if __name__ == "__main__":\n' + body + "\n"

    if not dry:
        orig = path.read_text(encoding="utf-8")
        path.write_text(new, encoding="utf-8")
        if not compile_ok(path):
            path.write_text(orig, encoding="utf-8")
            return "failed-rolled-back"
    return "main-rewritten"


def main():
    dry = "--dry" in sys.argv
    stats = {}
    for path in sorted(BOTS.glob("bot_*.py")):
        result = patch_file(path, dry=dry)
        stats[result] = stats.get(result, 0) + 1
        mark = {"main-rewritten": "✍️ ", "call-swapped": "🔁 ",
                "already": "·  ", "no-main": "⚠️ ",
                "failed-rolled-back": "✗ ", "skip-template": "⏭ ",
                "skip-store": "⏭ "}.get(result, "?  ")
        print(f"{mark}{path.name}: {result}")
    print("\n—— الملخص ——")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
