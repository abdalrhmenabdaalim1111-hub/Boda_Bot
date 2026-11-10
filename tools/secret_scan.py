"""
tools/secret_scan.py — كاسح أسرار للمستودع (بديل مؤتمت عن الفحص اليدوي).

لماذا؟
    سبق أن تسربت توكنات بوت تيليجرام إلى سجل Git (وثّقت في تقرير التدقيق) —
    هذا الكاسح يمنع تكرار الظاهرة قبل أي التزام ويُستخدم في CI كحاجز أول.

ماذا يفحص؟
    • الوضع الافتراضي: كل الملفات المتتبعة في git (الشجرة الحالية)
    • --cached   : سطور الالتزام المسرّح فقط (+ في git diff --cached)
    • --history N: عيّنة من آخر N التزامات — تقرير فقط (لا يفشل CI)،
                   لأن الأسرار في التاريخ تُعالج بالتدوير لا بالحذف.

أنماط الكشف:
    • توكن بوت تيليجرام: (8-10 أرقام):(30+ حرفاً بلا مسافات)
    • مفتاح API / كلمة سر مكتوبة literally في الكود بلا os.getenv

سماحية الأنماط الوهمية الموثقة (دروجنا المشتركة):
    • بادئات 1234567890: / 123456789:
    • كلمات العناصر النائبة: your_api_key_here, change-me, example, placeholder…

إخراج آمن: لا يُطبع أي مرشّح كاملاً — قناع فقط (أول 14 محرفاً + طول السلسلة).

كيف تستخدم؟
    python tools/secret_scan.py             # الشجرة الحالية (يفشل عند الاكتشاف)
    python tools/secret_scan.py --cached    # قبل الالتزام
    python tools/secret_scan.py --history 20
    python dev_tools.py secret-scan

الخروج: 0 نظيف | 1 سر مرشّح | 2 خطأ تنفيذ
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

TELEGRAM_TOKEN_RE = re.compile(r"\b(\d{8,10}):([A-Za-z0-9_-]{30,})\b")
KEY_RE = re.compile(
    r"(?i)(api[_-]?key|secret|password|passwd)\s*[=:]\s*[\"\']?"
    r"([A-Za-z0-9_\-\./+=]{16,})[\"\']?")

# توكنات العرض الموحدة المستخدمة في .env.example وكل الاختبارات
FAKE_TOKEN_PREFIXES = ("1234567890:", "123456789:")
# كلمات تسمّ العناصر النائبة — لا تُعتبر أسراراً
PLACEHOLDER_WORDS = (
    "your_api_key_here", "your_secure_password_here", "api_key_here",
    "change-me", "placeholder", "example", "dummy", "test", "testtest",
    "put-your", "xxx", "todo", "sample",
)
SKIP_DIRS = (".git", "__pycache__", ".venv", "venv", "node_modules")


def _mask(raw: str, keep: int = 14) -> str:
    """قناع القيم لتفادي إعادة نشر أي سر في مخرجات الفحص نفسها."""
    return f"{raw[:keep]}…(طول {len(raw)})"


def _is_fake(value: str) -> bool:
    v = value.lower()
    if value.startswith(FAKE_TOKEN_PREFIXES):
        return True
    return any(w in v for w in PLACEHOLDER_WORDS)


def scan_text(text: str, where: str):
    """فحص نص واحد وإرجاع [(مكان, سطر, نوع, قيمة مقنّعة)]."""
    findings = []
    for i, line in enumerate(text.splitlines(), 1):
        for m in TELEGRAM_TOKEN_RE.finditer(line):
            candidate = f"{m.group(1)}:{m.group(2)}"
            if not _is_fake(candidate):
                findings.append((where, i, "توكِن تيليجرام", _mask(candidate)))
        for m in KEY_RE.finditer(line):
            value = m.group(2)
            if not _is_fake(value) and "os." not in line and "getenv" not in line:
                findings.append((where, i, "مفتاح/كلمة سر مكتوبة", _mask(value)))
    return findings


def _git(args: str) -> str:
    proc = subprocess.run(f"git {args}", shell=True, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"git {args} فشل")
    return proc.stdout


def scan_tracked():
    """فحص كل الملفات المتتبعة في الشجرة الحالية."""
    findings = []
    for name in _git("ls-files").splitlines():
        if any(part in SKIP_DIRS for part in Path(name).parts):
            continue
        try:
            text = Path(name).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "\x00" in text[:2048]:  # ملف ثنائي
            continue
        findings.extend(scan_text(text, name))
    return findings


def scan_cached():
    """فحص سطور الالتزام المسرّح فقط (قبل git commit)."""
    findings = []
    current = "?"
    for line in _git("diff --cached -U0").splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
        elif line.startswith("+") and not line.startswith("+++"):
            findings.extend(scan_text(line[1:], f"(مسْرَّح) {current}"))
    return findings


def scan_history(depth: int = 20):
    """عيّنة من التاريخ: آخر N التزامات — تقرير لا يفشل البناء."""
    findings = []
    try:
        hashes = _git(f"log --all -n {int(depth)} --format=%h").splitlines()
    except RuntimeError as e:
        print(f"⚠ تعذّر قراءة التاريخ: {e}")
        return findings
    for h in hashes:
        current = "?"
        for line in _git(f"show {h}").splitlines():
            if line.startswith("+++ b/"):
                current = line[6:]
            elif line.startswith("+") and not line.startswith("+++"):
                findings.extend(
                    scan_text(line[1:], f"{h}:{current}"))
    # إزالة التكرار (نفس السر يظهر في عدة التزامات)
    unique = []
    seen = set()
    for f in findings:
        key = (f[2], f[3])
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique


def main(argv=None) -> int:
    # The report contains Arabic text and symbols; a Windows console defaults
    # to cp1252 and would raise UnicodeEncodeError while printing it.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    p = argparse.ArgumentParser(description="كاسح أسرار Boda Bot System")
    p.add_argument("--cached", action="store_true",
                   help="فحص سطور الالتزام المسرّح فقط")
    p.add_argument("--history", type=int, default=0, metavar="N",
                   help="فحص عيّنة من آخر N التزامات (تقرير فقط)")
    args = p.parse_args(argv)

    try:
        findings = scan_cached() if args.cached else scan_tracked()

        if args.history > 0:
            hist = scan_history(args.history)
            if hist:
                print(f"⚠ التاريخ يحتوي {len(hist)} سراً مسرّباً — "
                      "التدوير من BotFather إلزامي (الحذف من التاريخ غير كافٍ). "
                      "هذا تقرير ولا يفشل CI.")
            else:
                print("✅ المفحوص من التاريخ نظيف")

        if findings:
            print(f"❌ اكتُشف {len(findings)} سراً محتملاً — أوقف الالتزام:")
            for where, lineno, kind, mask in findings[:20]:
                print(f"   • [{kind}] {where}:{lineno} → {mask}")
            if len(findings) > 20:
                print(f"   … و{len(findings) - 20} أخرى")
            return 1

        print("✅ فحص الأسرار نظيف — لا توكنات أو مفاتيح حقيقية في الشجرة")
        return 0
    except RuntimeError as e:
        print(f"⚠ خطأ تنفيذ: {e} — راجع أن git يعمل")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
