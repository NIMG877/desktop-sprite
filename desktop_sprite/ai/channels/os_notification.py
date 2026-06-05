"""OsNotificationChannel——通过 QSystemTrayIcon.showMessage 弹系统通知。

tray 缺失时 no-op；调用 try/except 隔离异常。
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtWidgets import QSystemTrayIcon

from desktop_sprite.ai.channel import AIText, Channel


class OsNotificationChannel(Channel):
    def __init__(self, tray_provider: Callable[[], "QSystemTrayIcon | None"]) -> None:
        super().__init__(name="os_notification")
        self._tray_provider = tray_provider

    def dispatch(self, message: AIText) -> None:
        tray = self._tray_provider()
        if tray is None:
            return
        try:
            tray.showMessage(
                "桌宠小翼",
                message.text,
                QSystemTrayIcon.Information,
                5000,
            )
        except Exception:
            import logging
            logging.getLogger(__name__).warning(
                "OsNotificationChannel.showMessage failed", exc_info=True
            )
