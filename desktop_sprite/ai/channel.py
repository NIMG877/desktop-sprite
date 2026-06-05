"""Channel 抽象与 AIText 数据对象。

Channel 是 LLM 文案的"呈现端"抽象；Orchestrator 不关心每个 channel
长啥样，只调 `dispatch(AIText)`（一次性）或
`dispatch_stream_start/delta/end`（流式）。子类必须实现 `dispatch`；
3 个流式钩子默认 no-op，按需重写。
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
    """呈现端抽象。所有 dispatch* 方法必须在主线程被调。"""

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def dispatch(self, message: AIText) -> None:
        ...

    # 流式钩子（默认 no-op；Channel 选择性重写）

    def dispatch_stream_start(self, stream_id: str, use_case_id: str) -> None:
        pass

    def dispatch_stream_delta(
        self, stream_id: str, delta: str, use_case_id: str,
    ) -> None:
        pass

    def dispatch_stream_end(
        self, stream_id: str, full_text: str, source: str, use_case_id: str,
    ) -> None:
        pass
