import argparse
import signal
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from desktop_sprite.core.character_factory import create_character
from desktop_sprite.models.inventory import load_inventory
from desktop_sprite.ui.main_window import MainWindow
from desktop_sprite.ui.show_overlay import ShowOverlayWindow
from desktop_sprite.ui.sprite_window import SpriteWindow
from desktop_sprite.ui.target_selector import TargetSelectorOverlay
from desktop_sprite.ui.tray_controller import TrayController
from desktop_sprite.utils.config import AppConfig, load_config
from desktop_sprite.utils.logger import configure_logging


def _parse_args(argv: list[str], config: AppConfig) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument(
        "--character",
        choices=["pet"],
        default=config.character.default_type,
        help="Character implementation to run.",
    )
    return parser.parse_known_args(argv)


def main() -> int:
    config_path = Path(__file__).resolve().parents[1] / "config" / "default.json"
    user_config_path = config_path.with_name("user.json")
    inventory = load_inventory(
        config_path.with_name("items.json"),
        config_path.with_name("default_inventory.json"),
        config_path.with_name("inventory.json"),
    )
    config = load_config(config_path, user_config_path)
    args, qt_args = _parse_args(sys.argv[1:], config)
    configure_logging(config.app.log_level)

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName("Desktop Sprite")
    app.setQuitOnLastWindowClosed(False)
    signal.signal(signal.SIGINT, lambda *_args: app.quit())

    interrupt_timer = QTimer()
    interrupt_timer.timeout.connect(lambda: None)
    interrupt_timer.start(100)

    def create_runtime(runtime_config: AppConfig):
        runtime_character = create_character(runtime_config, character_type=args.character)
        runtime_window = SpriteWindow(runtime_character, runtime_config)
        runtime_character.set_own_window_handle(int(runtime_window.winId()))
        return (
            runtime_character,
            runtime_window,
            TargetSelectorOverlay(runtime_character, runtime_config),
            ShowOverlayWindow(runtime_character),
        )

    character, window, target_selector, show_overlay = create_runtime(config)

    def start_show() -> None:
        if character.start_show():
            target_selector.stop()
            show_overlay.start()

    def close_pet_runtime() -> None:
        target_selector.stop()
        show_overlay.stop()
        window.close()

    def quit_app() -> None:
        close_pet_runtime()
        main_window.hide()
        tray.tray.hide()
        app.quit()

    def restart_pet() -> None:
        nonlocal config, character, window, target_selector, show_overlay
        try:
            new_config = load_config(config_path, user_config_path)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            QMessageBox.critical(main_window, "配置重载失败", str(exc))
            return

        close_pet_runtime()
        config = new_config
        configure_logging(config.app.log_level)
        character, window, target_selector, show_overlay = create_runtime(config)
        tray.set_window(window)
        window.show()

    def apply_runtime_config() -> None:
        try:
            new_config = load_config(config_path, user_config_path)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            QMessageBox.critical(main_window, "配置重载失败", str(exc))
            return

        configure_logging(new_config.app.log_level)
        character.apply_config(new_config)
        window.apply_config(new_config)
        target_selector.apply_config(new_config)

    main_window = MainWindow(
        config_path,
        on_set_target=lambda: target_selector.start(),
        on_show=start_show,
        on_sleep=lambda: character.sleep(),
        user_config_path=user_config_path,
        on_restart=restart_pet,
        on_apply_config=apply_runtime_config,
        on_quit=quit_app,
        inventory_snapshot=inventory,
    )

    tray = TrayController(
        window,
        on_set_target=lambda: target_selector.start(),
        on_show=start_show,
        on_open_window=main_window.open_home,
        owner=main_window,
    )
    tray.show()
    window.show()

    try:
        return app.exec()
    except KeyboardInterrupt:
        app.quit()
        return 130
