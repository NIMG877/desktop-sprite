# `desktop_sprite.app` — 应用运行时门面

`python -m app` 启动后真正进入的代码位于本包。它把 CLI 入口、Qt 事件循环、桌宠子系统（character + 三个窗口 + 托盘 + 管理窗口）、配置热加载、灵痕调试流整合为单一 `AppRuntime` 实例，并对外提供 `main()` 作为唯一脚本入口。

本包只有 3 个源文件，合计约 460 行；承担"进程级生命周期 + 测试桩可注入"两项关键职责。

---

## 目录

- [文件清单](#文件清单)
- [`AppRuntime` 字段与职责](#appruntime-字段与职责)
- [`__init__.py` — 入口与模块级符号](#init_py--入口与模块级符号)
- [`config_paths.py` — 不可变路径容器](#config_paths_py--不可变路径容器)
- [`runtime.py` — `AppRuntime` 完整 API](#runtime_py--appruntime-完整-api)
- [启动流程端到端](#启动流程端到端)
- [可测试性设计](#可测试性设计)
- [公开 API vs 内部 API](#公开-api-vs-内部-api)

---

## 文件清单

| 路径 | 角色 |
| --- | --- |
| [`__init__.py`](__init__.py) | `main()` + 17 个模块级 re-export 符号（QApplication / signal / load_config / create_character / SpriteWindow / TargetSelectorOverlay / ShowOverlayWindow / TrayController / MainWindow / load_inventory / load_spirit_mark_inventory / save_spirit_mark_inventory / grant_spirit_mark / SpiritMarkInventory / SpiritMarkGrantRequest / configure_logging / sys） |
| [`runtime.py`](runtime.py) | `AppRuntime` 完整实现 |
| [`config_paths.py`](config_paths.py) | 不可变 `RuntimePaths` dataclass |

---

## `AppRuntime` 字段与职责

`AppRuntime` 是运行时门面：所有长生命周期对象（`QApplication` / 桌宠 / 三个窗口 / 托盘 / 管理窗口 / 灵痕档案）都聚合为它的字段；所有动作（重启宠物 / 切换配置 / 打开主窗 / 请求调试灵痕）都是它的显式方法，可直接 `monkeypatch` 注入替身做单测。

| 字段 | 类型 | 用途 |
| --- | --- | --- |
| `paths` | `RuntimePaths` | 已解析的配置文件 / 用户数据路径 |
| `qt_args` | `list[str]` | 透传给 `QApplication` 的 Qt 启动参数 |
| `args` | `argparse.Namespace` | CLI 参数（`args.character` 等） |
| `config` | `AppConfig` | 当前生效的应用配置（可被 `restart_pet` / `apply_runtime_config` 替换） |
| `app` | `QApplication` | 全局 Qt 应用对象 |
| `character` | `DesktopCharacter` | 桌宠主体；`restart_pet` 时重建 |
| `window` | `SpriteWindow` | 无边框置顶桌宠窗体 |
| `target_selector` | `TargetSelectorOverlay` | 选目标浮层 |
| `show_overlay` | `ShowOverlayWindow` | Show 表演浮层 |
| `spirit_marks` | `SpiritMarkInventory` | 持久化的灵痕档案 |
| `inventory` | `InventorySnapshot \| None` | 背包快照；首次打开管理窗口时加载 |
| `main_window` | `MainWindow \| None` | FluentWindow 管理界面，懒构造 |
| `tray` | `TrayController` | 托盘菜单/图标 |

---

## `__init__.py` — 入口与模块级符号

[`__init__.py`](__init__.py) 模块顶部显式 import 17 个符号到包对象上，确保：

- `from desktop_sprite.app import MainWindow` 之类语法直生效。
- `monkeypatch.setattr(desktop_sprite.app, "MainWindow", fake)` 在测试 setup 阶段可以把整组 Qt 控件替身。

```python
def main() -> int:
    """Build a default-config runtime and enter the event loop."""
    return AppRuntime.from_default_args().run()
```

`__all__` 列出全部 17 个 re-export 符号（见文件清单）。

---

## `config_paths.py` — 不可变路径容器

[`config_paths.py`](config_paths.py) 把 4 个运行时文件路径封装进单个 `frozen=True, slots=True` 的 dataclass：

```python
@dataclass(frozen=True, slots=True)
class RuntimePaths:
    config_path: Path
    user_config_path: Path
    user_inventory_path: Path
    user_spirit_mark_path: Path

    @classmethod
    def from_config_path(cls, config_path: Path) -> "RuntimePaths"
    @classmethod
    def resolve_default(cls) -> "RuntimePaths"
```

默认布局：`<repo>/config/default.json` + `<repo>/config/user/{user,inventory,spirit_marks}.json`。`from_config_path` 在用户提供的 `config_path` 同级派生 `user/` 目录。

---

## `runtime.py` — `AppRuntime` 完整 API

### 构造与工厂

```python
def __init__(
    self,
    paths: RuntimePaths,
    qt_args: list[str],
    args: argparse.Namespace,
    config: AppConfig,
    app: "QApplication",
) -> None

@classmethod
def from_default_args(cls) -> "AppRuntime"  # 内部调 _app_symbols + RuntimePaths + load_config
```

`_parse_args(argv, config)` 仅接受 `--character {pet}`，回退到 `config.character.default_type`。

### 桌宠窗口生命周期

| 方法 | 说明 |
| --- | --- |
| `create_pet_window(runtime_config: AppConfig) -> tuple[DesktopCharacter, SpriteWindow, TargetSelectorOverlay, ShowOverlayWindow]` | 1) `create_character(config, character_type=args.character)` → 2) 若 character 提供 `set_attribute_sheet` 则注入 `PetAttributeSheet.from_config(...).with_modifiers(self.spirit_marks.attribute_modifiers())` → 3) `SpriteWindow(character, config)` → 4) `character.set_own_window_handle(int(window.winId()))` → 5) `ShowOverlayWindow(character)` 并回写到 `window.show_overlay` 共享 tick |
| `start_show()` | 调 `character.start_show()`，成功则 `target_selector.stop()` + `show_overlay.start()` |
| `close_pet_runtime()` | 依次 stop 三个窗口并 `window.close()` |

### 配置热路径

| 方法 | 说明 |
| --- | --- |
| `restart_pet()` | `load_config` → 失败弹 `QMessageBox.critical` 返回 → 成功则 `close_pet_runtime`、`configure_logging`、`create_pet_window`、`TrayController(window, …)`（重建以保留 `on_open_window` 回调）、`tray.set_window(window)`、`window.show()` |
| `apply_runtime_config()` | 不重建：仅 `load_config` → 失败弹错 → 成功则 `configure_logging` + `character.apply_config` + `window.apply_config` + `target_selector.apply_config` |

### 管理窗口

| 方法 | 说明 |
| --- | --- |
| `open_main_window()` | 懒构造 `MainWindow`，首次调用时 `load_inventory(items_path, user_inventory_path, user_spirit_mark_path)` → 注入全部回调（`on_set_target / on_show / on_sleep / on_restart / on_apply_config / on_quit / inventory_snapshot / spirit_mark_inventory / pet_attribute_sheet / on_spirit_marks_changed / on_debug_request_spirit_mark`）→ `main_window.open_home()` |
| `save_updated_spirit_marks(updated)` | `save_spirit_mark_inventory` → 写回 `self.spirit_marks` → 若 character 提供 `set_attribute_sheet` 则用 `updated.attribute_modifiers()` 重算 |
| `request_debug_spirit_mark() -> str` | 构造 `SpiritMarkGrantRequest(source_type="debug", source_id="management-debug", quality_hint="completed", record_tags=("debug","management"))` → 调 `grant_spirit_mark(...)` → 同步 `inventory / spirit_marks` → 通知 `main_window.update_inventory_and_spirit_marks` → 返回中文成功文案 |

### 退出与事件循环

| 方法 | 说明 |
| --- | --- |
| `quit_app()` | `close_pet_runtime` → `main_window.close()`（若存在）→ `tray.tray.hide()` → `app.quit()` |
| `run() -> int` | `create_pet_window` → `TrayController(...).show()` → `window.show()` → `app.exec()`；捕获 `KeyboardInterrupt` 返回 `130` 并 `app.quit()` |

### 内部辅助

- `_app_symbols() -> dict[str, Any]`：每次访问时从 `desktop_sprite.app` 包对象重新读取符号（详见"可测试性设计"）。

---

## 启动流程端到端

```
python -m app
└─ app.py:main()
   └─ desktop_sprite.app.main()
      └─ AppRuntime.from_default_args().run()

AppRuntime.from_default_args()
├─ syms    = _app_symbols()                          # 延迟查表 → 读 desktop_sprite.app 包对象
├─ paths   = RuntimePaths.resolve_default()
├─ config  = load_config(paths.config_path, paths.user_config_path)
├─ args, qt_args = _parse_args(sys.argv[1:], config) # 仅 --character
├─ configure_logging(config.app.log_level)
├─ QApplication.setHighDpiScaleFactorRoundingPolicy(PassThrough)
├─ app = QApplication([sys.argv[0], *qt_args])
├─ app.setApplicationName("Desktop Sprite")
├─ app.setQuitOnLastWindowClosed(False)
├─ signal.signal(SIGINT, lambda *_a: app.quit())     # Ctrl+C 优雅退出
└─ return AppRuntime(paths, qt_args, args, config, app)

AppRuntime.run()
├─ character, window, target_selector, show_overlay = create_pet_window(self.config)
├─ tray = TrayController(window, on_set_target, on_show, on_open_window)
├─ tray.show(); window.show()
└─ return app.exec()                                 # 进入 Qt 事件循环
```

---

## 可测试性设计

### 符号延迟查表

`_app_symbols()` 每次访问时从 `desktop_sprite.app` 包对象重新读取符号：

```python
def _app_symbols() -> dict[str, Any]:
    pkg = sys.modules[__package__]  # desktop_sprite.app
    return {name: getattr(pkg, name) for name in _APP_PATCH_TARGETS}
```

`tests/test_app.py` 的 `monkeypatch.setattr(desktop_sprite.app, "X", fake)` 在 `from_default_args` 内部实际触发 `getattr(pkg, "X")` 时拿到 fake，无需修改 `__init__.py` 的 import 语句。

### `monkeypatch` 目标清单

`__init__.py` 显式 import 到包对象上的 17 个符号（见 `__all__`）都是合法 patch 目标；最常用的几个：

- `QApplication / Qt / QTimer`（GUI 启动门控）
- `signal / sys`（环境变量与 Ctrl+C 处理）
- `load_config / configure_logging`（配置/日志注入）
- `create_character`（桌宠替身）
- `SpriteWindow / TargetSelectorOverlay / ShowOverlayWindow / TrayController / MainWindow`（窗口替身）
- `load_inventory / load_spirit_mark_inventory / save_spirit_mark_inventory / grant_spirit_mark`（数据持久化替身）

### 对反射式测试的支持

`tests/test_pet_controller_climb_reach.py`（730 行）通过 `PetController.__new__` 跳过 `__init__`、直接读写 15+ 私有成员。`runtime.py` 在初始化阶段不校验"未来得及注入就会被访问"的字段；`AppRuntime` 字段全部是 `Optional` 或延迟构造，保证这类反射式访问安全。

---

## 公开 API vs 内部 API

### 外部应该 import

- 脚本入口：`desktop_sprite.app.main`
- 运行时类：`AppRuntime.from_default_args()` / `AppRuntime(…)`
- 路径解析：`RuntimePaths.resolve_default()` / `RuntimePaths.from_config_path(path)`

### 外部不应该用

- `AppRuntime._app_symbols()` / `AppRuntime._parse_args()` — 测试基础设施，生产代码不要调用。
- `desktop_sprite.app` 包对象上挂的 `signal / sys`（非真实 Qt 符号）— 仅为测试 patch 目标存在，**生产代码永远不要 `from desktop_sprite.app import signal`**（应该 `import signal`）。
- 任意 `AppRuntime` 字段如果在构造后未经过 `create_pet_window` / `open_main_window` 等懒方法就被访问，**可能为 None**（例如 `main_window` / `inventory` / `tray`）；调用方必须做 None 检查或保证触发过懒构造。

### 异常路径

- `restart_pet` / `apply_runtime_config` 内部用 `QMessageBox.critical` 弹错（**不**抛异常），用户取消则保留旧运行时。
- `quit_app` 不会触发 `closeEvent` 链路上的 `_save_window_geometry`（那是 `MainWindow.closeEvent` 的事，**与 `AppRuntime` 无关**）。
- 托盘 `TrayController.show()` 在 `QSystemTrayIcon.isSystemTrayAvailable()` 为假时 `logger.warning` 后直接 return — `AppRuntime.run` 不因此失败。
