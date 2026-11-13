# =============================================================================
#  Bots_Folder/ai_client.py — عميل ذكاء اصطناعي موحّد (واجهة متوافقة مع OpenAI)
# =============================================================================
"""
ai_client.py — نقطة وصول واحدة لكل البوتات للاتصال بواجهة CoArena.

لماذا هذا الملف؟
    كل بوت يحتاج الاتصال بنفس الـ endpoint وبنفس المفتاح. توحيد الوصول هنا
    يمنع تكرار كود الاتصال في عشرات الملفات، ويجعل تدوير المفتاح سهلاً
    (تعديل متغيّر بيئة واحد بدل تعديل كل بوت).

الإعدادات (متغيّرات بيئة — لا تُكتب الأسرار داخل الكود أبداً):
    COARENA_BASE_URL   عنوان الـ API   (افتراضي: https://coarena.ai/api/v1)
    COARENA_API_KEY    مفتاح الـ API  (مطلوب)
    COARENA_MODEL      اسم النموذج    (افتراضي: claude-fable-5)
    COARENA_TIMEOUT    مهلة الطلب بالثواني (افتراضي: 60)

الاستخدام::

    from ai_client import chat, chat_messages

    reply = chat("اكتب لي جملة تحفيزية قصيرة")
    reply = chat_messages([
        {"role": "system", "content": "أنت مساعد عربي موجز"},
        {"role": "user",   "content": "اشرح لي الذكاء الاصطناعي بجملة واحدة"},
    ])

ملاحظة مهمّة:
    إن لم تكن مكتبة ``openai`` مثبّتة، يعمل الملف تلقائياً عبر ``requests``
    (وهو اعتماد قائم في المشروع أصلاً) — فلا ينكسر تشغيل البوتات بسببها.
"""
import logging
import os
from pathlib import Path

# تحميل .env (نفس نمط bot_base.py) — يُتجاهل إن لم تكن المكتبة متوفرة
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except Exception:  # pragma: no cover — بيئة بلا python-dotenv
    pass

log = logging.getLogger("ai_client")

# ── القيم الافتراضية ──────────────────────────────────────────────────────────
DEFAULT_BASE_URL = "https://coarena.ai/api/v1"
DEFAULT_MODEL = "claude-fable-5"
DEFAULT_TIMEOUT = 60


class AIError(RuntimeError):
    """أي خطأ أثناء الاتصال بواجهة الذكاء الاصطناعي (شبكة، مصادقة، أو ردّ)."""


# ── قراءة الإعدادات ───────────────────────────────────────────────────────────
def base_url() -> str:
    """عنوان الـ API بلا شرطة أخيرة."""
    return (os.getenv("COARENA_BASE_URL", "").strip() or DEFAULT_BASE_URL).rstrip("/")


def api_key() -> str:
    """مفتاح الـ API (يُقرأ من متغيّر البيئة — لا يُخزَّن في الكود)."""
    return os.getenv("COARENA_API_KEY", "").strip()


def model_name() -> str:
    """اسم النموذج الافتراضي المستخدم في الطلبات."""
    return os.getenv("COARENA_MODEL", "").strip() or DEFAULT_MODEL


def timeout() -> int:
    """مهلة الطلب بالثواني."""
    try:
        return max(1, int(os.getenv("COARENA_TIMEOUT", "").strip() or DEFAULT_TIMEOUT))
    except ValueError:
        return DEFAULT_TIMEOUT


# ── إدارة العميل ─────────────────────────────────────────────────────────────
_CLIENT = None
_CLIENT_KEY = None


def reset_client() -> None:
    """يُفرغ الذاكرة المؤقتة للعميل (مفيد بعد تغيير المفتاح أو في الاختبارات)."""
    global _CLIENT, _CLIENT_KEY
    _CLIENT = None
    _CLIENT_KEY = None


def _cached_client():
    """
    يُعيد عميل OpenAI من الذاكرة المؤقتة، أو None إن لم تكن المكتبة مثبّتة.

    يُنشئ العميل من جديد تلقائياً عند تغيّر العنوان أو المفتاح.
    """
    global _CLIENT, _CLIENT_KEY
    key = (base_url(), api_key())
    if not key[1]:
        raise AIError("COARENA_API_KEY غير مضبوط — أضفه في ملف .env")
    if _CLIENT is not None and _CLIENT_KEY == key:
        return _CLIENT
    try:
        from openai import OpenAI
    except ImportError:
        return None
    _CLIENT = OpenAI(base_url=key[0], api_key=key[1],
                     timeout=timeout(), max_retries=2)
    _CLIENT_KEY = key
    return _CLIENT


def get_client():
    """
    عميل OpenAI مربوط بعنوان CoArena.

    Raises:
        AIError: إذا كانت مكتبة ``openai`` غير مثبّتة أو المفتاح غير مضبوط.
    """
    client = _cached_client()
    if client is None:
        raise AIError("مكتبة openai غير مثبّتة — ثبّتها: pip install openai")
    return client


# ── أدوات مساعدة ─────────────────────────────────────────────────────────────
def _as_text(content) -> str:
    """يحوّل محتوى الردّ (نص أو كتل) إلى نص عادي."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text") or "")
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return ""


def _usage_dict(usage) -> dict:
    """يحوّل عدّاد الاستخدام إلى قاموس (يتحمّل None أو كائن SDK)."""
    if usage is None:
        return {}
    if isinstance(usage, dict):
        return usage
    for attr in ("model_dump", "to_dict", "dict"):
        fn = getattr(usage, attr, None)
        if callable(fn):
            try:
                return fn()
            except Exception:
                continue
    return {}


# ── إرسال الطلبات ─────────────────────────────────────────────────────────────
def _complete_via_requests(payload: dict) -> dict:
    """بديل خفيف عبر ``requests`` يُستخدم إن لم تكن مكتبة openai مثبّتة."""
    import requests

    url = f"{base_url()}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key()}",
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=timeout())
    except Exception as e:
        raise AIError(f"تعذّر الاتصال بـ {url}: {e}") from e
    if resp.status_code >= 400:
        raise AIError(f"HTTP {resp.status_code} من {url}: {resp.text[:300]}")
    try:
        data = resp.json()
    except Exception as e:
        raise AIError(f"ردّ غير صالح من {url}: {e}") from e

    choices = data.get("choices") or []
    content, finish = "", None
    if choices:
        first = choices[0] or {}
        content = _as_text((first.get("message") or {}).get("content"))
        finish = first.get("finish_reason")
    return {
        "content": content,
        "model": data.get("model") or payload.get("model"),
        "finish_reason": finish,
        "usage": data.get("usage") or {},
    }


def complete(messages, *, model=None, temperature=None, max_tokens=None,
             **extra) -> dict:
    """
    يرسل قائمة رسائل ويعيد تفاصيل الردّ كاملة.

    Args:
        messages: قائمة رسائل بالشكل القياسي OpenAI.
        model: اسم النموذج (افتراضي: COARENA_MODEL).
        temperature / max_tokens / extra: معاملات اختيارية تُمرَّر كما هي.

    Returns:
        dict: ``{"content", "model", "finish_reason", "usage"}``

    Raises:
        AIError: عند غياب المفتاح أو فشل الطلب.
    """
    if not messages:
        raise AIError("لا يمكن إرسال طلب بلا رسائل")

    payload = {"model": model or model_name(), "messages": list(messages)}
    if temperature is not None:
        payload["temperature"] = temperature
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    payload.update(extra)

    client = _cached_client()
    if client is None:
        # لا مكتبة openai → المسار البديل عبر requests
        return _complete_via_requests(payload)

    try:
        reply = client.chat.completions.create(**payload)
    except Exception as e:
        raise AIError(f"فشل الطلب من {base_url()}: {e}") from e

    choices = getattr(reply, "choices", None) or []
    message = getattr(choices[0], "message", None) if choices else None
    return {
        "content": _as_text(getattr(message, "content", "")),
        "model": getattr(reply, "model", None) or payload["model"],
        "finish_reason": getattr(choices[0], "finish_reason", None) if choices else None,
        "usage": _usage_dict(getattr(reply, "usage", None)),
    }


def chat_messages(messages, **kwargs) -> str:
    """يرسل قائمة رسائل ويعيد نص الردّ فقط."""
    return complete(messages, **kwargs)["content"]


def chat(prompt, system=None, **kwargs) -> str:
    """
    يرسل نصّاً واحداً ويعيد نص الردّ.

    Args:
        prompt: نص المستخدم.
        system: رسالة نظام اختيارية (تُضاف قبل رسالة المستخدم).
    """
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return chat_messages(messages, **kwargs)


def list_models() -> list:
    """أسماء النماذج المتاحة على الواجهة (قائمة نصوص)."""
    client = _cached_client()
    if client is not None:
        try:
            page = client.models.list()
            data = getattr(page, "data", page)
            return [getattr(m, "id", None) or (m.get("id") if isinstance(m, dict) else str(m))
                    for m in data]
        except Exception as e:
            raise AIError(f"فشل جلب قائمة النماذج: {e}") from e

    import requests
    url = f"{base_url()}/models"
    try:
        resp = requests.get(url, headers={"Authorization": f"Bearer {api_key()}"},
                            timeout=timeout())
    except Exception as e:
        raise AIError(f"تعذّر الاتصال بـ {url}: {e}") from e
    if resp.status_code >= 400:
        raise AIError(f"HTTP {resp.status_code} من {url}: {resp.text[:300]}")
    data = resp.json()
    return [m.get("id", "") for m in (data.get("data") or [])]


def ping(prompt: str = "ping") -> dict:
    """
    فحص سريع لاتصال الواجهة — مفيد في التشخيص (``dev_tools.py diagnose``).

    Returns:
        dict: ``{"ok", "model", "latency_ms", "reply"}`` — ``ok=False`` عند الفشل.
    """
    import time

    started = time.perf_counter()
    try:
        reply = chat(prompt, max_tokens=32)
        latency = int((time.perf_counter() - started) * 1000)
        return {"ok": True, "model": model_name(), "latency_ms": latency,
                "reply": reply}
    except Exception as e:
        latency = int((time.perf_counter() - started) * 1000)
        return {"ok": False, "model": model_name(), "latency_ms": latency,
                "reply": str(e)}


# ── اختبار سريع ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    print(f"🔗 base_url : {base_url()}")
    print(f"🤖 model    : {model_name()}")
    print(f"🔑 key      : {'مضبوط ✅' if api_key() else 'غير مضبوط ❌'}")

    try:
        print("📋 النماذج المتاحة:")
        for name in list_models()[:10]:
            print(f"   • {name}")
    except Exception as e:
        print(f"⚠ تعذّر جلب النماذج: {e}")

    result = ping()
    if result["ok"]:
        print(f"✅ الاتصال يعمل ({result['latency_ms']}ms) — الرد: {result['reply'][:120]}")
    else:
        print(f"❌ فشل الاتصال: {result['reply']}")
