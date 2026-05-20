from __future__ import annotations

from desktop_sprite.models.geometry import Rect


def qt_primary_screen_rects() -> tuple[Rect, Rect] | None:
    try:
        from PySide6.QtGui import QGuiApplication
    except Exception:
        return None

    screen = QGuiApplication.primaryScreen()
    if screen is None:
        return None

    geometry = screen.geometry()
    available = screen.availableGeometry()
    return (
        Rect(geometry.left(), geometry.top(), geometry.right() + 1, geometry.bottom() + 1),
        Rect(available.left(), available.top(), available.right() + 1, available.bottom() + 1),
    )


def qt_primary_screen_scale(physical_screen_width: float | None = None) -> float:
    qt_rects = qt_primary_screen_rects()
    if qt_rects is None:
        return 1.0

    qt_screen, _ = qt_rects
    if qt_screen.width <= 0:
        return 1.0

    if physical_screen_width is not None and physical_screen_width > qt_screen.width:
        return physical_screen_width / qt_screen.width

    try:
        from PySide6.QtGui import QGuiApplication
    except Exception:
        return 1.0

    screen = QGuiApplication.primaryScreen()
    if screen is None:
        return 1.0
    return float(screen.devicePixelRatio())


def normalize_win32_rect_to_qt(rect: Rect, physical_screen_width: float) -> Rect:
    qt_rects = qt_primary_screen_rects()
    if qt_rects is None:
        return rect

    qt_screen, _ = qt_rects
    if qt_screen.width <= 0:
        return rect

    scale = qt_primary_screen_scale(physical_screen_width)
    if scale <= 1.01:
        return rect

    return Rect(
        rect.left / scale,
        rect.top / scale,
        rect.right / scale,
        rect.bottom / scale,
    )
