import json
from pathlib import Path

import httpx
import pytest

from covenants.providers import FakeProvider, GroqProvider, ProviderError, ReplayProvider, get_provider
from covenants.schemas import ExtractionDraft


def test_missing_key_is_explicit():
    with pytest.raises(ProviderError, match="not configured"):
        GroqProvider("test-model")


def test_unknown_provider_and_path_traversal_rejected():
    for name in ("unknown", "replay:../../private"):
        with pytest.raises(ProviderError):
            get_provider(name)


def test_mocked_real_provider_structured_output_usage_and_secrecy():
    def handler(request):
        body = json.loads(request.content)
        assert body["response_format"]["json_schema"]["strict"] is True
        assert body["model"] == "test-model"
        assert "tools" not in body
        assert "untrusted" in body["messages"][0]["content"]
        assert "not-a-real-key" not in request.content.decode()
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": '{"covenants": []}'}}],
                                         "usage": {"prompt_tokens": 100, "completion_tokens": 20}})
    provider = GroqProvider("test-model", api_key="not-a-real-key", transport=httpx.MockTransport(handler))
    result, usage = provider.generate("{}", ExtractionDraft)
    assert result.covenants == []
    assert usage.input_tokens == 100
    assert usage.output_tokens == 20
    assert usage.latency_ms >= 0


@pytest.mark.parametrize("failure", ["invalid_json", "truncated", "unauthorized", "timeout"])
def test_real_provider_failures_sanitized(failure):
    def handler(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("sensitive request detail")
        if failure == "unauthorized":
            return httpx.Response(401, json={"error": "sensitive request detail"})
        return httpx.Response(200, json={"choices": [{"finish_reason": "length" if failure == "truncated" else "stop",
                                                       "message": {"content": "not JSON"}}]})
    provider = GroqProvider("test", api_key="private-value", transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError) as error:
        provider.generate("{}", ExtractionDraft)
    assert "private-value" not in str(error.value)
    assert "sensitive request detail" not in str(error.value)


def test_retry_is_bounded(monkeypatch):
    calls = []
    def handler(request):
        calls.append(1)
        return httpx.Response(429, headers={"retry-after": "1000"})
    monkeypatch.setattr("covenants.providers.groq.time.sleep", lambda value: None)
    provider = GroqProvider("test", api_key="private", transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError, match="429"):
        provider.generate("{}", ExtractionDraft)
    assert len(calls) == 2


def test_replay_missing_is_an_error(tmp_path):
    with pytest.raises(ProviderError, match="manifest"):
        ReplayProvider(tmp_path)
    (tmp_path / "manifest.json").write_text(json.dumps({"model": "fake"}))
    provider = ReplayProvider(tmp_path)
    with pytest.raises(ProviderError, match="missing"):
        provider.generate("{}", ExtractionDraft)


def test_recording_detects_wrong_identity(tmp_path):
    provider = ReplayProvider(tmp_path, FakeProvider())
    prompt = json.dumps({"clauses": []})
    provider.generate(prompt, ExtractionDraft)
    path = next(p for p in tmp_path.glob("*.json") if p.name != "manifest.json")
    value = json.loads(path.read_text())
    value["key"] = "wrong"
    path.write_text(json.dumps(value))
    with pytest.raises(ProviderError, match="identity"):
        ReplayProvider(tmp_path).generate(prompt, ExtractionDraft)

