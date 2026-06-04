# `desktop_sprite.utils` — 工具与配置

4 个文件，约 280 行。本包只做"配置 + 平台探测 + 日志入口"三件基础设施性质的活，**不**持有任何运行时状态；所有函数/类都是**纯函数或可重入**的。

> 与本 README 互补：
> - 完整数据模型（`AppConfig` 字段消费方）见 [../models/README.md](../models/README.md)
> - 配置驱动的桌宠行为（`config` 段如何被 `physics / pathfinder / effective_stats` 消费）见 [../core/README.md](../core/README.md)

---

## 目录

- [文件清单](#文件清单)
- [`config.py` — 配置中枢](#config_py--配置中枢)
- [`dpi.py` — DPI 探测入口](#dpi_py--dpi-探测入口)
- [`logger.py` — 日志入口](#logger_py--日志入口)
- [`win_api.py` — Win32 探测点](#win_api_py--win32-探测点)
- [端到端加载流程示例](#端到端加载流程示例)

---

## 文件清单

| 路径 | 角色 | 行数级 |
| --- | --- | --- |
| `__init__.py` | re-export `AppConfig` / `load_config` | 极小 |
| [`config.py`](config.py) | `AppConfig` 树 + `load_config` + 跨段 key 归位 | 206 |
| [`dpi.py`](dpi.py) | Qt 屏幕矩形 + Win32 物理像素折算 | 65 |
| [`logger.py`](logger.py) | `configure_logging` 入口 | 10 |
| [`win_api.py`](win_api.py) | `is_windows()` 探测 | 7 |

---

## `config.py` — 配置中枢

### 公开 dataclass（全部 `@dataclass(frozen=True, slots=True)`）

| 名称 | 字段 |
| --- | --- |
| `RuntimeConfig` | `fps: int`, `always_on_top: bool`, `debug_draw: bool`, `log_level: str` |
| `PetConfig` | `width: int`, `height: int`, `default_spawn_x: int`, `default_spawn_y: int`, `flight: PetFlightConfig`, `wings: PetWingConfig`, `hover: PetHoverConfig` |
| `PetFlightConfig` | `speed: float = 520.0`, `landing_speed: float = 360.0` |
| `PetWingConfig` | `open_seconds: float = 0.7`, `close_seconds: float = 0.7` |
| `PetHoverConfig` | `amplitude: float = 8.0`, `frequency: float = 2.2` |
| `PhysicsConfig` | `gravity`, `walk_speed`, `climb_speed`, `jump_speed_x`, `jump_speed_y`, `max_fall_speed`, `drag_throw_factor`, `edge_snap_distance` |
| `BehaviorConfig` | `idle_min_seconds`, `idle_max_seconds`, `prefer_foreground_window`, `target_repick_seconds` |
| `AttributesConfig` | `wander`, `vigor`, `recovery`, `awareness`, `focus`, `satiety`, `spark`, `radiance`, `trail`, `resonance`, `aura`, `arcana`, `attunement`（13 项数值） |
| `InteractionConfig` | `draggable`, `throw_enabled`, `click_reaction`, `mouse_hover_reaction`, `target_search_down_distance = 220.0`, `target_search_up_distance = 80.0` |
| `CharacterConfig` | `default_type: str`, `profile_files: dict[str, str]` |
| `AppConfig` | 聚合以上 7 个子配置：`app`, `pet`, `physics`, `behavior`, `interaction`, `character`, `attributes` |

### 公开函数

```python
def load_config(
    path: str | Path | None = None,
    user_path: str | Path | None = None,
) -> AppConfig
```

- 默认 `path = <repo>/config/default.json`（`Path(__file__).resolve().parents[2] / "config" / "default.json"`）。
- 加载流程：**先读 default.json → 若有 user_path，先把 user 的 `character` 子段 merge 进 default → 调用 `_load_character_profiles` 把 `character.profile_files` 指向的角色档全部 merge 进顶层数据 → 最后再把整个 user_path 顶层 merge 一次**。
- 内部对 `interaction` 注入两个 `setdefault`（`target_search_*` 距离默认值）。
- 解析时把 `pet.flight / wings / hover` 三个嵌套段从 `pet` 中分离，留下 `pet` 的 `width / height / spawn` 等顶层字段；再调用 `_migrate_pet_motion_keys`（见下）后构造 `AppConfig`。

### 内部辅助（不导出）

| 名字 | 角色 |
| --- | --- |
| `_load_character_profiles(config_root, data)` | 遍历 `character.profile_files`，按相对路径打开并 merge |
| `_PET_MOTION_KEYS: tuple[str, ...] = ("walk_speed", "climb_speed", "jump_speed_x", "jump_speed_y")` | 跨段归位的 4 个 motion key（规范上属于 `physics` 段） |
| `_migrate_pet_motion_keys(pet_data, physics_data)` | 把上述 4 个 key 从 `pet_data` 中移除并写入 `physics_data`。**配置应直接写在 `physics` 段** |
| `_merge_dict(target, source)` | 递归浅 merge，值不是 dict 时覆盖 |

### 加载流程图

```
default.json ──► 读入 data
                  │
   (可选) user.json
        │         │
        ▼         │
  user.character ─┘  先 merge 到 data.character（profile_files 保持可解析）
                  │
 character.profile_files
        │         │
        ▼         │
  各角色档 JSON  ─┘  依次 merge 到 data
                  │
  user.json 顶层 ─┘  最后再 merge 到 data
                  │
  _migrate_pet_motion_keys
        │         │
        ▼         ▼
  从 pet 段分离 flight / wings / hover，构造 AppConfig
```

---

## `dpi.py` — DPI 探测入口

### 公开函数

```python
def qt_primary_screen_rects() -> tuple[Rect, Rect] | None
def qt_primary_screen_scale(physical_screen_width: float | None = None) -> float
def normalize_win32_rect_to_qt(rect: Rect, physical_screen_width: float) -> Rect
```

- `qt_primary_screen_rects`：通过 `QGuiApplication.primaryScreen()` 取得 `geometry` 与 `availableGeometry`，返回 `(screen_rect, available_rect)`（`Rect` 来自 `desktop_sprite.models.geometry`）。PySide6 不可用 / `primaryScreen()` 为空时返回 `None`。
- `qt_primary_screen_scale`：默认返回 `screen.devicePixelRatio()`。若提供了比 Qt 报告的 `qt_screen.width` 更大的 `physical_screen_width`，则改用 `physical / qt` 作为缩放比（用于 Win32 GDI 物理像素 → Qt 逻辑像素折算）。
- `normalize_win32_rect_to_qt`：仅在 `scale > 1.01` 时按 `1/scale` 缩放四个边；否则原样返回。

### 调用点

- `ui/sprite_window.py:DebugOverlayWindow._debug_lines` 通过 `qt_primary_screen_scale()` 显示当前 `scale=`。
- `environment/{taskbar,window}_sensor.py` 走 `normalize_win32_rect_to_qt` 把 Win32 矩形转为 Qt 坐标（Y 轴向下、多屏缩放修正）。
- `environment/screen_sensor.py` 走 `qt_primary_screen_rects()`。

---

## `logger.py` — 日志入口

```python
def configure_logging(level: str = "INFO") -> None
```

- 调 `logging.basicConfig`。
- `level` 取 `level.upper()` 对应的常量（未知回退 `INFO`）。
- 格式：`%(asctime)s %(levelname)s %(name)s: %(message)s`。

项目内绝大多数 `logger = logging.getLogger(__name__)` 都依赖此入口在启动时被调一次。**调用时机**：`AppRuntime.from_default_args` 构造期（`configure_logging(config.app.log_level)`），之后任何 import 时机使用 `getLogger(__name__)` 都会拿到这个 handler。

---

## `win_api.py` — Win32 探测点

```python
def is_windows() -> bool
```

- 用 `hasattr(ctypes, "windll")` 判定。
- 可作为后续 Win32 调用的前置 gate；当前实现只有一个该判定函数，未在 `ui` 包内被直接调用。

---

## 端到端加载流程示例

调用方在 [`../app/runtime.py`](../app/runtime.py) 的 `from_default_args` 内：

```python
paths = RuntimePaths.resolve_default()
config = load_config(paths.config_path, paths.user_config_path)
configure_logging(config.app.log_level)
app = QApplication([sys.argv[0], *qt_args])
```

典型路径：

- `paths.config_path` = `<repo>/config/default.json`
- `paths.user_config_path` = `<repo>/config/user/user.json`（不存在时 `load_config` 仍可用，仅跳过 user 合并）
- `paths.user_inventory_path` = `<repo>/config/user/inventory.json`
- `paths.user_spirit_mark_path` = `<repo>/config/user/spirit_marks.json`

返回的 `AppConfig` 可直接喂给 `create_character(config, character_type="pet")` 与 `SpriteWindow(character, config)`。
