"""
tests/test_ads_parser.py — اختبارات محول snippet الإعلانات (مرحلة 2).

يغطي:
  • استخراج data-zone / data-sdk / src من snippet مونتاج (اقتباس مفرد/مزدوج، رابط نسبي للبروتوكول)
  • الحفاظ على النص كما هو (verbatim)
  • رفض الوسائط الخطرة (eval, document.write, إعادة توجيه، تشويش)
  • رفض التوكنات الشبيهة بتوكنات البوت
  • وسوم script مفقودة / نص فارغ
"""
import pytest

from control_center.ads.parser import parse_snippet, snippet_for_db


def _mk(zone="12250058", sdk="show_12250058", src="//libtl.com/sdk.js", quote="'"):
    return (f"<script src={quote}{src}{quote} "
            f"data-zone={quote}{zone}{quote} "
            f"data-sdk={quote}{sdk}{quote}></script>")


def test_parse_monetag_single_quote():
    """ snippet بمonetag تقليدي (اقتباس مفرد)."""
    p = parse_snippet(_mk())
    assert p.ok is True
    assert p.zone_id == "12250058"
    assert p.sdk_name == "show_12250058"
    assert p.raw_script_src == "//libtl.com/sdk.js"


def test_parse_monetag_double_quote():
    """ snippet بمonetag تقليد (اقتباس مزدوج)."""
    p = parse_snippet(_mk(quote='"'))
    assert p.ok is True
    assert p.zone_id == "12250058"
    assert p.sdk_name == "show_12250058"


def test_parse_protocol_relative_src():
    """ src يبدأ بـ // (نسبي للبروتوكول) يُقبل ويُحفظ كما هو."""
    p = parse_snippet(_mk(src="//cdn.monetag.com/sdk.js"))
    assert p.ok is True
    assert p.raw_script_src == "//cdn.monetag.com/sdk.js"


def test_parse_https_src():
    """ src عادي HTTPS يُقبل."""
    p = parse_snippet(_mk(src="https://libtl.com/sdk.js"))
    assert p.ok is True
    assert p.raw_script_src == "https://libtl.com/sdk.js"


def test_snippet_preserved_verbatim():
    """ النص يُخزّن كما هو دون أي تعديل."""
    raw = _mk()
    p = parse_snippet(raw)
    assert p.snippet == raw


def test_snippet_for_db_contains_verbatim():
    """ snippet_for_db يعيد snippet كما هو."""
    raw = _mk()
    db = snippet_for_db(raw)
    assert db["snippet"] == raw
    assert db["zone_id"] == "12250058"
    assert db["sdk_name"] == "show_12250058"
    assert db["parsed_ok"] is True


def test_empty_snippet_rejected():
    p = parse_snippet("")
    assert p.ok is False
    assert "فارغ" in " ".join(p.errors)


def test_no_script_tag_rejected():
    p = parse_snippet("just some text without script")
    assert p.ok is False
    assert any("script" in e for e in p.errors)


def test_eval_rejected():
    p = parse_snippet("<script>eval('bad')</script>")
    assert p.ok is False
    assert any("eval" in e.lower() for e in p.errors)


def test_document_write_rejected():
    p = parse_snippet("<script>document.write('x')</script>")
    assert p.ok is False
    assert any("document.write" in e.lower() for e in p.errors)


def test_location_redirect_rejected():
    p = parse_snippet("<script>window.location='https://evil.com'</script>")
    assert p.ok is False
    assert any("إعادة توجيه" in e for e in p.errors)


def test_atob_obfuscation_rejected():
    p = parse_snippet("<script>atob('YQ==')</script>")
    assert p.ok is False
    assert any("base64" in e.lower() for e in p.errors)


def test_bot_token_like_rejected():
    p = parse_snippet("<script src='x.js'>123456789:AAAABBBBCCCCDDDDEEEEFFFFGGGGHHHHIIII</script>")
    assert p.ok is False
    assert any("توكن" in e for e in p.errors)


def test_missing_zone_is_warning_not_error():
    """ غياب data-zone تحذير لا خطأ — snippet لا يزال صالحًا."""
    p = parse_snippet("<script src='//libtl.com/sdk.js' data-sdk='show_x'></script>")
    assert p.ok is True
    assert p.zone_id is None
    assert p.sdk_name == "show_x"
    assert any("data-zone" in w for w in p.warnings)


def test_missing_sdk_is_warning_not_error():
    p = parse_snippet("<script src='//libtl.com/sdk.js' data-zone='123'></script>")
    assert p.ok is True
    assert p.sdk_name is None
    assert any("data-sdk" in w for w in p.warnings)


def test_different_zone_and_sdk_names():
    """每个 snippet يمكن أن يحمل منطقة ودالة مختلفة."""
    p = parse_snippet(_mk(zone="777", sdk="custom_show_777"))
    assert p.ok is True
    assert p.zone_id == "777"
    assert p.sdk_name == "custom_show_777"


def test_size_limit():
    """ snippet كبير جداً يُرفض."""
    big = "<script src='//x.js' data-zone='1' data-sdk='s1'>" + "A" * 70000 + "</script>"
    p = parse_snippet(big, size_limit=65536)
    assert p.ok is False
    assert any("أكبر" in e or "size" in e.lower() for e in p.errors)
