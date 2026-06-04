"""UseCase 声明式注册。

UseCase 把"订阅哪个事件 / 用什么 prompt 模板 / 投到哪些 channel /
节流多少毫秒 / 失败时用什么 fallback 文案"打包成一个不可变记录。
Orchestrator 通过 `UseCaseRegistry` 按 topic 反查。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class UseCase:
    """声明式用例记录。"""

    use_case_id: str
    event_topic: str
    prompt_template: str
    target_channels: tuple[str, ...]
    throttle_ms: int = 0
    fallback_text: str | None = None


class UseCaseRegistry:
    """按 use_case_id 与 event_topic 双索引。"""

    def __init__(self) -> None:
        self._by_id: dict[str, UseCase] = {}
        self._by_topic: dict[str, list[UseCase]] = {}

    def register(self, use_case: UseCase) -> None:
        # 同 id 重复注册则覆盖；旧条目从 topic 索引中移除
        old = self._by_id.get(use_case.use_case_id)
        if old is not None:
            lst = self._by_topic.get(old.event_topic, [])
            if old in lst:
                lst.remove(old)
        self._by_id[use_case.use_case_id] = use_case
        self._by_topic.setdefault(use_case.event_topic, []).append(use_case)

    def get(self, use_case_id: str) -> UseCase | None:
        return self._by_id.get(use_case_id)

    def for_topic(self, topic: str) -> list[UseCase]:
        return list(self._by_topic.get(topic, ()))
