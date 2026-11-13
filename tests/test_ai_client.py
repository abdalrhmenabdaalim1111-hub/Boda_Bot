# =============================================================================
#  tests/test_ai_client.py — اختبارات عميل الذكاء الاصطناعي الموحّد
#  تغطي: قراءة الإعدادات، المسار عبر SDK، المسار البديل (requests)، الأخطاء
# =============================================================================
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "Bots_Folder"))

import ai_client


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """بيئة نظيفة لكل اختبار + تفريغ ذاكرة العميل المؤقتة."""
    for var in ("COARENA_BASE_URL", "COARENA_API_KEY", "COARENA_MODEL", "COARENA_TIMEOUT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("COARENA_API_KEY", "test-key")
    ai_client.reset_client()
    yield
    ai_client.reset_client()


# ── قراءة الإعدادات ───────────────────────────────────────────────────────────

class TestSettings:
    def test_defaults(self):
        assert ai_client.base_url() == "https://coarena.ai/api/v1"
        assert ai_client.model_name() == "claude-fable-5"
        assert ai_client.timeout() == 60

    def test_env_overrides(self, monkeypatch):
        monkeypatch.setenv("COARENA_BASE_URL", "https://example.com/api/v1/")
        monkeypatch.setenv("COARENA_MODEL", "grok-4-7")
        monkeypatch.setenv("COARENA_TIMEOUT", "12")
        assert ai_client.base_url() == "https://example.com/api/v1"  # بلا شرطة أخيرة
        assert ai_client.model_name() == "grok-4-7"
        assert ai_client.timeout() == 12

    def test_invalid_timeout_falls_back(self, monkeypatch):
        monkeypatch.setenv("COARENA_TIMEOUT", "abc")
        assert ai_client.timeout() == 60

    def test_missing_key_raises(self, monkeypatch):
        monkeypatch.delenv("COARENA_API_KEY", raising=False)
        with pytest.raises(ai_client.AIError):
            ai_client._cached_client()


# ── المسار عبر مكتبة openai ───────────────────────────────────────────────────

class TestSdkPath:
    def _fake_client(self, content="مرحباً"):
        client = MagicMock()
        message = MagicMock()
        message.content = content
        choice = MagicMock()
        choice.message = message
        choice.finish_reason = "stop"
        reply = MagicMock()
        reply.choices = [choice]
        reply.model = "claude-fable-5"
        reply.usage = {"total_tokens": 12}
        client.chat.completions.create.return_value = reply
        return client

    def test_chat_returns_text(self):
        client = self._fake_client("نص الرد")
        with patch.object(ai_client, "_cached_client", return_value=client):
            assert ai_client.chat("مرحبا") == "نص الرد"

    def test_chat_sends_user_message(self):
        client = self._fake_client()
        with patch.object(ai_client, "_cached_client", return_value=client):
            ai_client.chat("سؤال المستخدم")
        payload = client.chat.completions.create.call_args.kwargs
        assert payload["model"] == "claude-fable-5"
        assert payload["messages"] == [{"role": "user", "content": "سؤال المستخدم"}]

    def test_chat_with_system_message(self):
        client = self._fake_client()
        with patch.object(ai_client, "_cached_client", return_value=client):
            ai_client.chat("سؤال", system="أنت مساعد")
        messages = client.chat.completions.create.call_args.kwargs["messages"]
        assert messages[0] == {"role": "system", "content": "أنت مساعد"}
        assert messages[1] == {"role": "user", "content": "سؤال"}

    def test_chat_messages_passes_extra_params(self):
        client = self._fake_client()
        with patch.object(ai_client, "_cached_client", return_value=client):
            ai_client.chat_messages([{"role": "user", "content": "x"}],
                                    temperature=0.2, max_tokens=64)
        payload = client.chat.completions.create.call_args.kwargs
        assert payload["temperature"] == 0.2
        assert payload["max_tokens"] == 64

    def test_complete_returns_metadata(self):
        client = self._fake_client("محتوى")
        with patch.object(ai_client, "_cached_client", return_value=client):
            result = ai_client.complete([{"role": "user", "content": "x"}])
        assert result["content"] == "محتوى"
        assert result["model"] == "claude-fable-5"
        assert result["finish_reason"] == "stop"
        assert result["usage"] == {"total_tokens": 12}

    def test_sdk_error_wrapped(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = RuntimeError("boom")
        with patch.object(ai_client, "_cached_client", return_value=client):
            with pytest.raises(ai_client.AIError):
                ai_client.chat("x")

    def test_empty_messages_rejected(self):
        with pytest.raises(ai_client.AIError):
            ai_client.complete([])


# ── المسار البديل عبر requests ───────────────────────────────────────────────

class TestRequestsFallback:
    def test_fallback_posts_correct_payload(self):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "model": "claude-fable-5",
            "choices": [{"message": {"content": "رد بديل"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 5},
        }
        with patch.object(ai_client, "_cached_client", return_value=None), \
             patch("requests.post", return_value=response) as post:
            assert ai_client.chat("سؤال") == "رد بديل"

        args, kwargs = post.call_args
        assert args[0] == "https://coarena.ai/api/v1/chat/completions"
        assert kwargs["json"]["model"] == "claude-fable-5"
        assert kwargs["headers"]["Authorization"] == "Bearer test-key"

    def test_fallback_http_error(self):
        response = MagicMock()
        response.status_code = 401
        response.text = "unauthorized"
        with patch.object(ai_client, "_cached_client", return_value=None), \
             patch("requests.post", return_value=response):
            with pytest.raises(ai_client.AIError) as exc:
                ai_client.chat("x")
        assert "401" in str(exc.value)

    def test_fallback_network_error(self):
        with patch.object(ai_client, "_cached_client", return_value=None), \
             patch("requests.post", side_effect=OSError("no network")):
            with pytest.raises(ai_client.AIError):
                ai_client.chat("x")

    def test_list_models_fallback(self):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"data": [{"id": "a"}, {"id": "b"}]}
        with patch.object(ai_client, "_cached_client", return_value=None), \
             patch("requests.get", return_value=response):
            assert ai_client.list_models() == ["a", "b"]


# ── أدوات مساعدة ─────────────────────────────────────────────────────────────

class TestHelpers:
    def test_as_text_plain_string(self):
        assert ai_client._as_text("نص") == "نص"

    def test_as_text_blocks(self):
        assert ai_client._as_text([{"type": "text", "text": "أ"}, {"text": "ب"}]) == "أب"

    def test_as_text_none(self):
        assert ai_client._as_text(None) == ""

    def test_usage_dict_none(self):
        assert ai_client._usage_dict(None) == {}

    def test_ping_success(self):
        with patch.object(ai_client, "chat", return_value="pong"):
            result = ai_client.ping()
        assert result["ok"] is True
        assert result["reply"] == "pong"
        assert result["latency_ms"] >= 0

    def test_ping_failure(self):
        with patch.object(ai_client, "chat", side_effect=ai_client.AIError("down")):
            result = ai_client.ping()
        assert result["ok"] is False
        assert "down" in result["reply"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
