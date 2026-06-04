"""Channel 抽象与 AIText 数据对象。

Channel 是 LLM 文案的"呈现端"抽象；Orchestrator 不关心每个 channel
长啥样，只调 `dispatch(AIText)`。子类必须实现 `dispatch`。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AIText:
    """Orchestrator → Channel 的不可变数据单元。

    `source` 区分 `ai`（provider 正常返回）和 `fallback`（provider 失败
    走 use_case 的 fallback_text）。
    """

    text: str
    source: str  # "ai" / "fallback"
    use_case_id: str
    timestamp: float


class Channel(ABC):
    """呈现端抽象。`dispatch` 必须在主线程被调。"""

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def dispatch(self, message: AIText) -> None:
        ...
