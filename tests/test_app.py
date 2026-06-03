from types import SimpleNamespace

import desktop_sprite.app as app_module


class _FakeApplication:
    @staticmethod
    def setHighDpiScaleFactorRoundingPolicy(_policy) -> None:
        pass

    def __init__(self, _args) -> None:
        pass

    def setApplicationName(self, _name: str) -> None:
        pass

    def setQuitOnLastWindowClosed(self, _enabled: bool) -> None:
        pass

    def exec(self) -> int:
        return 0

    def quit(self) -> None:
        pass


class _FakeTimer:
    def __init__(self) -> None:
        self.timeout = SimpleNamespace(connect=lambda _callback: None)

    def start(self, _interval: int) -> None:
        pass


class _FakeCharacter:
    def set_own_window_handle(self, _handle: int) -> None:
        pass


class _FakeSpriteWindow:
    def __init__(self, _character, _config) -> None:
        pass

    def winId(self) -> int:
        return 1

    def show(self) -> None:
        pass


class _FakeOverlay:
    def __init__(self, *_args) -> None:
        pass


class _FakeTrayController:
    instance = None

    def __init__(self, _window, **kwargs) -> None:
        self.on_open_window = kwargs["on_open_window"]
        _FakeTrayController.instance = self

    def show(self) -> None:
        pass


class _FakeMainWindow:
    instances = []

    def __init__(self, *_args, **_kwargs) -> None:
        self.open_count = 0
        self.instances.append(self)

    def open_home(self) -> None:
        self.open_count += 1


def test_management_window_is_created_on_first_tray_open(monkeypatch):
    inventory_calls = []
    spirit_mark_calls = []
    config = SimpleNamespace(
        app=SimpleNamespace(log_level="INFO"),
        character=SimpleNamespace(default_type="pet"),
    )
    _FakeMainWindow.instances.clear()
    _FakeTrayController.instance = None

    monkeypatch.setattr(app_module, "QApplication", _FakeApplication)
    monkeypatch.setattr(app_module, "QTimer", _FakeTimer)
    monkeypatch.setattr(app_module.signal, "signal", lambda *_args: None)
    monkeypatch.setattr(app_module.sys, "argv", ["desktop-sprite"])
    monkeypatch.setattr(app_module, "load_config", lambda *_args: config)
    monkeypatch.setattr(app_module, "configure_logging", lambda *_args: None)
    monkeypatch.setattr(app_module, "create_character", lambda *_args, **_kwargs: _FakeCharacter())
    monkeypatch.setattr(app_module, "SpriteWindow", _FakeSpriteWindow)
    monkeypatch.setattr(app_module, "TargetSelectorOverlay", _FakeOverlay)
    monkeypatch.setattr(app_module, "ShowOverlayWindow", _FakeOverlay)
    monkeypatch.setattr(app_module, "TrayController", _FakeTrayController)
    monkeypatch.setattr(app_module, "MainWindow", _FakeMainWindow)
    monkeypatch.setattr(app_module, "load_inventory", lambda *_args: inventory_calls.append(1))
    monkeypatch.setattr(app_module, "load_spirit_mark_inventory", lambda *_args: spirit_mark_calls.append(1))
    monkeypatch.setattr(app_module, "save_spirit_mark_inventory", lambda *_args: None)

    assert app_module.main() == 0
    assert _FakeMainWindow.instances == []
    assert inventory_calls == []

    tray = _FakeTrayController.instance
    tray.on_open_window()
    tray.on_open_window()

    assert len(_FakeMainWindow.instances) == 1
    assert _FakeMainWindow.instances[0].open_count == 2
    assert inventory_calls == [1]
    assert spirit_mark_calls == [1]
