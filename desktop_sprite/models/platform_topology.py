from __future__ import annotations

from desktop_sprite.models.platform import Platform


class PlatformTopology:
    @staticmethod
    def window_top_id(hwnd: int) -> str:
        return f"window:{hwnd}:top"

    @staticmethod
    def window_left_id(hwnd: int) -> str:
        return f"window:{hwnd}:left"

    @staticmethod
    def window_right_id(hwnd: int) -> str:
        return f"window:{hwnd}:right"

    @staticmethod
    def top_id_for_side_id(side_id: str) -> str:
        parts = side_id.split(":")
        return f"{parts[0]}:{parts[1]}:top" if len(parts) >= 3 else side_id

    @staticmethod
    def top_id_for_side(side: Platform) -> str:
        return PlatformTopology.top_id_for_side_id(side.id)

