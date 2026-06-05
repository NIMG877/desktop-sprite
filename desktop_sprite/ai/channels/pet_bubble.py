"""PetBubbleChannel——把 AIText 推到桌宠头顶 BubbleOverlayWindow。

bubble 由外部构造（桌宠启动时建），channel 持 callable lazy 拿。
"""
from __future__ import annotations

from typing import Callable

from desktop_sprite.ai.channel import AIText, Channel


class PetBubbleChannel(Channel):
    def __init__(self, bubble_provider: Callable[[], "object | None"]) -> None:
        super().__init__(name="pet_bubble")
        self._bubble_provider = bubble_provider

    def dispatch(self, message: AIText) -> None:
        bubble = self._bubble_provider()
        if bubble is None:
            return
        bubble.show_message(message.text)

    def dispatch_stream_start(self, stream_id: str, use_case_id: str) -> None:
        bubble = self._bubble_provider()
        if bubble is None:
            return
        bubble.show_message("")

    def dispatch_stream_delta(
        self, stream_id: str, delta: str, use_case_id: str,
    ) -> None:
        bubble = self._bubble_provider()
        if bubble is None:
            return
        bubble.append_text(delta)

    def dispatch_stream_end(
        self, stream_id: str, full_text: str, source: str, use_case_id: str,
    ) -> None:
        # 不主动关；BubbleOverlayWindow 自己有 hide timer 流期间被 append_text
        # 不断 reset；end 后没有新 delta，timer 走完自动隐藏。
        pass
