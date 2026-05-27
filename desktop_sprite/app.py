import argparse
import signal
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

from desktop_sprite.core.character_factory import create_character
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
    config = load_config()
    args, qt_args = _parse_args(sys.argv[1:], config)
    configure_logging(config.app.log_level)

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName("Desktop Sprite")
    signal.signal(signal.SIGINT, lambda *_args: app.quit())

    interrupt_timer = QTimer()
    interrupt_timer.timeout.connect(lambda: None)
    interrupt_timer.start(100)

    character = create_character(config, character_type=args.character)
    window = SpriteWindow(character, config)
    character.set_own_window_handle(int(window.winId()))
    target_selector = TargetSelectorOverlay(character, config)
    tray = TrayController(window, on_set_target=target_selector.start)
    tray.show()
    window.show()

    try:
        return app.exec()
    except KeyboardInterrupt:
        app.quit()
        return 130
