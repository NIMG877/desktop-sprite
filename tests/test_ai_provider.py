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


# ----------------------------------------------------------------------------
# ping() — GET /models, no token cost
# ----------------------------------------------------------------------------


class _FakeHttpxGet(_FakeHttpx):
    """_FakeHttpx 的 GET 版：post 不可用，get 走同一套响应队列。"""

    def get(self, url, headers=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "timeout": timeout})
        if not self._responses:
            raise RuntimeError("no more fake responses")
        return self._responses.pop(0)


@pytest.fixture
def patch_httpx_get(monkeypatch):
    def _patch(responses):
        fake = _FakeHttpxGet(responses)
        import desktop_sprite.ai.provider as provider_mod
        monkeypatch.setattr(provider_mod, "httpx", fake)
        return fake
    return _patch


def test_openai_provider_ping_success_returns_latency(patch_httpx_get):
    fake = patch_httpx_get([_FakeResponse(200, {"data": [{"id": "m"}]})])
    p = OpenAIProvider(base_url="https://x/v1", api_key="k", model="m")
    ms = p.ping(timeout=2.0)
    assert ms >= 0
    assert fake.calls[0]["url"] == "https://x/v1/models"
    assert fake.calls[0]["headers"]["Authorization"] == "Bearer k"


def test_openai_provider_ping_401_raises_auth_error(patch_httpx_get):
    patch_httpx_get([_FakeResponse(401, {"error": "bad key"})])
    p = OpenAIProvider(base_url="https://x/v1", api_key="bad", model="m")
    with pytest.raises(AuthError):
        p.ping()


def test_openai_provider_ping_429_raises_rate_limit_error(patch_httpx_get):
    patch_httpx_get([_FakeResponse(429, {"error": "rate"})])
    p = OpenAIProvider(base_url="https://x/v1", api_key="k", model="m")
    with pytest.raises(RateLimitError):
        p.ping()


def test_openai_provider_ping_timeout_raises_timeout_error(monkeypatch):
    import httpx as real_httpx
    import desktop_sprite.ai.provider as provider_mod
    class _BoomHttpx:
        TimeoutException = real_httpx.TimeoutException
        def get(self, *a, **kw): raise self.TimeoutException("slow")
    monkeypatch.setattr(provider_mod, "httpx", _BoomHttpx())
    p = OpenAIProvider(base_url="https://x/v1", api_key="k", model="m")
    with pytest.raises(TimeoutError):
        p.ping()


def test_disabled_provider_ping_raises_provider_disabled():
    p = DisabledProvider()
    with pytest.raises(ProviderDisabled):
        p.ping()


# ----------------------------------------------------------------------------
# generate_stream() — abstract method declaration (Task 2)
# ----------------------------------------------------------------------------


def test_abstract_provider_must_implement_generate_stream():
    """未实现 generate_stream 不能实例化。"""
    with pytest.raises(TypeError):
        AIProvider()  # 触发 ABC 检查


def test_disabled_provider_stream_raises_provider_disabled():
    p = DisabledProvider()
    with pytest.raises(ProviderDisabled):
        # generator 第一次 next() 时抛
        next(p.generate_stream("s", "u"))


# ----------------------------------------------------------------------------
# generate_stream() — SSE streaming (Task 4)
# ----------------------------------------------------------------------------


class _FakeStreamChunk:
    """httpx 的 stream chunk 替身；iter_lines() 期望的是字节/str。"""
    def __init__(self, text: str):
        self.text = text

    def iter_lines(self):
        for line in self.text.split("\n"):
            yield line


class _FakeStreamContext:
    def __init__(self, chunks: list[str], status_code: int = 200):
        self._chunks = chunks
        self.status_code = status_code

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def send(self, request):
        # 模拟 httpx.stream 进入时发送请求，返回 response-like
        return _FakeStreamResponse(self.status_code, self._chunks)


class _FakeStreamResponse:
    def __init__(self, status_code, chunks):
        self.status_code = status_code
        self._chunks = chunks

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def iter_lines(self):
        for c in self._chunks:
            for line in c.split("\n"):
                yield line


class _FakeHttpxStream:
    def __init__(self, chunks, status_code=200):
        import httpx as real_httpx
        self.TimeoutException = real_httpx.TimeoutException
        self._chunks = chunks
        self._status = status_code
        self.calls: list[dict] = []

    def stream(self, method, url, json=None, headers=None, timeout=None):
        self.calls.append({
            "method": method, "url": url, "json": json,
            "headers": headers, "timeout": timeout,
        })
        return _FakeStreamResponse(self._status, self._chunks)


def _patch_stream(monkeypatch, chunks, status_code=200):
    fake = _FakeHttpxStream(chunks, status_code)
    import desktop_sprite.ai.provider as provider_mod
    monkeypatch.setattr(provider_mod, "httpx", fake)
    return fake


def test_openai_provider_stream_yields_deltas(monkeypatch):
    sse = (
        'data: {"choices":[{"delta":{"content":"你"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"好"}}]}\n\n'
        'data: [DONE]\n\n'
    )
    _patch_stream(monkeypatch, [sse])
    p = OpenAIProvider(base_url="https://x/v1", api_key="k", model="m")
    deltas = list(p.generate_stream("sys", "usr"))
    assert deltas == ["你", "好"]


def test_openai_provider_stream_401_raises_auth_error(monkeypatch):
    sse = "data: [DONE]\n\n"
    _patch_stream(monkeypatch, [sse], status_code=401)
    p = OpenAIProvider(base_url="https://x/v1", api_key="k", model="m")
    from desktop_sprite.ai.provider import AuthError
    with pytest.raises(AuthError):
        list(p.generate_stream("sys", "usr"))


def test_openai_provider_stream_sends_stream_flag(monkeypatch):
    sse = "data: [DONE]\n\n"
    fake = _patch_stream(monkeypatch, [sse])
    p = OpenAIProvider(base_url="https://x/v1", api_key="k", model="m")
    list(p.generate_stream("sys", "usr"))
    body = fake.calls[0]["json"]
    assert body["stream"] is True
    assert body["model"] == "m"
    assert body["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "usr"},
    ]
