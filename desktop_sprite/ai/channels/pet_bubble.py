"""PetBubbleChannel——把 AIText 推到 BubbleOverlayWindow。"""
from __future__ import annotations

from desktop_sprite.ai.channel import AIText, Channel


class PetBubbleChannel(Channel):
    """桌宠气泡 channel。`overlay` 由外部构造后注入。"""

    def __init__(self, overlay) -> None:
        super().__init__(name="pet_bubble")
        self._overlay = overlay

    def dispatch(self, message: AIText) -> None:
        self._overlay.show_message(message)
