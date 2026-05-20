from __future__ import annotations

from dataclasses import dataclass

from desktop_sprite.models.geometry import Rect


@dataclass(frozen=True, slots=True)
class WindowInfo:
    hwnd: int
    title: str
    rect: Rect
    visible: bool
    minimized: bool
    is_foreground: bool
    class_name: str = ""
