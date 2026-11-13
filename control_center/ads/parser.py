"""control_center/ads/parser.py — تحليل Snippets الإعلانات (Monetag وغيرها).

يستقبل snippet خام (كما يُلصق من لوحة المونتاج) ويستخرج:
  • data-zone  → معرف المنطقة (zone)
  • data-sdk   → اسم الدالة/global function التي يُستدعى عبرها (show_XXXX)
  • src        → رابط السكربت (يُحتفظ به كما هو، inclusively protocol-relative)

النص يُخزّن كما هو دون إعادة كتابة (byte-exact). لا يُفترض اسم دالة ثابت ولا نطاق ثابت.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# <script ... data-zone="..." data-sdk="..." ... src="..."> (أي ترتيب للسُمات)
_SCRIPT_TAG_RE = re.compile(
    r"<script\b[^>]*?>", re.IGNORECASE | re.DOTALL
)
_ATTR_RE = re.compile(
    r"(data-zone|data-sdk|src)\s*=\s*(['\"])(.*?)\2", re.IGNORECASE
)

# التوكن المشبوه (توكن بوت) — يُرفض بداخله snippet
_TOKEN_LIKE = re.compile(r"\b\d{5,}:[A-Za-z0-9_-]{20,}\b")

# أنماط خطيرة مرفوضة完全ًا في snippet الإعلاني
_DANGEROUS = (
    (re.compile(r"\beval\s*\(", re.I), "يستخدم eval()"),
    (re.compile(r"document\.write\s*\(", re.I), "يستخدم document.write()"),
    (re.compile(r"window\.location\s*=\s*['\"]", re.I), "إعادة توجيه كاملة للصفحة"),
    (re.compile(r"location\.href\s*=\s*['\"]", re.I), "إعادة توجيه كاملة للصفحة"),
    (re.compile(r"location\.replace\s*\(", re.I), "إعادة توجيه كاملة للصفحة"),
    (re.compile(r"atob\s*\(", re.I), "تفكيك base64 (إخفاء/تشويش)"),
    (re.compile(r"String\.fromCharCode", re.I), "إخفاء بالأحرف الرمزية"),
)


@dataclass
class ParsedSnippet:
    """نتيجة تحليل snippet إعلاني."""
    ok: bool = False
    zone_id: Optional[str] = None
    sdk_name: Optional[str] = None
    raw_script_src: Optional[str] = None
    snippet: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    size_bytes: int = 0

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "zone_id": self.zone_id,
            "sdk_name": self.sdk_name,
            "raw_script_src": self.raw_script_src,
            "snippet": self.snippet,
            "errors": self.errors,
            "warnings": self.warnings,
            "size_bytes": self.size_bytes,
        }


def _extract_attrs(tag: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for m in _ATTR_RE.finditer(tag):
        key = m.group(1).lower()
        value = m.group(3)
        attrs[key] = value
    return attrs


def parse_snippet(snippet: str, *, size_limit: int = 65536) -> ParsedSnippet:
    """
    حلل snippet إعلاني وأعد كائن ParsedSnippet.

    القواعد:
      • النص يُخزّن كما هو (verbatim) — لا إعادة كتابة.
      • يجب أن يحتوي على وسم <script> واحد على الأقل.
      • يُستخرج data-zone و data-sdk إذا وُجدا (اختياريان).
      • يُستخرج src إذا وُجد (incl. //protocol-relative).
      • تُرفض الأنماط الخطرة (eval, document.write, re-directions, obfuscation).
      • تُرفض التوكنات الشبيهة بتوكنات البوت.
      • حد حجم افتراضي 64 كيلو بايت.
    """
    result = ParsedSnippet()
    text = snippet or ""
    result.snippet = text
    result.size_bytes = len(text.encode("utf-8"))

    if not text.strip():
        result.errors.append("ال snippet فارغ")
        return result

    if result.size_bytes > size_limit:
        result.errors.append(
            f"الحجم أكبر من المسموح: {result.size_bytes} > {size_limit} بايت")
        return result

    if _TOKEN_LIKE.search(text):
        result.errors.append("يحتوي على ما يبدو مثل توكن بوت — مرفوض")
        return result

    for rx, msg in _DANGEROUS:
        if rx.search(text):
            result.errors.append("نمط خطر: " + msg)
            return result

    # وسوم السكربت
    script_tags = _SCRIPT_TAG_RE.findall(text)
    if not script_tags:
        result.errors.append("لا يحتوي على وسم <script>")
        return result

    # 분석 السمة من أول وسم script
    attrs = _extract_attrs(script_tags[0])
    result.zone_id = attrs.get("data-zone") or None
    result.sdk_name = attrs.get("data-sdk") or None
    result.raw_script_src = attrs.get("src") or None

    # تحذيرات مساعدة (ليست أخطاء)
    if result.raw_script_src and not result.raw_script_src.startswith(("http://", "https://", "//")):
        result.warnings.append("رابط السكربت ليس http/https/protocol-relative: " + result.raw_script_src)
    if not result.zone_id:
        result.warnings.append("لا يوجد data-zone — لن يتم ربط الإعلان بمنطقة مونتاج محددة")
    if not result.sdk_name:
        result.warnings.append("لا يوجد data-sdk — لن يُعرف اسم دالة العرض")

    result.ok = True
    return result


def snippet_for_db(snippet: str) -> dict:
    """
    أعد قاموسًا مهيّأً للحفظ في مكتبة الإعلانات (Ad):
    snippet verbatim + الحقول المستخرجة.
    """
    parsed = parse_snippet(snippet)
    return {
        "snippet": parsed.snippet,
        "zone_id": parsed.zone_id,
        "sdk_name": parsed.sdk_name,
        "raw_script_src": parsed.raw_script_src,
        "parsed_ok": parsed.ok,
        "parse_errors": parsed.errors,
        "parse_warnings": parsed.warnings,
        "size_bytes": parsed.size_bytes,
    }
