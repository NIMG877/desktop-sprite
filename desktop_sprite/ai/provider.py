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


class DisabledProvider(AIProvider):
    """`ai.enabled=false` 时的占位 provider；generate 抛 ProviderDisabled。"""

    def generate(self, system_prompt: str, user_prompt: str, *, timeout: float = 30.0) -> str:
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
