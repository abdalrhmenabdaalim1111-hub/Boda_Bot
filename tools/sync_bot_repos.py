# -*- coding: utf-8 -*-
"""
tools/sync_bot_repos.py — مزامنة مستودعات البوتات على GitHub

لكل بوت 34: يبني محتوى مستقلًا (صفحة بالقالب الجديد + بيانات + README + .nojekyll)
ثم يضمن وجود المستودع، يرفع المحتوى، يفعّل Pages إن لزم، ويتحقق حيًا من الصفحة.

- تحترم حد GitHub ("too many repositories, too quickly") بانتظار 10 دقائق.
- عبارة تشغيل:  python tools/sync_bot_repos.py
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
GH = r"C:\Program Files\GitHub CLI\gh.exe"
OWNER_ENV = "GITHUB_OWNER"
SITE_DEFAULT = "https://abdalrhmenabdaalim1111-hub.github.io"
UNIFIED_REPO = "Boda_Bot"
GIT_IDENTITY = ["-c", "user.name=Boda",
                "-c", "user.email=231137064+abdalrhmenabdaalim1111-hub@users.noreply.github.com"]

RATE_WAIT_SECONDS = 600        # انتظار عند رفض الإنشاء
CREATE_SPACING_SECONDS = 60    # تباعد بعد كل إنشاء جديد
PUSH_SPACING_SECONDS = 12      # تباعد بعد الرفع فقط


def get_owner() -> str:
    """أسماء المستخدم من متغير البيئة أو من gh CLI"""
    owner = os.getenv(OWNER_ENV, "").strip()
    if owner:
        return owner
    try:
        p = subprocess.run([GH, "api", "user", "--jq", ".login"],
                           capture_output=True, text=True, timeout=60)
        return p.stdout.strip() or SITE_DEFAULT.split("//")[1].split(".")[0]
    except Exception:
        return SITE_DEFAULT.split("//")[1].split(".")[0]


def build_repo_content(bot: dict, webroot: Path, dest: Path, site: str, owner: str) -> dict:
    """بناء محتوى مستقل لريبو بوت واحد — دالة نقطة (قابلة للفحص آليًا)"""
    bid = bot["id"]
    name = f"boda-bot-{bid}"
    dest.mkdir(parents=True, exist_ok=True)

    html = (webroot / bid / "index.html").read_text(encoding="utf-8")
    # مسارات بيانات لموقع مستقل + إعادة توجيه og:url لمستودع البوت الخاص
    html = html.replace("../data/", "./data/")
    html = html.replace(f"{site}/{UNIFIED_REPO}/{bid}/", f"{site}/{name}/")
    (dest / "index.html").write_text(html, encoding="utf-8")

    data = dest / "data"
    data.mkdir(exist_ok=True)
    copied = []
    for fname in ("catalog.json", "stats.json"):
        src = webroot / "data" / fname
        if src.exists():
            shutil.copy2(src, data / fname)
            copied.append(fname)

    (dest / ".nojekyll").write_text("", encoding="utf-8")
    (dest / "README.md").write_text(
        f"# {bot.get('emoji', '')} {bot['name']}\n\n{bot.get('description', '')}\n\n"
        f"🌐 **الموقع الحي:** {site}/{name}/\n\n"
        f"🤖 **البوت على تيليجرام:** https://t.me/{bot.get('username', '').lstrip('@')}\n\n"
        f"جزء من [Boda Bot System](https://github.com/{owner}/{UNIFIED_REPO})\n",
        encoding="utf-8")

    return {"name": name, "files": ["index.html", "README.md", ".nojekyll"] + copied}


def run(cmd, cwd=None, timeout=300) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                       encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout + p.stderr).strip()


def clean_dir(d: Path):
    """تنظيف محكم يعالج ملفات .git بخصائص read-only على Windows"""
    if d.exists():
        subprocess.run(["cmd", "/c", "rmdir", "/s", "/q", str(d)], capture_output=True, timeout=60)
        time.sleep(1)
    d.mkdir(parents=True, exist_ok=True)


def repo_exists(owner: str, name: str) -> bool:
    return run([GH, "api", f"repos/{owner}/{name}"])[0] == 0


def pages_enabled(owner: str, name: str) -> bool:
    return run([GH, "api", f"repos/{owner}/{name}/pages"])[0] == 0


def create_repo(owner: str, name: str) -> str | None:
    """إنشاء ريبو عام مع احترام حد GitHub — يعيد None على النجاح أو نص الخطأ"""
    for attempt in range(8):
        rc, out = run([GH, "repo", "create", name, "--public"], timeout=300)
        if rc == 0:
            return None
        low = out.lower()
        if "too many repositories" in low:
            print(f"    ⏳ حد GitHub — انتظار {RATE_WAIT_SECONDS}ث (محاولة {attempt + 1})", flush=True)
            time.sleep(RATE_WAIT_SECONDS)
            continue
        if "already exists" in low:
            return None
        if "TLS" in out or "timeout" in low:
            time.sleep(20)
            continue
        return f"create: {out[:130]}"
    return "create: استنفدت المحاولات على حد GitHub"


def page_live(url: str) -> bool:
    from urllib import request as urlreq
    try:
        with urlreq.urlopen(url, timeout=25) as r:
            return r.status == 200
    except Exception:
        return False


def main() -> int:
    print("🔄 مزامنة مستودعات البوتات هيكل الحالي → GitHub", flush=True)
    owner = get_owner()
    site = SITE_DEFAULT  # نطاق Pages الموحد للجميع
    webroot = ROOT / "webroot"
    reg = json.load(open(ROOT / "bots_registry.json", encoding="utf-8"))
    tmp = Path(os.getenv("TEMP", str(ROOT / "tmp"))) / "boda_sync_repos"
    tmp.mkdir(parents=True, exist_ok=True)

    done, errs = [], []
    for i, bot in enumerate(reg):
        bid = bot["id"]
        name = f"boda-bot-{bid}"
        print(f"\n[{i + 1}/{len(reg)}] {name}", flush=True)
        staging = tmp / bid
        clean_dir(staging)

        info = build_repo_content(bot, webroot, staging, site, owner)

        rc, out = run(["git", "init", "-q", "-b", "main"], cwd=staging)
        run(["git", "add", "-A"], cwd=staging)
        rc, out = run(["git"] + GIT_IDENTITY + ["commit", "-q", "-m", f"feat: {bot['name']} mini-app (pro template)"], cwd=staging)
        if rc:
            errs.append(f"{bid}: commit: {out[:100]}")
            continue

        was_new = False
        if not repo_exists(owner, name):
            err = create_repo(owner, name)
            if err:
                errs.append(f"{bid}: {err}")
                continue
            was_new = True
            time.sleep(10)
        run(["git", "remote", "add", "origin", f"https://github.com/{owner}/{name}.git"], cwd=staging)

        for attempt in range(3):
            rc, out = run(["git"] + GIT_IDENTITY + ["push", "-q", "-f", "origin", "main"], cwd=staging, timeout=420)
            if rc == 0:
                break
            if "TLS" in out or "timeout" in out.lower():
                time.sleep(20)
            else:
                break
        if rc:
            errs.append(f"{bid}: push: {out[:130]}")
            continue

        if not pages_enabled(owner, name):
            rc, out = run([GH, "api", "--method", "POST", f"/repos/{owner}/{name}/pages",
                           "-f", "source[branch]=main", "-f", "source[path]=/"])
            if rc and "already" not in out.lower() and "422" not in out:
                errs.append(f"{bid}: pages enable: {out[:130]}")
                continue
            time.sleep(25)

        url = f"{site}/{name}/"
        live = False
        for _ in range(3):
            live = page_live(url)
            if live:
                break
            time.sleep(15)
        status = "✅" if live else "⚠️ مرفوع، الصفحة لم تستجب بعد"
        print(f"    {status} {url}", flush=True)
        done.append({"id": bid, "url": url, "live": live, "created": was_new})

        time.sleep(CREATE_SPACING_SECONDS if was_new else PUSH_SPACING_SECONDS)

    print("\n" + "=" * 60, flush=True)
    print(f"النتيجة: {len(done)}/{len(reg)} مزامن | أخطاء: {len(errs)}", flush=True)
    for x in errs:
        print("  ❌", x, flush=True)
    (tmp.parent / "sync_results.json").write_text(
        json.dumps({"done": done, "errors": errs}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("=== SYNC DONE ===", flush=True)
    return 0 if not errs else 1


if __name__ == "__main__":
    if sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
