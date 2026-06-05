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
