import signal
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

from desktop_sprite.core.pet_controller import PetController
from desktop_sprite.ui.sprite_window import SpriteWindow
from desktop_sprite.utils.config import load_config
from desktop_sprite.utils.logger import configure_logging


def main() -> int:
    config = load_config()
    configure_logging(config.app.log_level)

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("Desktop Sprite")
    signal.signal(signal.SIGINT, lambda *_args: app.quit())

    interrupt_timer = QTimer()
    interrupt_timer.timeout.connect(lambda: None)
    interrupt_timer.start(100)

    controller = PetController(config)
    window = SpriteWindow(controller, config)
    controller.set_own_window_handle(int(window.winId()))
    window.show()

    try:
        return app.exec()
    except KeyboardInterrupt:
        app.quit()
        return 130
