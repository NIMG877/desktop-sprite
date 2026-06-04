# `desktop_sprite.environment` — 桌面环境感知层

每帧把 Windows 桌面的"屏幕 + 工作区 + 任务栏 + 可见窗口"实时采集成一个不可变快照 `EnvironmentSnapshot`，并派生桌宠可踩踏/可攀爬的 `Platform` 列表。**不**消费/写入桌宠状态；`PetController._refresh_environment_if_needed` 拉取本层。

> 与本 README 互补：
> - `Platform` / `WindowInfo` / `Rect` 等数据模型见 [../models/README.md](../models/README.md)
> - 寻路层（消费 `EnvironmentSnapshot.platforms`）见 [../core/README.md](../core/README.md)

---

## 目录

- [文件清单](#文件清单)
- [公开 API](#公开-api)
- [平台 ID 规则](#平台-id-规则)
- [业务流程](#业务流程)
- [跨平台降级](#跨平台降级)
- [文件间依赖图](#文件间依赖图)

---

## 文件清单

| 路径 | 角色 | 行数级 |
| --- | --- | --- |
| `__init__.py` | re-export `EnvironmentSnapshot` / `PlatformMapper` / `WindowSensor` | 极小 |
| [`desktop_environment.py`](desktop_environment.py) | 聚合 Facade，统一 `snapshot()` 入口 | 41 |
| [`environment_snapshot.py`](environment_snapshot.py) | frozen 数据类 + 查询方法 | 27 |
| [`platform_mapper.py`](platform_mapper.py) | 屏幕 → 平台列表 | 94 |
| [`screen_sensor.py`](screen_sensor.py) | Qt 主屏 full rect + work area rect | 28 |
| [`taskbar_sensor.py`](taskbar_sensor.py) | Win32 `Shell_TrayWnd` 矩形 | 36 |
| [`window_sensor.py`](window_sensor.py) | Win32 `EnumWindows` 矩形 + 过滤 | 109 |

---

## 公开 API

### `DesktopEnvironment`（[`desktop_environment.py`](desktop_environment.py)）

```python
class DesktopEnvironment:
    def __init__(self, pet_width: int, pet_height: int) -> None
    def set_own_window_handle(self, hwnd: int | None) -> None
    def snapshot(self) -> EnvironmentSnapshot
```

- 公开字段：`screen_sensor` / `taskbar_sensor` / `window_sensor` / `platform_mapper`。
- `snapshot()` 时间戳使用 `time.monotonic()`（单调时钟，用于帧间差值）。
- `set_own_window_handle` 把桌宠自身 HWND 透传到 `WindowSensor`，枚举时剔除自己。

### `EnvironmentSnapshot`（[`environment_snapshot.py`](environment_snapshot.py)）

`@dataclass(frozen=True, slots=True)`：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `screen_rect` | `Rect` | 主屏全屏矩形 |
| `work_area_rect` | `Rect` | 主屏工作区（去掉任务栏） |
| `taskbar_rect` | `Rect \| None` | 任务栏矩形；不可用则为 None |
| `windows` | `list[WindowInfo]` | 可见窗口列表，前台窗排首位 |
| `platforms` | `list[Platform]` | 当帧派生的可交互平台 |
| `timestamp` | `float` | `time.monotonic()` |

方法 / 属性：

- `platform_by_id(platform_id: str | None) -> Platform | None`：线性查找，传 `None` 直接返回 `None`。
- `foreground_window`（property）→ `WindowInfo | None`：返回 `windows` 中首个 `is_foreground=True`。

### `PlatformMapper`（[`platform_mapper.py`](platform_mapper.py)）

```python
class PlatformMapper:
    def __init__(self, pet_width: int, pet_height: int) -> None
    def map_platforms(
        self,
        screen_rect: Rect,
        work_area_rect: Rect,
        taskbar_rect: Rect | None,
        windows: list[WindowInfo],
    ) -> list[Platform]
```

内部方法（私有）：`_window_platforms`、`_clip_horizontal`、`_duplicates_ground`。

### `ScreenSensor`（[`screen_sensor.py`](screen_sensor.py)）

```python
class ScreenSensor:
    def get_screen_rect(self) -> Rect        # 主屏 full rect
    def get_work_area_rect(self) -> Rect     # 主屏 work area；无 Qt 时回退到 screen
```

### `TaskbarSensor`（[`taskbar_sensor.py`](taskbar_sensor.py)）

```python
class TaskbarSensor:
    def __init__(self) -> None
    def get_taskbar_rect(self) -> Rect | None
```

内部 ctypes 结构：`_WinRect(LONG, LONG, LONG, LONG)`。

### `WindowSensor`（[`window_sensor.py`](window_sensor.py)）

```python
class WindowSensor:
    def __init__(self) -> None
    def set_own_window_handle(self, hwnd: int | None) -> None
    def get_windows(self) -> list[WindowInfo]
```

模块级常量：

```python
IGNORED_CLASSES = {
    "Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
    "Button", "Windows.UI.Core.CoreWindow",
}
EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
```

私有方法：`_window_info` / `_is_usable_window` / `_window_text` / `_class_name`。

---

## 平台 ID 规则

`PlatformMapper.map_platforms` 输出 5 类 `Platform`：

| 类型 | ID 格式 | walkable | climbable | dynamic | source_id |
| --- | --- | --- | --- | --- | --- |
| 地面 | `"ground:work_area"` | ✓ | ✗ | ✗ | — |
| 任务栏 | `"taskbar:main"` | ✓ | ✗ | ✓ | — |
| 窗口顶 | `"window:{hwnd}:top"` | 受 pet_height 限制 | ✗ | ✓ | `hwnd` |
| 窗口左 | `"window:{hwnd}:left"` | ✗ | ✓ | ✓ | `hwnd` |
| 窗口右 | `"window:{hwnd}:right"` | ✗ | ✓ | ✓ | `hwnd` |

**派生细节**：

- 地面 rect：宽度 `work_area_rect.left → work_area_rect.right`，高度 `work_area_rect.bottom → bottom + 4`（4 像素厚"踏板"）。
- 任务栏 rect：高度 4 像素、贴在 `taskbar_rect.top`；当 `taskbar_rect` 与 `work_area_rect` 顶边一致且横向重叠时（即任务栏与地面重合）跳过，避免重复平台。
- 窗口顶 walkable 条件：`rect.top - screen_rect.top >= pet_height`（桌宠能完整站到顶面）。
- 窗口顶水平裁剪到 `screen_rect.left/right`（`_clip_horizontal`）；左右两柱不裁剪。
- 任何最小化窗口（`window.minimized=True`）不会派生平台。

> `PlatformType` 枚举与 `Platform` 字段定义在 [`../models/platform.py`](../models/platform.py)；`PlatformTopology` 提供窗口三边 ID 工厂（`window_top_id / window_left_id / window_right_id` / `top_id_for_side_id`），见 [`../models/platform_topology.py`](../models/platform_topology.py)。

---

## 业务流程

```
ScreenSensor ─┐
TaskbarSensor ├─► DesktopEnvironment.snapshot()
WindowSensor ─┘                       │
                                     ▼
                       PlatformMapper.map_platforms()
                                     │
                                     ▼
                          EnvironmentSnapshot(timestamp)
                                     │
              ┌──────────────────────┼──────────────────────┐
              ▼                      ▼                      ▼
     PetController (per-frame)   TargetSelectorOverlay   DebugOverlay
```

调用方：

- `PetController._refresh_environment_if_needed`（每帧或按节流）调 `desktop_environment.snapshot()` 并把快照作为参数传给 `pathfinder.find_path_to_surface_point` 与 `physics.update`。
- `ui.target_selector.select_target_candidate` 遍历 `snapshot.platforms` 找最近的 walkable 平台。
- `ui.sprite_window.DebugOverlayWindow.paintEvent` 用 `debug_state.snapshot` 画导航地图。

---

## 跨平台降级

所有 Win32 传感器在 `ctypes.windll` 不可用（非 Windows）时安全返回 `None` / `[]`；`ScreenSensor` 在 Qt 不可用时回退到 `Rect(0,0,1280,720)`。坐标系通过 `utils.dpi.normalize_win32_rect_to_qt` 转为 Qt 坐标（Y 轴向下、多屏缩放修正）。

| 不可用条件 | 行为 |
| --- | --- |
| 非 Windows（`ctypes.windll` 不存在） | `WindowSensor.get_windows` → `[]`；`TaskbarSensor.get_taskbar_rect` → `None` |
| Qt 不可用 | `ScreenSensor` 兜底 `Rect(0,0,1280,720)`；`work_area_rect` 与 `screen_rect` 同值 |
| `physical_screen_width > qt_screen.width × 1.01` | 缩放比 `= physical / qt`，通过 `utils.dpi.normalize_win32_rect_to_qt` 把 Win32 物理像素折算回 Qt 逻辑像素 |

---

## 文件间依赖图

```
desktop_environment.py
  ├── environment_snapshot.py
  ├── platform_mapper.py
  │     ├── models.geometry.Rect
  │     ├── models.platform.{Platform, PlatformType}
  │     ├── models.platform_topology.PlatformTopology
  │     └── models.window_info.WindowInfo
  ├── screen_sensor.py
  │     ├── models.geometry.Rect
  │     └── utils.dpi.qt_primary_screen_rects
  ├── taskbar_sensor.py
  │     ├── models.geometry.Rect
  │     └── utils.dpi.normalize_win32_rect_to_qt
  └── window_sensor.py
        ├── models.geometry.Rect
        ├── models.window_info.WindowInfo
        └── utils.dpi.normalize_win32_rect_to_qt
```

外部依赖（`utils/`）：`utils.dpi.qt_primary_screen_rects`、`utils.dpi.normalize_win32_rect_to_qt`。

---

## 可见性窗口过滤规则

`WindowSensor._is_usable_window` 拒绝以下窗口：

1. 最小化（`minimized=True`）
2. 类名命中 `IGNORED_CLASSES`（托盘、桌面管理器、UI 内部窗口）
3. 宽 < 120 或高 < 80
4. 无标题 **且** 非前台

`WindowSensor._own_hwnd`（由 `set_own_window_handle` 注入）会跳过枚举到的自身窗口。`get_windows()` 返回的 `windows` 已按 `is_foreground` 排序，前台在前。
