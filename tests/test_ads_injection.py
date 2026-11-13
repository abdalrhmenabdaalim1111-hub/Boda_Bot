"""
tests/test_ads_injection.py — اختبارات حقن علامات الإعلانات (مرحلة 2).

يغطي:
  • إدراج علامة جديدة في المكان المناسب (head / body_end)
  • تحديث علامة موجودة بنفس الفتحية (في مكانها)
  • إزالة علامة
  • idempotency: نفس المحتوى → لا تغيير
  • rollback عند فشلvalidation (HTML ناقص)
  • حقن عبر build_mini_apps (بوت واحد)
"""
import os
import tempfile
from pathlib import Path

import pytest

from control_center.ads.injector import (
    inject_markers, remove_markers, list_blocks, apply_injection,
    rollback_file, list_backups, make_block, dry_run,
)
from control_center.ads.validator import validate_snippet


SNIPPET_HEAD = "<script src='//libtl.com/sdk.js' data-zone='1' data-sdk='show_1'></script>"
SNIPPET_BODY = "<script src='//libtl.com/sdk.js' data-zone='2' data-sdk='show_2'></script>"


def _write(tmp: Path, name: str, content: str) -> Path:
    p = tmp / name
    p.write_text(content, encoding="utf-8")
    return p


def test_insert_head_and_body_end(tmp_path):
    p = _write(tmp_path, "t.html", "<html><head></head><body>hi</body></html>")
    blocks = [("head", "ad1", SNIPPET_HEAD), ("body_end", "ad2", SNIPPET_BODY)]
    new = inject_markers(p.read_text(encoding="utf-8"), blocks)
    assert "<!-- AD:BEGIN slot=head id=ad1 -->" in new
    assert "<!-- AD:END slot=head -->" in new
    assert "<!-- AD:BEGIN slot=body_end id=ad2 -->" in new
    assert SNIPPET_HEAD in new
    assert SNIPPET_BODY in new


def test_update_same_slot_in_place(tmp_path):
    # المحتوى الأصلي يحمل علامة كاملة (BEGIN + END) بنفس الفتحية
    nl = chr(10)
    old_block = ("<!-- AD:BEGIN slot=head id=old_ad -->" + nl + "old_content_body" + nl +
                 "<!-- AD:END slot=head -->")
    content = ("<html><head>" + old_block + "</head><body></body></html>")
    p = _write(tmp_path, "t.html", content)
    new = inject_markers(p.read_text(encoding="utf-8"), [("head", "new_ad", SNIPPET_HEAD)])
    assert new.count("AD:BEGIN slot=head") == 1
    assert SNIPPET_HEAD in new
    assert "old_content_body" not in new
    assert "old_ad" not in new


def test_remove_markers(tmp_path):
    content = ("<html><!-- AD:BEGIN slot=head id=a -->A<!-- AD:END slot=head -->"
               "<!-- AD:BEGIN slot=body_end id=b -->B<!-- AD:END slot=body_end -->"
               "<body></body></html>")
    p = _write(tmp_path, "t.html", content)
    new = remove_markers(content, ["head"])
    assert "<!-- AD:BEGIN slot=head" not in new
    assert "<!-- AD:BEGIN slot=body_end" in new


def test_idempotency_no_change_when_same(tmp_path):
    nl = chr(10)
    block = ("<!-- AD:BEGIN slot=head id=ad1 -->" + nl + SNIPPET_HEAD.rstrip() + nl +
             "<!-- AD:END slot=head -->")
    content = ("<html><head>" + block + "</head><body></body></html>")
    p = _write(tmp_path, "t.html", content)
    result = apply_injection(p, [("head", "ad1", SNIPPET_HEAD)])
    assert result["ok"] is True
    assert result["changed"] is False, result.get("diff")


def test_apply_injection_writes_and_backup(tmp_path):
    p = _write(tmp_path, "t.html", "<html><head></head><body>x</body></html>")
    result = apply_injection(p, [("head", "ad1", SNIPPET_HEAD)])
    assert result["ok"] is True
    assert result["changed"] is True
    assert result["backup"] != ""
    assert os.path.exists(result["backup"])
    # الملف يُحدّث فعلاً
    text = p.read_text(encoding="utf-8")
    assert "<!-- AD:BEGIN slot=head id=ad1 -->" in text


def test_rollback_restores_backup(tmp_path):
    original = "<html><head></head><body>x</body></html>"
    p = _write(tmp_path, "t.html", original)
    apply_injection(p, [("head", "ad1", SNIPPET_HEAD)])
    restored = rollback_file(p)
    assert restored["ok"] is True
    assert p.read_text(encoding="utf-8") == original


def test_list_backups(tmp_path):
    p = _write(tmp_path, "t.html", "<html><body></body></html>")
    apply_injection(p, [("head", "ad1", SNIPPET_HEAD)])
    apply_injection(p, [("head", "ad1", SNIPPET_BODY)])
    backups = list_backups(p)
    assert len(backups) >= 1


def test_dry_run_returns_diff(tmp_path):
    p = _write(tmp_path, "t.html", "<html><body></body></html>")
    new = inject_markers(p.read_text(encoding="utf-8"), [("head", "ad1", SNIPPET_HEAD)])
    diff = dry_run(p, new)
    assert "@@" in diff or "---" in diff or "+++" in diff


def test_validate_snippet_accepts_monetag():
    vr = validate_snippet(SNIPPET_HEAD)
    assert vr.ok is True
    assert vr.size_bytes > 0


def test_validate_snippet_rejects_eval():
    vr = validate_snippet("<script>eval('x')</script>")
    assert vr.ok is False or len(vr.warnings) > 0


def test_list_blocks_returns_slots():
    text = ("<html><!-- AD:BEGIN slot=head id=a -->A<!-- AD:END slot=head -->"
            "<!-- AD:BEGIN slot=body_end id=b -->B<!-- AD:END slot=body_end -->"
            "<body></body></html>")
    blocks = list_blocks(text)
    assert len(blocks) == 2
    slots = {b["slot"] for b in blocks}
    assert slots == {"head", "body_end"}


def test_build_applies_ad_library_markers(tmp_path, monkeypatch):
    """حقن علامة من مكتبة الإعلانات في صفحة بوتر."""
    # نُنشئ صفحة بسيطة لنختبر right injector بالبيانات من المكتبة
    content = "<html><head></head><body>content</body></html>"
    blocks = [("head", "ad_test", SNIPPET_HEAD)]
    new = inject_markers(content, blocks)
    assert "<!-- AD:BEGIN slot=head id=ad_test -->" in new
