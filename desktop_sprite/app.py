import argparse
import signal
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from desktop_sprite.core.character_factory import create_character
from desktop_sprite.models.inventory import load_inventory
from desktop_sprite.models.pet_attribute import PetAttributeSheet
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
    user_config_dir = config_path.parent / "user"
    user_config_path = user_config_dir / "user.json"
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
    main_window: MainWindow | None = None

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
        if main_window is not None:
            main_window.close()
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

    def open_main_window() -> None:
        nonlocal main_window
        if main_window is None:
            user_inventory_path = user_config_dir / "inventory.json"
            user_spirit_mark_path = user_config_dir / "spirit_marks.json"
            inventory = load_inventory(
                config_path.with_name("items.json"),
                user_inventory_path,
                user_spirit_mark_path,
            )
            spirit_marks = load_spirit_mark_inventory(user_spirit_mark_path)

            def save_updated_spirit_marks(updated: SpiritMarkInventory) -> None:
                nonlocal spirit_marks
                spirit_marks = updated
                save_spirit_mark_inventory(user_spirit_mark_path, updated)

            def request_debug_spirit_mark() -> str:
                nonlocal inventory, spirit_marks
                request = SpiritMarkGrantRequest(
                    source_type="debug",
                    source_id="management-debug",
                    source_description="这道灵痕来自管理界面的一次调试请求，用于验证真实生成、入包和装备流程。",
                    quality_hint="completed",
                    record_tags=("debug", "management"),
                )
                result = grant_spirit_mark(
                    request,
                    items_path=config_path.with_name("items.json"),
                    inventory_path=user_inventory_path,
                    spirit_mark_path=user_spirit_mark_path,
                )
                inventory = result.inventory_snapshot
                spirit_marks = result.spirit_mark_inventory
                if main_window is not None:
                    main_window.update_inventory_and_spirit_marks(inventory, spirit_marks)
                return f"已生成灵痕：{result.mark.name}（{result.mark.entry_id}）"

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
                spirit_mark_inventory=spirit_marks,
                pet_attribute_sheet=PetAttributeSheet.from_config(config),
                on_spirit_marks_changed=save_updated_spirit_marks,
                on_debug_request_spirit_mark=request_debug_spirit_mark,
            )
        main_window.open_home()

    tray = TrayController(
        window,
        on_set_target=lambda: target_selector.start(),
        on_show=start_show,
        on_open_window=open_main_window,
    )
    tray.show()
    window.show()

    try:
        return app.exec()
    except KeyboardInterrupt:
        app.quit()
        return 130
