"""进程内同步 pub/sub。

设计取舍：用纯 Python dict-of-handlers 实现，不走 Qt Signal。Signal
不支持动态 topic 名 + 任意 callable 组合；dict 模式最直接。Handler
抛错在 `publish` 时被隔离，单个坏 handler 不影响其他订阅者或调用方。
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Callable


logger = logging.getLogger(__name__)


class EventBus:
    """同步 pub/sub，按 topic 字符串索引 handler 列表。"""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[[Any], None]]] = defaultdict(list)

    def subscribe(
        self, topic: str, handler: Callable[[Any], None]
    ) -> Callable[[], None]:
        """注册 handler；返回反订阅 callable。多次调用幂等。"""
        self._handlers[topic].append(handler)

        def unsubscribe() -> None:
            try:
                self._handlers[topic].remove(handler)
            except ValueError:
                pass

        return unsubscribe

    def publish(self, topic: str, payload: Any) -> None:
        """在调用方线程同步派发；handler 抛错被隔离并记录 warning。"""
        for handler in list(self._handlers.get(topic, ())):
            try:
                handler(payload)
            except Exception:
                logger.warning(
                    "EventBus handler for %r raised; isolating", topic, exc_info=True
                )
