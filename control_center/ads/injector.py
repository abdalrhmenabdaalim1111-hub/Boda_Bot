"""
control_center/ads/injector.py — marker-based injection engine.

Idempotent marker blocks:

    <!-- AD:BEGIN slot=<slot> id=<ad_id> -->
    ...snippet...
    <!-- AD:END slot=<slot> -->

Operations:
  * inject_markers(path, blocks)  — insert or update each block at the right
    anchor (</head>, </body>, after <header>, ...). Existing markers with the
    same (slot) are replaced; different slots coexist.
  * remove_markers(path, slots)   — remove blocks for the given slots.
  * dry_run(path, new_content)    — unified diff between current and proposed.
  * apply (via inject_markers with backup=True) — timestamped backup first,
    atomic write (temp + replace), post-write validation, rollback on failure.
  * rollback_file(path)           — restore the most recent backup of path.

Safety:
  * never touches a file outside the given path
  * preserves encoding (UTF-8) and line endings (LF) of the original
  * aborts (and restores) if the resulting file fails validation
"""

import difflib
import os
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from .validator import validate_snippet

MARKER_BEGIN = "<!-- AD:BEGIN slot={slot} id={ad_id} -->"
MARKER_END = "<!-- AD:END slot={slot} -->"

# A regex matching one complete marker block for a given slot (any ad_id).
BLOCK_RE = re.compile(
    r"<!-- AD:BEGIN slot=(?P<slot>[\w-]+) id=(?P<id>[\w-]+) -->.*?"
    r"<!-- AD:END slot=(?P=slot) -->",
    re.DOTALL,
)

# Anchors per slot — where to insert when no existing marker is present.
ANCHORS = {
    "head": ("</head>", "before"),
    "body_end": ("</body>", "before"),
    "banner_top": ("<header", "after_block"),
    "banner_bottom": ("</div>\
</body>", "before"),
    "interstitial": ("</body>", "before"),
}

BACKUP_DIR_NAME = "ads_pre"


def _backup_dir(path: Path) -> Path:
    return path.parent / f".ads_backup_{path.name}"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _detect_eol(text: str) -> str:
    return "\\r\
" if "\\r\
" in text else "\
"


def make_block(slot: str, ad_id: str, snippet: str) -> str:
    """Render one marker block (snippet kept byte-exact inside)."""
    nl = chr(10)
    return (MARKER_BEGIN.format(slot=slot, ad_id=ad_id) + nl
            + snippet.rstrip() + nl
            + MARKER_END.format(slot=slot))


def list_blocks(text: str) -> list[dict]:
    """Return [{slot, ad_id, start, end}] for every marker block in text."""
    out = []
    for m in BLOCK_RE.finditer(text):
        out.append({"slot": m.group("slot"), "ad_id": m.group("id"),
                    "start": m.start(), "end": m.end()})
    return out


def remove_markers(text: str, slots: list[str] | None = None) -> str:
    """Remove marker blocks. None/empty → remove all."""
    wanted = set(slots or [])
    def _repl(m):
        if wanted and m.group("slot") not in wanted:
            return m.group(0)
        return ""
    new = BLOCK_RE.sub(_repl, text)
    # collapse runs of blank lines left behind
    new = re.sub(r"\
{3,}", "\
\
", new)
    return new


def inject_markers(text: str, blocks: list[tuple[str, str, str]]) -> str:
    """
    Insert or replace marker blocks.

    ``blocks`` is a list of ``(slot, ad_id, snippet)``. For each, any existing
    block with the same slot is replaced in place; otherwise the block is
    inserted at the slot's anchor.
    """
    eol = _detect_eol(text)
    # First, remove existing blocks for the slots we are (re)injecting so we
    # can re-insert them at the correct (possibly new) anchor.
    slots_to_replace = {b[0] for b in blocks}
    # Keep a record of where each slot's old block lived so we can replace
    # in place when possible.
    current = text
    for slot, ad_id, snippet in blocks:
        new_block = make_block(slot, ad_id, snippet)
        # Replace existing block for this slot (in place) if present.
        slot_re = re.compile(
            rf"<!-- AD:BEGIN slot={re.escape(slot)} id=[\w-]+ -->.*?"
            rf"<!-- AD:END slot={re.escape(slot)} -->",
            re.DOTALL,
        )
        if slot_re.search(current):
            current = slot_re.sub(lambda _m: new_block, current, count=1)
            continue
        # Otherwise insert at the anchor.
        current = _insert_at_anchor(current, slot, new_block)
    return current


def _insert_at_anchor(text: str, slot: str, block: str) -> str:
    anchor, mode = ANCHORS.get(slot, ("</body>", "before"))
    if mode == "before":
        idx = text.rfind(anchor)
        if idx == -1:
            # fall back: append before end of file
            return text.rstrip() + "\
" + block + "\
"
        return text[:idx] + block + "\
" + text[idx:]
    if mode == "after_block":
        # insert after the closing of the first matching open tag block
        m = re.search(re.escape(anchor), text)
        if not m:
            idx = text.find("<body")
            if idx == -1:
                return text.rstrip() + "\
" + block + "\
"
            # insert after the body tag
            end = text.find(">", idx) + 1
            return text[:end] + "\
" + block + "\
" + text[end:]
        # find end of the tag
        end = text.find(">", m.start()) + 1
        return text[:end] + "\
" + block + "\
" + text[end:]
    return text.rstrip() + "\
" + block + "\
"


def dry_run(path: str | Path, new_content: str) -> str:
    """Unified diff (current → proposed) as a string."""
    p = Path(path)
    try:
        old = p.read_text(encoding="utf-8") if p.exists() else ""
    except Exception:
        old = ""
    old_lines = old.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    diff = difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"a/{p.name}", tofile=f"b/{p.name}",
    )
    return "".join(diff)


def _validate_result(text: str) -> bool:
    """Post-write sanity check: still parseable as HTML-ish + markers balanced."""
    if "<!DOCTYPE" not in text and "<html" not in text:
        return False
    # every BEGIN must have a matching END for the same slot
    begins = re.findall(r"<!-- AD:BEGIN slot=([\w-]+)", text)
    ends = re.findall(r"<!-- AD:END slot=([\w-]+)", text)
    if sorted(begins) != sorted(ends):
        return False
    return True


def _backup_path(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    d = _backup_dir(path)
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{path.name}.{stamp}.bak"


def apply_injection(path: str | Path, blocks: list[tuple[str, str, str]],
                    *, remove_slots: list[str] | None = None,
                    validate_snippets: bool = True) -> dict:
    """
    Apply marker injection to ``path``.

    Returns a dict with: ok, path, backup, diff, changed, error, warnings.
    On any failure the original file is restored from the backup.
    """
    p = Path(path)
    result = {"ok": False, "path": str(p), "backup": "", "diff": "",
              "changed": False, "error": "", "warnings": []}

    if not p.exists():
        result["error"] = f"file not found: {p}"
        return result

    # Validate snippets first (hard errors abort before touching the file).
    if validate_snippets:
        for slot, ad_id, snippet in (blocks or []):
            vr = validate_snippet(snippet)
            if not vr.ok:
                result["error"] = f"snippet invalid ({ad_id}): " + "; ".join(vr.errors)
                result["warnings"] = vr.warnings
                return result
            result["warnings"].extend(vr.warnings)

    try:
        original = _read_text(p)
    except Exception as exc:
        result["error"] = f"cannot read file: {exc}"
        return result

    eol = _detect_eol(original)
    new_text = original
    if remove_slots:
        new_text = remove_markers(new_text, remove_slots)
    if blocks:
        new_text = inject_markers(new_text, blocks)

    # Normalize line endings back to the original style.
    if eol == "\\r\
":
        new_text = new_text.replace("\\r\
", "\
").replace("\
", "\\r\
")
    else:
        new_text = new_text.replace("\\r\
", "\
")

    result["diff"] = dry_run(p, new_text)
    if new_text == original:
        result["ok"] = True
        result["changed"] = False
        return result

    # Backup before writing.
    backup = _backup_path(p)
    try:
        shutil.copy2(p, backup)
        result["backup"] = str(backup)
    except Exception as exc:
        result["error"] = f"backup failed: {exc}"
        return result

    # Atomic write: temp file in the same directory, then replace.
    tmp_fd, tmp_name = tempfile.mkstemp(prefix=f".{p.name}.", suffix=".tmp",
                                        dir=str(p.parent))
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(new_text)
        # Post-write validation on the in-memory content.
        if not _validate_result(new_text):
            raise RuntimeError("post-injection validation failed")
        os.replace(tmp_name, p)
    except Exception as exc:
        # Restore from backup.
        try:
            shutil.copy2(backup, p)
        except Exception:
            pass
        try:
            os.remove(tmp_name)
        except OSError:
            pass
        result["error"] = f"write failed, restored from backup: {exc}"
        return result

    result["ok"] = True
    result["changed"] = True
    return result


def rollback_file(path: str | Path) -> dict:
    """Restore the most recent backup of ``path``. Returns status dict."""
    p = Path(path)
    d = _backup_dir(p)
    if not d.exists():
        return {"ok": False, "error": "no backups found", "path": str(p)}
    backups = sorted(d.glob(f"{p.name}.*.bak"), key=lambda f: f.stat().st_mtime,
                     reverse=True)
    if not backups:
        return {"ok": False, "error": "no backups found", "path": str(p)}
    latest = backups[0]
    try:
        shutil.copy2(latest, p)
        return {"ok": True, "path": str(p), "restored_from": str(latest)}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "path": str(p)}


def list_backups(path: str | Path) -> list[Path]:
    p = Path(path)
    d = _backup_dir(p)
    if not d.exists():
        return []
    return sorted(d.glob(f"{p.name}.*.bak"),
                  key=lambda f: f.stat().st_mtime, reverse=True)
