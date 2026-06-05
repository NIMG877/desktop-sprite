"""ChatPanelChannel——把 AIText 追加到 AIPanelWidget。

panel 由外部 lazy 构造（主窗首次打开时才建），所以 channel 持有一个
`Callable[[], AIPanelWidget | None]` provider，dispatch 时取一下。
panel 未开 → no-op。
"""
from __future__ import annotations

from typing import Callable

from desktop_sprite.ai.channel import AIText, Channel


class ChatPanelChannel(Channel):
    def __init__(self, panel_provider: Callable[[], "object | None"]) -> None:
        super().__init__(name="chat_panel")
        self._panel_provider = panel_provider

    def dispatch(self, message: AIText) -> None:
        panel = self._panel_provider()
        if panel is None:
            return
        panel.append_history(message)

    def dispatch_stream_start(self, stream_id: str, use_case_id: str) -> None:
        panel = self._panel_provider()
        if panel is None:
            return
        panel.append_stream_start(stream_id, use_case_id)

    def dispatch_stream_delta(
        self, stream_id: str, delta: str, use_case_id: str,
    ) -> None:
        panel = self._panel_provider()
        if panel is None:
            return
        panel.append_stream_delta(stream_id, delta, use_case_id)

    def dispatch_stream_end(
        self, stream_id: str, full_text: str, source: str, use_case_id: str,
    ) -> None:
        panel = self._panel_provider()
        if panel is None:
            return
        panel.append_stream_end(stream_id, full_text, source, use_case_id)
