"""Application runtime.

`AppRuntime` replaces the previous 200-line `main()` that used nested
closures and `nonlocal` to share mutable state. Each runtime concern
(open main window, restart pet, request debug spirit mark, ...) is now a
regular method on the class, so the data flow is explicit and the
runtime can be reasoned about (and tested) without unravelling closures.

The runtime owns the long-lived objects of the app: the QApplication,
the desktop character, the sprite window, the target selector overlay,
the show overlay, the tray icon, and the (lazily-constructed) main
management window. Restarting the pet re-uses the same QApplication but
rebuilds the character and its dependent windows.

The names that `tests/test_app.py` monkey-patches
(`QApplication`, `QTimer`, `signal`, `sys.argv`, `load_config`, ...)
are not imported at module top here; they are looked up lazily through
the `desktop_sprite.app` package so that test-time patches take effect.
"""

from __future__ import annotations

import argparse
import logging
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMessageBox

from desktop_sprite.app.config_paths import RuntimePaths
from desktop_sprite.core.character import DesktopCharacter
from desktop_sprite.models.inventory import InventorySnapshot
from desktop_sprite.models.pet_attribute import PetAttributeSheet
from desktop_sprite.models.spirit_mark import (
    SpiritMarkGrantRequest,
    SpiritMarkInventory,
)
from desktop_sprite.ui.main_window import MainWindow
from desktop_sprite.ui.show_overlay import ShowOverlayWindow
from desktop_sprite.ui.sprite_window import SpriteWindow
from desktop_sprite.ui.target_selector import TargetSelectorOverlay
from desktop_sprite.ui.tray_controller import TrayController
from desktop_sprite.utils.config import AppConfig
from desktop_sprite.utils.logger import configure_logging


if TYPE_CHECKING:
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtWidgets import QApplication


logger = logging.getLogger(__name__)


def _app_symbols():
    """Look up the names the test suite monkey-patches.

    Importing this function lazily defers reading `desktop_sprite.app`
    attributes until after `__init__.py` has finished setting them up,
    and lets `monkeypatch.setattr(desktop_sprite.app, "X", fake)`
    propagate to the runtime's setup code.
    """

    import desktop_sprite.app as _pkg

    return {
        "Qt": _pkg.Qt,
        "QTimer": _pkg.QTimer,
        "QApplication": _pkg.QApplication,
        "signal": _pkg.signal,
        "sys": _pkg.sys,
        "load_config": _pkg.load_config,
        "configure_logging": _pkg.configure_logging,
        "create_character": _pkg.create_character,
        "SpriteWindow": _pkg.SpriteWindow,
        "TargetSelectorOverlay": _pkg.TargetSelectorOverlay,
        "ShowOverlayWindow": _pkg.ShowOverlayWindow,
        "TrayController": _pkg.TrayController,
        "MainWindow": _pkg.MainWindow,
        "load_inventory": _pkg.load_inventory,
        "load_spirit_mark_inventory": _pkg.load_spirit_mark_inventory,
        "save_spirit_mark_inventory": _pkg.save_spirit_mark_inventory,
        "grant_spirit_mark": _pkg.grant_spirit_mark,
    }


class AppRuntime:
    """Top-level runtime state.

    Lifecycle:
        1. `AppRuntime.from_default_args()` builds the instance from CLI.
        2. `run()` enters the Qt event loop.
        3. Lifecycle methods (`restart_pet`, `apply_runtime_config`,
           `quit_app`, ...) are invoked from the tray, the management
           window, or the in-app action cards.
    """

    def __init__(
        self,
        paths: RuntimePaths,
        qt_args: list[str],
        args: argparse.Namespace,
        config: AppConfig,
        app: "QApplication",
    ) -> None:
        self.paths = paths
        self.qt_args = qt_args
        self.args = args
        self.config = config
        self.app = app

        # Cache the test-monkey-patchable symbols once at construction.
        # Tests patch `desktop_sprite.app.*` *before* the runtime is
        # built, so the cache still picks up their fakes. Storing the
        # dict (not the individual names) keeps the cache local to the
        # runtime and avoids repeated dict constructions in hot paths.
        self._app_symbols: dict = _app_symbols()

        # Pet runtime state. Re-built by `restart_pet`.
        self.character: DesktopCharacter
        self.window: SpriteWindow
        self.target_selector: TargetSelectorOverlay
        self.show_overlay: ShowOverlayWindow

        # Persistent state read by the management window.
        self.spirit_marks: SpiritMarkInventory = self._app_symbols["load_spirit_mark_inventory"](
            paths.user_spirit_mark_path
        )
        self.inventory: InventorySnapshot | None = None

        # Lazily constructed — opening the management window is rare
        # and pulling up the FluentWindow pulls in heavy qfluentwidgets
        # imports we'd rather defer.
        self.main_window: MainWindow | None = None
        self.tray: TrayController

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_default_args(cls) -> "AppRuntime":
        """Build a runtime using the shipped default config and CLI args."""

        # Read every patchable symbol once before the runtime is built.
        # The runtime's `__init__` will cache the same dict on
        # `self._app_symbols` for use in the rest of the lifecycle.
        syms = _app_symbols()
        Qt = syms["Qt"]
        QTimer = syms["QTimer"]
        QApplication = syms["QApplication"]
        signal = syms["signal"]
        sys = syms["sys"]
        load_config = syms["load_config"]
        configure_logging = syms["configure_logging"]

        paths = RuntimePaths.resolve_default()
        config = load_config(paths.config_path, paths.user_config_path)
        args, qt_args = cls._parse_args(sys.argv[1:], config)
        configure_logging(config.app.log_level)

        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        app = QApplication([sys.argv[0], *qt_args])
        app.setApplicationName("Desktop Sprite")
        app.setQuitOnLastWindowClosed(False)
        signal.signal(signal.SIGINT, lambda *_a: app.quit())

        # Pump the Python interpreter regularly so SIGINT raised via
        # Ctrl+C in the console is observed even when Qt owns the loop.
        pump = QTimer()
        pump.timeout.connect(lambda: None)
        pump.start(100)

        return cls(paths, qt_args, args, config, app)

    @staticmethod
    def _parse_args(argv: list[str], config: AppConfig) -> tuple[argparse.Namespace, list[str]]:
        parser = argparse.ArgumentParser(add_help=True)
        parser.add_argument(
            "--character",
            choices=["pet"],
            default=config.character.default_type,
            help="Character implementation to run.",
        )
        return parser.parse_known_args(argv)

    # ------------------------------------------------------------------
    # Pet window lifecycle
    # ------------------------------------------------------------------

    def create_pet_window(
        self, runtime_config: AppConfig
    ) -> tuple[DesktopCharacter, SpriteWindow, TargetSelectorOverlay, ShowOverlayWindow]:
        """Build a fresh character + UI triple bound to the given config."""

        create_character = self._app_symbols["create_character"]
        SpriteWindow = self._app_symbols["SpriteWindow"]
        TargetSelectorOverlay = self._app_symbols["TargetSelectorOverlay"]
        ShowOverlayWindow = self._app_symbols["ShowOverlayWindow"]

        runtime_character = create_character(runtime_config, character_type=self.args.character)
        set_attribute_sheet = getattr(runtime_character, "set_attribute_sheet", None)
        if callable(set_attribute_sheet):
            set_attribute_sheet(
                PetAttributeSheet.from_config(runtime_config).with_modifiers(
                    self.spirit_marks.attribute_modifiers()
                )
            )
        runtime_window = SpriteWindow(runtime_character, runtime_config)
        runtime_character.set_own_window_handle(int(runtime_window.winId()))
        runtime_show_overlay = ShowOverlayWindow(runtime_character)
        # The show overlay shares the sprite window's tick. Passing
        # it in here keeps both windows in sync without a second timer.
        runtime_window.show_overlay = runtime_show_overlay
        return (
            runtime_character,
            runtime_window,
            TargetSelectorOverlay(runtime_character, runtime_config),
            runtime_show_overlay,
        )

    def start_show(self) -> None:
        """Entry point wired to the "展示" tray/menu action."""

        if self.character.start_show():
            self.target_selector.stop()
            self.show_overlay.start()

    def close_pet_runtime(self) -> None:
        """Stop the show overlay, target selector, and sprite window."""

        self.target_selector.stop()
        self.show_overlay.stop()
        self.window.close()

    # ------------------------------------------------------------------
    # Configuration changes
    # ------------------------------------------------------------------

    def restart_pet(self) -> None:
        """Rebuild the pet runtime from disk and reset dependent windows."""

        load_config = self._app_symbols["load_config"]
        configure_logging = self._app_symbols["configure_logging"]
        TrayController = self._app_symbols["TrayController"]

        try:
            new_config = load_config(self.paths.config_path, self.paths.user_config_path)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            QMessageBox.critical(self.main_window, "配置重载失败", str(exc))
            return

        self.close_pet_runtime()
        self.config = new_config
        configure_logging(self.config.app.log_level)
        self.character, self.window, self.target_selector, self.show_overlay = (
            self.create_pet_window(new_config)
        )
        self.tray = TrayController(  # Re-create to keep the on_open_window callback live.
            self.window,
            on_set_target=lambda: self.target_selector.start(),
            on_show=self.start_show,
            on_open_window=self.open_main_window,
        )
        self.tray.set_window(self.window)
        self.window.show()

    def apply_runtime_config(self) -> None:
        """Hot-apply config changes without rebuilding the pet runtime."""

        load_config = self._app_symbols["load_config"]
        configure_logging = self._app_symbols["configure_logging"]

        try:
            new_config = load_config(self.paths.config_path, self.paths.user_config_path)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            QMessageBox.critical(self.main_window, "配置重载失败", str(exc))
            return

        configure_logging(new_config.app.log_level)
        self.character.apply_config(new_config)
        self.window.apply_config(new_config)
        self.target_selector.apply_config(new_config)

    # ------------------------------------------------------------------
    # Management window
    # ------------------------------------------------------------------

    def open_main_window(self) -> None:
        """Lazily build the FluentWindow the first time it is requested."""

        load_inventory = self._app_symbols["load_inventory"]
        MainWindow = self._app_symbols["MainWindow"]

        if self.main_window is None:
            self.inventory = load_inventory(
                self.paths.config_path.with_name("items.json"),
                self.paths.user_inventory_path,
                self.paths.user_spirit_mark_path,
            )
            self.main_window = MainWindow(
                self.paths.config_path,
                on_set_target=lambda: self.target_selector.start(),
                on_show=self.start_show,
                on_sleep=lambda: self.character.sleep(),
                user_config_path=self.paths.user_config_path,
                on_restart=self.restart_pet,
                on_apply_config=self.apply_runtime_config,
                on_quit=self.quit_app,
                inventory_snapshot=self.inventory,
                spirit_mark_inventory=self.spirit_marks,
                pet_attribute_sheet=PetAttributeSheet.from_config(self.config),
                on_spirit_marks_changed=self.save_updated_spirit_marks,
                on_debug_request_spirit_mark=self.request_debug_spirit_mark,
            )
        self.main_window.open_home()

    def save_updated_spirit_marks(self, updated: SpiritMarkInventory) -> None:
        """Persist equipped/owned marks and reflect attribute changes."""

        save_spirit_mark_inventory = self._app_symbols["save_spirit_mark_inventory"]

        self.spirit_marks = updated
        save_spirit_mark_inventory(self.paths.user_spirit_mark_path, updated)
        set_attribute_sheet = getattr(self.character, "set_attribute_sheet", None)
        if callable(set_attribute_sheet):
            set_attribute_sheet(
                PetAttributeSheet.from_config(self.config).with_modifiers(
                    updated.attribute_modifiers()
                )
            )

    def request_debug_spirit_mark(self) -> str:
        """Mint a debug spirit mark end-to-end (write inventory + marks)."""

        grant_spirit_mark = self._app_symbols["grant_spirit_mark"]

        request = SpiritMarkGrantRequest(
            source_type="debug",
            source_id="management-debug",
            source_description=(
                "这道灵痕来自管理界面的一次调试请求，"
                "用于验证真实生成、入包和装备流程。"
            ),
            quality_hint="completed",
            record_tags=("debug", "management"),
        )
        result = grant_spirit_mark(
            request,
            items_path=self.paths.config_path.with_name("items.json"),
            inventory_path=self.paths.user_inventory_path,
            spirit_mark_path=self.paths.user_spirit_mark_path,
        )
        self.inventory = result.inventory_snapshot
        self.spirit_marks = result.spirit_mark_inventory
        if self.main_window is not None:
            self.main_window.update_inventory_and_spirit_marks(
                self.inventory, self.spirit_marks
            )
        return f"已生成灵痕：{result.mark.name}（{result.mark.entry_id}）"

    # ------------------------------------------------------------------
    # App shutdown
    # ------------------------------------------------------------------

    def quit_app(self) -> None:
        """Tear down every UI surface and request the event loop to stop."""

        self.close_pet_runtime()
        if self.main_window is not None:
            self.main_window.close()
        self.tray.tray.hide()
        self.app.quit()

    # ------------------------------------------------------------------
    # Event loop
    # ------------------------------------------------------------------

    def run(self) -> int:
        """Enter the Qt event loop and return its exit code."""

        TrayController = self._app_symbols["TrayController"]

        # Build the pet runtime for the first time using the loaded config.
        self.character, self.window, self.target_selector, self.show_overlay = (
            self.create_pet_window(self.config)
        )
        self.tray = TrayController(
            self.window,
            on_set_target=lambda: self.target_selector.start(),
            on_show=self.start_show,
            on_open_window=self.open_main_window,
        )
        self.tray.show()
        self.window.show()

        try:
            return self.app.exec()
        except KeyboardInterrupt:
            self.app.quit()
            return 130
