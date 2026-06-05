import json

import pytest
from desktop_sprite.ai.provider import (
    AIProvider, DisabledProvider, OpenAIProvider, ProviderError,
    ProviderDisabled, AuthError, RateLimitError, TimeoutError, NetworkError, BadRequestError,
)


def test_abstract_provider_cannot_be_instantiated():
    with pytest.raises(TypeError):
        AIProvider()  # type: ignore[abstract]


def test_disabled_provider_generate_raises_provider_disabled():
    p = DisabledProvider()
    with pytest.raises(ProviderDisabled):
        p.generate("sys", "user", timeout=1.0)


def test_provider_error_hierarchy():
    assert issubclass(ProviderDisabled, ProviderError)
    assert issubclass(AuthError, ProviderError)
    assert issubclass(RateLimitError, ProviderError)
    assert issubclass(TimeoutError, ProviderError)
    assert issubclass(NetworkError, ProviderError)
    assert issubclass(BadRequestError, ProviderError)


def test_provider_error_default_message():
    err = AuthError("bad key")
    assert "bad key" in str(err)


class _FakeResponse:
    def __init__(self, status_code: int, body: dict | str) -> None:
        self.status_code = status_code
        self._body = body

    def json(self):
        if isinstance(self._body, dict):
            return self._body
        return json.loads(self._body)

    @property
    def text(self) -> str:
        return self._body if isinstance(self._body, str) else json.dumps(self._body, ensure_ascii=False)


class _FakeHttpx:
    """极简 httpx 替身：记录调用、按预设返回响应。"""

    def __init__(self, responses: list[_FakeResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        if not self._responses:
            raise RuntimeError("no more fake responses")
        return self._responses.pop(0)


@pytest.fixture
def patch_httpx(monkeypatch):
    def _patch(responses):
        fake = _FakeHttpx(responses)
        # OpenAIProvider 内部 import httpx；我们替换模块级 httpx
        import desktop_sprite.ai.provider as provider_mod
        monkeypatch.setattr(provider_mod, "httpx", fake)
        return fake
    return _patch


def test_openai_provider_success(patch_httpx):
    fake = patch_httpx([_FakeResponse(200, {
        "choices": [{"message": {"content": "你好呀"}}]
    })])
    p = OpenAIProvider(base_url="https://x/v1", api_key="k", model="m")
    out = p.generate("sys", "user", timeout=10.0)
    assert out == "你好呀"
    assert len(fake.calls) == 1
    body = fake.calls[0]["json"]
    assert body["model"] == "m"
    assert body["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "user"},
    ]
    assert fake.calls[0]["headers"]["Authorization"] == "Bearer k"


def test_openai_provider_401_raises_auth_error(patch_httpx):
    patch_httpx([_FakeResponse(401, {"error": {"message": "bad key"}})])
    p = OpenAIProvider(base_url="https://x/v1", api_key="bad", model="m")
    with pytest.raises(AuthError):
        p.generate("sys", "user")


def test_openai_provider_429_raises_rate_limit(patch_httpx):
    patch_httpx([_FakeResponse(429, {"error": {"message": "rate"}})])
    p = OpenAIProvider(base_url="https://x/v1", api_key="k", model="m")
    with pytest.raises(RateLimitError):
        p.generate("sys", "user")


def test_openai_provider_400_raises_bad_request(patch_httpx):
    patch_httpx([_FakeResponse(400, {"error": {"message": "bad prompt"}})])
    p = OpenAIProvider(base_url="https://x/v1", api_key="k", model="m")
    with pytest.raises(BadRequestError):
        p.generate("sys", "user")


def test_openai_provider_500_raises_network_error(patch_httpx):
    patch_httpx([_FakeResponse(500, {"error": {"message": "server"}})])
    p = OpenAIProvider(base_url="https://x/v1", api_key="k", model="m")
    with pytest.raises(NetworkError):
        p.generate("sys", "user")


def test_openai_provider_timeout_raises_timeout_error(patch_httpx):
    import httpx as real_httpx
    def boom(*a, **kw): raise real_httpx.TimeoutException("slow")
    import desktop_sprite.ai.provider as provider_mod
    provider_mod.httpx.post = boom
    p = OpenAIProvider(base_url="https://x/v1", api_key="k", model="m")
    with pytest.raises(TimeoutError):
        p.generate("sys", "user")


def test_openai_provider_invalid_json_raises_network_error(patch_httpx):
    patch_httpx([_FakeResponse(200, "not json {{{")])
    p = OpenAIProvider(base_url="https://x/v1", api_key="k", model="m")
    with pytest.raises(NetworkError):
        p.generate("sys", "user")
