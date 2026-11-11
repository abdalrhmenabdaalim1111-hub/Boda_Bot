#!/usr/bin/env python3
"""
tools/check_coverage.py — بوابة تغطية لكل وحدة أساسية (≥ الحد الأدنى)

يقرأ coverage.json (ناتج: pytest --cov-report=json) ويفشل إذا نزلت أي
وحدة أساسية مشتركة عن حدها الأدنى. ملفات البوتات الفردية (bot_*.py)
خارج البوابة حالياً — تُضاف تدريجياً مع اختبارات كل بوت.

الاستخدام:
    pytest --cov=Bots_Folder --cov-report=json --cov-report=term
    python tools/check_coverage.py
"""
import json
import sys
from pathlib import Path

# الوحدات الأساسية المشتركة → الحد الأدنى المطلوب لكل منها
CORE_MODULES = {
    "Bots_Folder/database.py": 80,
    "Bots_Folder/ad_manager.py": 80,
    "Bots_Folder/growth_engine.py": 80,
    "Bots_Folder/error_tracker.py": 80,
    "Bots_Folder/notification_system.py": 80,
    "Bots_Folder/unified_middleware.py": 80,
    "Bots_Folder/bot_base.py": 80,
    "Bots_Folder/i18n.py": 80,
    "Bots_Folder/webhook_server.py": 80,
    "Bots_Folder/logger_config.py": 80,
}


def main() -> int:
    cov_file = Path(__file__).parent.parent / "coverage.json"
    if not cov_file.exists():
        # السماح بالتشغيل من جذر المستودع أيضاً
        cov_file = Path("coverage.json")
    if not cov_file.exists():
        print("❌ coverage.json غير موجود — شغّل pytest مع --cov-report=json أولاً")
        return 2

    data = json.loads(cov_file.read_text(encoding="utf-8"))
    # coverage يستخدم فواصل مسار خاصة بالنظام (\\ على ويندوز) — نوحّدها
    files = {k.replace("\\", "/"): v for k, v in data.get("files", {}).items()}

    failures = []
    print(f"{'Module':40s} {'Cover':>7s}  Gate")
    print("-" * 60)
    for module, gate in sorted(CORE_MODULES.items()):
        entry = files.get(module)
        if entry is None:
            failures.append(f"{module}: غير موجود في تقرير التغطية")
            print(f"{module:40s} {'—':>7s}  ❌ MISSING (min {gate}%)")
            continue
        pct = entry["summary"]["percent_covered"]
        ok = pct >= gate
        print(f"{module:40s} {pct:6.1f}%  {'✅' if ok else '❌'} (min {gate}%)")
        if not ok:
            failures.append(f"{module}: {pct:.1f}% < {gate}%")

    if failures:
        print("\n❌ فشلت بوابة التغطية:")
        for f in failures:
            print(f"   - {f}")
        return 1

    print("\n✅ كل الوحدات الأساسية تجاوزت حد التغطية المطلوب")
    return 0


if __name__ == "__main__":
    sys.exit(main())
