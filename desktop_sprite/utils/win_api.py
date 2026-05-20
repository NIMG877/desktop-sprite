from __future__ import annotations

import ctypes


def is_windows() -> bool:
    return hasattr(ctypes, "windll")
