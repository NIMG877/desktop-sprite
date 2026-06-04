"""Application package — entry point for the desktop pet runtime.

`desktop_sprite.app.main` is the canonical CLI entry; `AppRuntime` is
the long-lived runtime class. The package also re-exports the
Qt/PySide6 and project-specific symbols that `tests/test_app.py`
monkey-patches when running headless.

Symbols are imported here at module top so `monkeypatch.setattr(
desktop_sprite.app, "X", fake)` succeeds when X is one of the
patch targets. The runtime module reads these names lazily through
this package so the patches propagate to its setup code.
"""

import signal
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

from desktop_sprite.app.config_paths import RuntimePaths
from desktop_sprite.app.runtime import AppRuntime
from desktop_sprite.core.character_factory import create_character
from desktop_sprite.models.inventory import load_inventory
from desktop_sprite.models.spirit_mark import (
    SpiritMarkGrantRequest,
    SpiritMarkInventory,
    load_spirit_mark_inventory,
    save_spirit_mark_inventory,
)
from desktop_sprite.models.spirit_mark_service import grant_spirit_mark
from desktop_sprite.ui.main_window import MainWindow
from desktop_sprite.ui.show_overlay import ShowOverlayWindow
from desktop_sprite.ui.sprite_window import SpriteWindow
from desktop_sprite.ui.target_selector import TargetSelectorOverlay
from desktop_sprite.ui.tray_controller import TrayController
from desktop_sprite.utils.config import load_config
from desktop_sprite.utils.logger import configure_logging


def main() -> int:
    """Build a default-config runtime and enter the event loop."""

    return AppRuntime.from_default_args().run()


__all__ = [
    "AppRuntime",
    "MainWindow",
    "QApplication",
    "Qt",
    "QTimer",
    "RuntimePaths",
    "ShowOverlayWindow",
    "SpriteWindow",
    "TargetSelectorOverlay",
    "TrayController",
    "configure_logging",
    "create_character",
    "grant_spirit_mark",
    "load_config",
    "load_inventory",
    "load_spirit_mark_inventory",
    "main",
    "save_spirit_mark_inventory",
    "signal",
    "sys",
    "SpiritMarkGrantRequest",
    "SpiritMarkInventory",
]
