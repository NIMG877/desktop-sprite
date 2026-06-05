"""AI provider 抽象 + 错误分类 + 默认实现。

错误分类与重试策略（见 spec §6.1）：
  - AuthError      不重试、不计熔断
  - RateLimitError 重试 1 次（2s）、计熔断
  - TimeoutError   重试 1 次（4s）、计熔断
  - NetworkError   不重试、计熔断
  - BadRequestError 不重试、不 fallback（暴露 prompt bug）
  - ProviderDisabled 触发于 `ai.enabled=false`；不计熔断、不 fallback
"""
from __future__ import annotations

import time
import httpx
from abc import ABC, abstractmethod


class ProviderError(Exception):
    """所有 provider 错误的基类。"""


class ProviderDisabled(ProviderError):
    """`ai.enabled=false` 时构造的 DisabledProvider 抛此错。"""


class AuthError(ProviderError):
    """401 / 403。"""


class RateLimitError(ProviderError):
    """429。"""


class TimeoutError(ProviderError):
    """httpx 超时。"""


class NetworkError(ProviderError):
    """连接失败 / JSON 解析失败。"""


class BadRequestError(ProviderError):
    """400，prompt 模板有 bug 时暴露。"""


class AIProvider(ABC):
    """LLM 调用抽象。**同步阻塞**——必须被 worker 线程调用。"""

    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str, *, timeout: float = 30.0) -> str:
        ...

    @abstractmethod
    def generate_stream(
        self, system_prompt: str, user_prompt: str, *, timeout: float = 30.0,
    ):
        """返回 Iterator[str]，每段是 SSE delta 文本。必须被 worker 线程调用。"""
        ...

    @abstractmethod
    def ping(self, *, timeout: float = 5.0) -> float:
        """无 token 消耗的连通性探针。

        命中 `GET {base_url}/models`（OpenAI 兼容标准）：不调 LLM，只列
        元数据，**不消耗 token**。同时验证 base_url 可达、api_key 有效。

        返回：响应往返延迟（ms，浮点）。失败时抛 ProviderError 子类。
        """


class DisabledProvider(AIProvider):
    """`ai.enabled=false` 时的占位 provider；generate/ping 都抛 ProviderDisabled。"""

    def generate(self, system_prompt: str, user_prompt: str, *, timeout: float = 30.0) -> str:
        raise ProviderDisabled("AI is disabled in config")

    def generate_stream(
        self, system_prompt: str, user_prompt: str, *, timeout: float = 30.0,
    ):
        raise ProviderDisabled("AI is disabled in config")
        yield  # 让它成为 generator（不会被执行）

    def ping(self, *, timeout: float = 5.0) -> float:
        raise ProviderDisabled("AI is disabled in config")


class OpenAIProvider(AIProvider):
    """OpenAI 兼容 HTTP 接口的同步实现。

    请求体格式：`{model, messages, ...}`；响应解析 `choices[0].message.content`。
    错误按 HTTP 状态码分类：401/403→AuthError；429→RateLimitError；
    400→BadRequestError；5xx / 解析失败→NetworkError；超时→TimeoutError。
    """

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    def ping(self, *, timeout: float = 5.0) -> float:
        """GET /models：验证连通性与鉴权，不消耗 token。"""
        url = f"{self.base_url}/models"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        t0 = time.perf_counter()
        try:
            response = httpx.get(url, headers=headers, timeout=timeout)
        except httpx.TimeoutException as exc:
            raise TimeoutError(str(exc)) from exc
        except Exception as exc:
            raise NetworkError(str(exc)) from exc
        latency_ms = (time.perf_counter() - t0) * 1000.0

        if response.status_code in (401, 403):
            raise AuthError(f"auth failed: {response.status_code}")
        if response.status_code == 429:
            raise RateLimitError("rate limited")
        if response.status_code >= 500:
            raise NetworkError(f"server error: {response.status_code}")
        if response.status_code >= 400:
            raise NetworkError(f"http error: {response.status_code}")
        return latency_ms

    def generate(self, system_prompt: str, user_prompt: str, *, timeout: float = 30.0) -> str:
        url = f"{self.base_url}/chat/completions"
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = httpx.post(url, json=body, headers=headers, timeout=timeout)
        except httpx.TimeoutException as exc:
            raise TimeoutError(str(exc)) from exc
        except Exception as exc:
            raise NetworkError(str(exc)) from exc

        if response.status_code in (401, 403):
            raise AuthError(f"auth failed: {response.status_code}")
        if response.status_code == 429:
            raise RateLimitError("rate limited")
        if response.status_code == 400:
            raise BadRequestError(f"bad request: {response.text[:200]}")
        if response.status_code >= 500:
            raise NetworkError(f"server error: {response.status_code}")
        if response.status_code >= 400:
            raise NetworkError(f"http error: {response.status_code}")

        try:
            data = response.json()
        except Exception as exc:
            raise NetworkError(f"invalid json: {exc}") from exc

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise NetworkError(f"unexpected response shape: {exc}") from exc

    def generate_stream(
        self, system_prompt: str, user_prompt: str, *, timeout: float = 30.0,
    ):
        raise NotImplementedError("to be implemented in Task 4")
        yield
