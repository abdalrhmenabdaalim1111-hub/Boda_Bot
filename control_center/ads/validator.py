"""control_center/ads/validator.py — ad snippet validation."""

import re
from dataclasses import dataclass, field

from .. import config

_CHECKED_TAGS = ("script", "div", "span", "a", "iframe", "style", "section")
_VOID = {"br", "hr", "img", "input", "meta", "link", "col", "embed", "source"}

_DANGEROUS = (
    (re.compile(r"\beval\s*\("), "uses eval()"),
    (re.compile(r"document\.write\s*\([^)]*https?://", re.I),
     "document.write of remote content"),
    (re.compile(r"window\.location\s*=\s*['\"]https?://", re.I),
     "full-page redirect"),
    (re.compile(r"location\.href\s*=\s*['\"]https?://", re.I),
     "full-page redirect"),
    (re.compile(r"atob\s*\("), "base64 decoding (obfuscation)"),
    (re.compile(r"String\.fromCharCode"), "char-code obfuscation"),
)

_TOKEN_LIKE = re.compile(r"\b\d{5,}:[A-Za-z0-9_-]{20,}\b")

_SCRIPT_SRC_RE = re.compile(
    r"<script[^>]*\bsrc\s*=\s*['\"]([^'\"]+)['\"]", re.I)


def _balanced_tags(snippet):
    problems = []
    for tag in _CHECKED_TAGS:
        opens = len(re.findall(rf"<{tag}(?:\s[^>]*)?>", snippet, re.I))
        closes = len(re.findall(rf"</{tag}\s*>", snippet, re.I))
        self_close = len(re.findall(rf"<{tag}[^>]*/>", snippet, re.I))
        if opens - self_close != closes:
            problems.append("unbalanced <{}>: {} open, {} close".format(tag, opens, closes))
    return problems


@dataclass
class ValidationResult:
    ok: bool = True
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    size_bytes: int = 0

    def to_dict(self):
        return {"ok": self.ok, "errors": self.errors,
                "warnings": self.warnings, "size_bytes": self.size_bytes}


def validate_snippet(snippet, *, size_limit=None, allowed_domains=None):
    result = ValidationResult()
    text = snippet or ""
    result.size_bytes = len(text.encode("utf-8"))

    limit = size_limit if size_limit is not None else config.ad_max_size_bytes()
    if not text.strip():
        result.ok = False
        result.errors.append("snippet is empty")
        return result
    if result.size_bytes > limit:
        result.ok = False
        result.errors.append(
            "snippet too large: {} > {} bytes".format(result.size_bytes, limit))

    if _TOKEN_LIKE.search(text):
        result.ok = False
        result.errors.append(
            "snippet contains something that looks like a bot token - refused")

    for problem in _balanced_tags(text):
        result.warnings.append(problem)

    for rx, msg in _DANGEROUS:
        if rx.search(text):
            result.warnings.append("dangerous pattern: " + msg)

    domains = allowed_domains if allowed_domains is not None else config.ad_allowed_domains()
    if domains:
        allowed = {d.lower() for d in domains}
        for m in _SCRIPT_SRC_RE.finditer(text):
            src = m.group(1)
            try:
                host = src.split("//", 1)[-1].split("/", 1)[0].lower()
            except Exception:
                host = ""
            if host and host not in allowed:
                if not any(host == d or host.endswith("." + d) for d in allowed):
                    result.warnings.append("script domain not in allow-list: " + host)
    else:
        for m in _SCRIPT_SRC_RE.finditer(text):
            src = m.group(1)
            if src.startswith("http"):
                result.warnings.append(
                    "external script (allow-list is empty): " +
                    src.split("//")[-1].split("/")[0])

    if result.errors:
        result.ok = False
    return result
