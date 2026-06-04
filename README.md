# Desktop Sprite · 桌宠

> 一个使用 `PySide6` + `PySide6-Fluent-Widgets` 实现的 Windows 桌面小精灵，融合了 **桌面环境感知**、**寻路与动作规划**、**属性/资源系统**、**灵痕装备系统** 与 **养成/背包/调试管理界面** 的完整闭环。

---

## 目录

- [特性总览](#特性总览)
- [项目结构](#项目结构)
- [运行与安装](#运行与安装)
- [配置说明](#配置说明)
- [架构总览](#架构总览)
- [模块详解](#模块详解)
  - [app.py 入口](#apppy-入口)
  - [core · 行为/物理/寻路核心](#core--行为物理寻路核心)
  - [environment · 桌面环境感知](#environment--桌面环境感知)
  - [models · 领域模型](#models--领域模型)
  - [ui · 视图层与渲染](#ui--视图层与渲染)
  - [utils · 配置/DPI/日志/平台工具](#utils--配置dpi日志平台工具)
- [数据文件与存档](#数据文件与存档)
- [测试](#测试)
- [扩展指引](#扩展指引)
- [路线与 TODO](#路线与-todo)

---

## 特性总览

- **透明、置顶、无边框桌宠窗口** —— 基于 `QWidget` + `WA_TranslucentBackground`，可在桌面上自由拖拽。
- **多状态动画系统** —— `IDLE / WALK / JUMP / CLIMB / FALL / DRAGGED / SLEEP / OPEN_WINGS / FLY / HOVER / WING_LAND / CLOSE_WINGS`，状态机限制合法切换并使用前态-当前态的插值过渡。
- **桌面环境感知** —— 通过 Win32 API 枚举窗口、读取屏幕/工作区/任务栏矩形，实时构建 **平台/墙** 拓扑（窗口顶部=平台，左右边=可攀爬墙），窗口移动/最小化时自动跟随或掉落。
- **统一表面图寻路** —— `PathFinder` 用 `Surface`（水平/竖直同构）+ `TraversalAction`（`MOVE/JUMP/TRANSFORM/FALL`）构建事件点图，`GraphPlanner` 做 Dijkstra 最短路，输出 `PathPlan`，`PathExecutor` 分发执行。
- **物理引擎** —— 重力、抛投、平台落地、动态平台跟随、屏幕夹紧、撞墙处理、攀爬沿轴运动均封装在 `PhysicsEngine`。
- **属性/资源系统** —— 15 种属性（机动/攀附/腾跃/巡游/元气/生息/灵识/凝神/饱腹/迸发/辉映/留痕/共鸣/灵韵/异能/调律）分为基础/视觉/特殊三类，影响移动/攀爬/跳跃/体力/精力/饥饿/展示动作的多个因子。
- **灵痕系统** —— 5 个部位（灵核/形骸/脉络/锋质/余响）× 5 个套装（静默守护/星尘余响/破风远行/坠落回响/幻形流转），有主副词条、强化、装备、分解、收藏、属性 modifier 自动注入到桌宠。
- **展示动作（Show）** —— 一段按 `OPEN_WINGS → FLY → HOVER → TITLE → LAND → CLOSE_WINGS` 顺序播放的展示动画序列，渲染体积放大到 `4.6×3.8`，并叠加独立的全屏标题与画布。
- **目标点选择** —— 在桌面上点选可见的窗口顶部作为目标，桌宠自动寻路过去；找不到候选时给出视觉提示。
- **养成/背包/调试界面** —— 基于 `qfluentwidgets` 的深色 Fluent 风格管理窗口，包含「启动、实时触发、养成、背包、全自动、辅助操控、调试、通知、设置」9 个子页面。
- **配置编辑** —— 内嵌的 `ConfigEditorWidget` 支持对 `config/default.json` 进行扁平化键路径编辑、保存到 `user/user.json`、运行时热应用/重启/撤销。
- **托盘控制** —— 通过 `QSystemTrayIcon` 提供「展示 / 设置目标点 / 退出」菜单项，支持单击或双击托盘图标打开主窗口。
- **可调试可视化** —— 开启 `app.debug_draw` 后，全屏覆盖层会绘制平台图、导航图、当前路径、碰撞框和实时状态/资源/路径文本。

---

## 项目结构

```
DesktopSprite/
├─ app.py                       # 极薄的入口，转调 desktop_sprite.app.main
├─ config/                      # 默认配置与角色档案
│  ├─ default.json              # 默认运行配置（FPS、物理、行为、属性、交互、角色）
│  ├─ items.json                # 道具目录（灵痕与测试分类）
│  ├─ characters/pet.json       # 桌宠角色档案（尺寸、生成点、行走/攀爬/跳跃/飞行/翅膀/悬停参数）
│  └─ user/                     # 运行时存档
│     ├─ user.json              # 用户配置覆盖（自动生成）
│     ├─ inventory.json         # 背包条目（自动生成）
│     ├─ spirit_marks.json      # 灵痕存档（自动生成）
│     └─ ui_state.json          # 管理界面状态（自动生成）
├─ assets/                      # 静态资源
│  └─ spirit_mark/              # 灵痕图标
│     └─ sanctum_radiance/      # 圣所辉光套装的灵核/形骸/脉络/锋质/余响 PNG
├─ desktop_sprite/              # 主包
│  ├─ app.py                    # 应用启动：装配 QApplication、托盘、桌宠、目标选择、Show、管理窗口
│  ├─ core/                     # 行为/物理/寻路/状态机核心
│  │  ├─ animation_player.py
│  │  ├─ behavior_orchestrator.py
│  │  ├─ behavior_state_machine.py
│  │  ├─ character.py           # DesktopCharacter 协议、CharacterRenderState/DebugState
│  │  ├─ character_factory.py   # 角色构造（目前固定 PetController）
│  │  ├─ path_executor.py
│  │  ├─ pathfinding.py
│  │  ├─ pet_controller.py
│  │  ├─ pet_mode.py
│  │  ├─ physics_engine.py
│  │  ├─ planner.py
│  │  └─ reachability_policy.py
│  ├─ environment/              # 桌面环境感知
│  │  ├─ desktop_environment.py
│  │  ├─ environment_snapshot.py
│  │  ├─ platform_mapper.py
│  │  ├─ screen_sensor.py
│  │  ├─ taskbar_sensor.py
│  │  └─ window_sensor.py
│  ├─ models/                   # 领域模型与持久化
│  │  ├─ geometry.py            # Vec2 / Rect
│  │  ├─ state.py               # Pet / PetState / Facing
│  │  ├─ platform.py            # Platform / PlatformType
│  │  ├─ platform_topology.py
│  │  ├─ window_info.py
│  │  ├─ pet_attribute.py       # 15 个属性定义、PetAttributeSheet、PetEffectiveStats、资源与影响
│  │  ├─ inventory.py           # InventorySnapshot / 加载与校验
│  │  ├─ spirit_mark.py         # 灵痕/套装/部位/材料/品质/强化/分解
│  │  └─ spirit_mark_service.py # 授予灵痕（同时写 inventory 与 spirit_marks）
│  ├─ ui/                       # 视图层
│  │  ├─ sprite_window.py       # 桌宠窗口 + 调试覆盖层
│  │  ├─ pet_renderer.py        # 由 Pose 绘制桌宠（影子/翅膀/四肢/身体/围巾/眼睛）
│  │  ├─ render_pose.py         # Pose 数据结构 + 状态驱动的 PoseBuilder
│  │  ├─ main_window.py         # Fluent 主窗口，9 个子页面
│  │  ├─ config_editor.py       # 配置编辑器
│  │  ├─ inventory_widget.py    # 背包（分类、卡片、滚动、详情）
│  │  ├─ growth_widget.py       # 养成（属性/灵痕/装备）
│  │  ├─ debug_widget.py        # 调试页：触发一次灵痕生成
│  │  ├─ show_overlay.py        # Show 模式全屏覆盖层（标题文字）
│  │  ├─ target_selector.py     # 目标点候选选择 + 全屏选择覆盖
│  │  └─ tray_controller.py     # 系统托盘
│  └─ utils/
│     ├─ config.py              # AppConfig dataclass + load_config（含 user.json 合并）
│     ├─ dpi.py                 # Qt 屏幕矩形归一化、DPR 缩放
│     ├─ logger.py              # 日志配置
│     └─ win_api.py             # 平台判断
├─ system_design/               # 设计文档（属性、灵痕、专注、PBD 软体等）
├─ PATHFINDING.md               # 寻路系统重构方案
├─ PLAN.md                      # 寻路系统重构方案（旧版）
├─ requirements.txt
└─ tests/                       # pytest 套件（21 个）
```

---

## 运行与安装

### 1. 准备环境

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

依赖：

- `PySide6>=6.7`
- `PySide6-Fluent-Widgets>=1.11.2`
- `pytest>=8.0`（仅测试需要）

### 2. 启动

```powershell
.\.venv\Scripts\python app.py
```

也可加参数指定角色（当前仅 `pet`）：

```powershell
.\.venv\Scripts\python app.py --character pet
```

程序入口在 [app.py:5](app.py) —— 实际是 `desktop_sprite.app.main()` 的薄包装。

### 3. 停止

- 在终端按 `Ctrl+C`（已注册 `SIGINT` 处理器调用 `QApplication.quit`）。
- 在 IDE 内运行则使用 IDE 的停止按钮。
- 托盘菜单 → 退出。
- 主窗口「启动」页 → 退出应用。

---

## 配置说明

主配置在 [config/default.json](config/default.json)；角色档案在 [config/characters/pet.json](config/characters/pet.json)。运行期在管理界面「设置」页修改后保存，会写入 [config/user/user.json](config/user/user.json)，下次启动时叠加在默认配置之上。

| 键 | 含义 |
| --- | --- |
| `app.fps` | 主循环、动画和环境感知刷新频率 |
| `app.always_on_top` | 桌宠窗口置顶 |
| `app.debug_draw` | 启用调试覆盖层（导航图/路径/碰撞框/调试文本） |
| `app.log_level` | 日志级别（`DEBUG/INFO/WARNING/ERROR`） |
| `physics.gravity` | 重力加速度（px/s²） |
| `physics.max_fall_speed` | 最大下落速度 |
| `physics.drag_throw_factor` | 拖拽松手后的投掷速度衰减 |
| `physics.edge_snap_distance` | 边缘吸附距离（攀爬抓边、平台跳判定） |
| `behavior.idle_min_seconds / idle_max_seconds` | 空闲目标停留时间区间 |
| `behavior.sleep_after_seconds` | 长时间空闲触发睡眠的阈值 |
| `behavior.prefer_foreground_window` | 是否倾向走向前景窗口 |
| `attributes.*` | 15 个属性初始值（详细定义见 [pet_attribute.py:323](desktop_sprite/models/pet_attribute.py#L323)） |
| `interaction.draggable / throw_enabled / click_reaction / mouse_hover_reaction` | 交互开关 |
| `interaction.target_search_down_distance / target_search_up_distance` | 目标点搜索的垂直范围（px） |
| `character.default_type / profile_files` | 角色选择与档案文件路径 |
| `pet.width / height / default_spawn_x / default_spawn_y` | 桌宠尺寸与初始生成点 |
| `pet.walk_speed / climb_speed / jump_speed_x / jump_speed_y` | 移动参数（在 `pet` 段中，会被 `physics` 段使用，见 [config.py:141](desktop_sprite/utils/config.py#L141)） |
| `pet.flight.speed / landing_speed` | Show 模式飞行与降落速度 |
| `pet.wings.open_seconds / close_seconds` | 翅膀展开/收起的基准时长 |
| `pet.hover.amplitude / frequency` | 悬停振幅与频率 |

### 运行时热重载

- **应用配置**：[MainWindow._save_and_apply_config](desktop_sprite/ui/main_window.py#L360) 会调用 `app.apply_runtime_config`，桌宠/窗口/目标选择器同步更新参数而无需重启。
- **重启桌宠**：[MainWindow](desktop_sprite/ui/main_window.py)「启动」页的「重启桌宠」会调用 `app.restart_pet`，重新加载配置并重建桌宠实例。
- **恢复默认**：[MainWindow._restore_default_config](desktop_sprite/ui/main_window.py#L370) 删除 `user.json` 后重新加载并应用。

---

## 架构总览

整体采用「**环境 → 寻路 → 物理 → 行为 → 渲染**」的分层循环，辅以「**配置 → 角色工厂 → 控制器（Protocol）**」的装配入口。

```
            ┌──────────────────────────────────────────────────────┐
            │                       app.py                         │
            │   QApplication 装配 + 托盘/管理窗口回调 + 重启/退出  │
            └────────────┬──────────────────────────┬──────────────┘
                         │                          │
            ┌────────────▼──────────┐   ┌───────────▼─────────────┐
            │  SpriteWindow + Show  │   │  MainWindow (Fluent)    │
            │  TargetSelector       │   │  ConfigEditor / Growth  │
            │  ShowOverlay / Debug  │   │  Inventory / Debug      │
            └────────────┬──────────┘   └───────────┬─────────────┘
                         │                          │
                         └────────────┬─────────────┘
                                      │ DesktopCharacter (Protocol)
                                      ▼
                       ┌──────────────────────────┐
                       │       PetController      │
                       │  ┌────────────────────┐  │
                       │  │ AnimationPlayer    │  │
                       │  │ BehaviorPhase/…    │  │
                       │  │ ModeController     │  │
                       │  │ PathExecutor       │  │
                       │  │ PetRuntimeResources│  │
                       │  └────────────────────┘  │
                       └──┬──────────┬──────────┬─┘
                          │          │          │
                ┌─────────▼─┐  ┌─────▼─────┐  ┌─▼──────────────┐
                │ PathFinder│  │ PhysicsEng│  │  BehaviorState │
                │  + Planner│  │           │  │    Machine     │
                └─────┬─────┘  └─────┬─────┘  └────────────────┘
                      │              │
                      └──────┬───────┘
                             ▼
                ┌─────────────────────────────┐
                │     EnvironmentSnapshot     │
                │  ┌──────────┐  ┌─────────┐  │
                │  │  Sensors │  │Platform │  │
                │  │ (Win32)  │→ │ Mapper  │  │
                │  └──────────┘  └─────────┘  │
                └─────────────────────────────┘
```

**单帧主循环**（见 [sprite_window.py:59](desktop_sprite/ui/sprite_window.py#L59)）：

1. `SpriteWindow._tick` 由 QTimer 按 `1000 / app.fps` 触发；
2. 调用 `character.tick(dt)`，内部按顺序：
   - `BehaviorOrchestrator.tick` 推进当前行为相位；
   - `DesktopEnvironment.snapshot` 刷新桌面/工作区/任务栏/窗口列表并生成 `Platform` 列表；
   - `PetController._update_behavior` 选择执行 `_execute_path_plan` / `_update_show` / 自由行为；
   - `PhysicsEngine.update` 推进位置、解决落地、夹紧到工作区/屏幕；
   - `PetRuntimeResources.tick` 推进体力/精力/饱腹；
3. `SpriteWindow` 读取 `CharacterRenderState` 调整大小、位置、触发 `update()` 走 `paintEvent` 渲染；
4. 如果开启了 `debug_draw`，同步更新 `DebugOverlayWindow`。

---

## 模块详解

### app.py 入口

[app.py](app.py) 只是一个 `from desktop_sprite.app import main` 的转发。真正的装配在 [desktop_sprite/app.py](desktop_sprite/app.py)：

- 解析 `config/default.json` 与 `config/user/user.json`；
- 创建 `QApplication`，绑定 `SIGINT` 退出、`always_on_top`、高 DPI 策略；
- 通过 `character_factory.create_character(config, character_type=...)` 构造 `PetController`；
- 创建 `SpriteWindow`（桌宠）、`TargetSelectorOverlay`（选目标）、`ShowOverlayWindow`（Show 标题层）、`TrayController`（托盘）；
- 懒加载 `MainWindow`：第一次从托盘/「启动」页进入时构造，注入 `ConfigEditor`、养成/背包/调试子页以及灵痕修改的回调；
- 提供 `restart_pet` / `apply_runtime_config` / `quit_app` 等运行时函数。

### core · 行为/物理/寻路核心

| 文件 | 职责 |
| --- | --- |
| [character.py](desktop_sprite/core/character.py) | 定义 `DesktopCharacter` 协议、`CharacterRenderState` 与 `CharacterDebugState` 数据类。 |
| [character_factory.py](desktop_sprite/core/character_factory.py) | `create_character(config, character_type)` 工厂（当前固定返回 `PetController`）。 |
| [pet_controller.py](desktop_sprite/core/pet_controller.py) | **主控**：拥有 `Pet`、`DesktopEnvironment`、`PhysicsEngine`、`PathFinder`、`PathExecutor`、`ModeController`、`BehaviorOrchestrator`、`BehaviorStateMachine`、`AnimationPlayer`、`PetRuntimeResources`，是桌宠完整状态机的入口。 |
| [physics_engine.py](desktop_sprite/core/physics_engine.py) | 物理求解器：根据 `support_surface_id` 决定是否施加重力；落点检测（候选平台取 top 最小）；拖拽/攀爬/屏幕外夹紧；动态平台向上跟随；`MotionEvents` 把 `landed_on` / `support_lost` / `clamped_to_*` 通知给上层。 |
| [pathfinding.py](desktop_sprite/core/pathfinding.py) | `SurfaceGraph` + `PathFinder`：将平台/墙同构为 `Surface`（`HORIZONTAL/VERTICAL`），按事件点（`JUMP_POINT/DROP_POINT/TRANSFORM_POINT`）连边，统一 `MOVE/JUMP/TRANSFORM/FALL` 代价模型。 |
| [path_executor.py](desktop_sprite/core/path_executor.py) | `PathExecutor`：拿到 `PathStep` 后分派执行：沿水平/竖直轴移动、起跳（含 `_compute_jump_velocity_to` 弹道反解）、`TRANSFORM` 在墙/平台之间瞬切、`FALL` 切到 `FALL` 态让物理引擎接管。 |
| [planner.py](desktop_sprite/core/planner.py) | `GraphPlanner.shortest_path_tree`：Dijkstra，返回前驱表。 |
| [reachability_policy.py](desktop_sprite/core/reachability_policy.py) | 早期能力评估（最大跳高/跳距/传送/下落/攀爬），目前 `PathFinder` 自身已实现等价判定，作为对外能力说明保留。 |
| [behavior_state_machine.py](desktop_sprite/core/behavior_state_machine.py) | `BehaviorStateMachine` + `ALLOWED_TRANSITIONS` 表，控制所有 `PetState` 之间的合法切换。 |
| [behavior_orchestrator.py](desktop_sprite/core/behavior_orchestrator.py) | `BehaviorOrchestrator`：跟踪高层行为相位（`IDLE_WAIT / PATH_PLANNING / PATH_EXECUTING / PATH_FINISHED / SHOW_*`），并对 Show 阶段提供序列推进（`SHOW_PHASE_SEQUENCE`）。 |
| [pet_mode.py](desktop_sprite/core/pet_mode.py) | `PetMode`（`IDLE/GO_TO_TARGET/SHOW`）与 `ModeController`：可锁的全局模式切换，Show 模式下锁住防止被路径执行改写。 |
| [animation_player.py](desktop_sprite/core/animation_player.py) | 状态→动画参数映射（`DEFAULT_ANIMATIONS`），提供 `phase / previous_phase / blend_alpha` 三元组供 `PoseBuilder` 做插值。 |

**关键流程：执行一个目标点**（[PetController.set_target_surface_point](desktop_sprite/core/pet_controller.py#L239)）

1. `PathFinder.find_path_to_surface_point` 构造 `SurfaceGraph` 并查 `Surface`；
2. 若 start/target 是同一表面，返回 `PathPlan` 仅含一条 `MOVE` 步；
3. 否则在 `start_node` 与 `target_node` 之间跑 Dijkstra，把 `NavEdge` 序列映射为 `PathStep`；
4. `_start_path_plan` 切换 `ModeController` 到 `GO_TO_TARGET` 并通知 `BehaviorOrchestrator`；
5. 下一帧 `_update_behavior` 走到 `_execute_path_plan` → `PathExecutor` 按步执行，直到 `_finish_path_plan` 回到 `IDLE` 并挑选新的随机目标。

### environment · 桌面环境感知

| 文件 | 职责 |
| --- | --- |
| [desktop_environment.py](desktop_sprite/environment/desktop_environment.py) | 聚合 `Screen/Taskbar/Window/PlatformMapper` 生成 `EnvironmentSnapshot`。 |
| [screen_sensor.py](desktop_sprite/environment/screen_sensor.py) | 优先用 Qt 主屏 API（`qt_primary_screen_rects`）拿真实坐标；回退到 `GetSystemMetrics` + `SystemParametersInfo(SPI_GETWORKAREA)`。 |
| [taskbar_sensor.py](desktop_sprite/environment/taskbar_sensor.py) | 通过 `FindWindowW("Shell_TrayWnd", None)` + `GetWindowRect` 取任务栏矩形，并用 `normalize_win32_rect_to_qt` 处理高 DPI 缩放。 |
| [window_sensor.py](desktop_sprite/environment/window_sensor.py) | `EnumWindows` 枚举可见窗口，过滤掉自身/任务栏/桌面类、过小窗口、空标题，排序时把前台窗口置顶。 |
| [platform_mapper.py](desktop_sprite/environment/platform_mapper.py) | **环境 → 平台** 的关键映射：每个窗口产出 3 个 `Platform`（顶部=可走平台、左右=可攀爬墙，全部标记 `dynamic=True`），加 `ground:work_area` 与可选的 `taskbar:main`。 |
| [environment_snapshot.py](desktop_sprite/environment/environment_snapshot.py) | 不可变快照：屏幕/工作区/任务栏/窗口列表/`Platform` 列表/时间戳，并提供 `platform_by_id` 与 `foreground_window` 访问。 |

### models · 领域模型

| 文件 | 职责 |
| --- | --- |
| [geometry.py](desktop_sprite/models/geometry.py) | `Vec2`、`Rect`（`overlaps_x/overlaps_y/intersects/contains_point/clamp_point/is_valid`）。 |
| [state.py](desktop_sprite/models/state.py) | `PetState`/`Facing` 枚举与 `Pet` 数据类（`position/velocity/width/height/state/support_surface_id/target_surface_id/state_time/drag_positions` 等）。 |
| [platform.py](desktop_sprite/models/platform.py) | `PlatformType`（`GROUND/TASKBAR/WINDOW_TOP/WINDOW_LEFT/WINDOW_RIGHT`）与 `Platform` 不可变记录。 |
| [platform_topology.py](desktop_sprite/models/platform_topology.py) | 平台 ID 命名工具（`window:{hwnd}:top/left/right`），便于上层无歧义引用。 |
| [window_info.py](desktop_sprite/models/window_info.py) | `WindowInfo` 不可变记录。 |
| [pet_attribute.py](desktop_sprite/models/pet_attribute.py) | 15 个属性定义（`PET_ATTRIBUTE_DEFINITIONS`）+ `PetAttributeSheet`（带 `flat/percent` 修饰器聚合）+ `PetEffectiveStats`（把 sheet 翻译为物理/体力/精力/Show 参数等运行时数值）+ `PetRuntimeResources`（体力/精力/饱腹三元组）+ `PetResourceInfluence`（按状态输出的「衰减/睡眠/寻食/休息」建议与运动/跳跃/特殊能力乘子）。 |
| [inventory.py](desktop_sprite/models/inventory.py) | 道具目录（`items.json`）+ 背包条目（`inventory.json`）的加载/校验/合并；自动把 `spirit_marks.json` 中的灵痕信息回填到道具 `details`。 |
| [spirit_mark.py](desktop_sprite/models/spirit_mark.py) | 灵痕领域：`SpiritMarkSlot` × 5、`SpiritMarkSet` × 5、品质/强化/分解/装备/收藏/裂纹、材料（`SpiritMarkMaterials`）、`SpiritMarkInventory` 的全部操作（`equip/unequip/enhance/decompose/stat_totals/attribute_modifiers`），以及 `generate_spirit_mark` 概率卷轴。 |
| [spirit_mark_service.py](desktop_sprite/models/spirit_mark_service.py) | `grant_spirit_mark(request, items_path, inventory_path, spirit_mark_path)`：同时写 `inventory.json` 与 `spirit_marks.json` 并返回最新 `InventorySnapshot` 与 `SpiritMarkInventory`。 |

### ui · 视图层与渲染

| 文件 | 职责 |
| --- | --- |
| [sprite_window.py](desktop_sprite/ui/sprite_window.py) | 桌宠窗口本体（透明/置顶/无边框），接管 `mousePress/Move/Release/DoubleClick` → `start_drag/drag_to/release_drag/poke`；`paintEvent` 调用 `PetRenderer.draw_pose` 渲染；可选 `DebugOverlayWindow` 全屏覆盖层可视化环境/导航/路径/碰撞框/资源/路径步骤。 |
| [pet_renderer.py](desktop_sprite/ui/pet_renderer.py) | 由 `RenderPose` 描述的几何/颜色画到 QPainter：影子、双翅（羽根/主羽/次羽 + 翼膜）、四肢（双段折线 + 终端椭圆）、身体（背/前/高光）、围巾（带 + 尾三角）、眼睛（含睡眠横线）。 |
| [render_pose.py](desktop_sprite/ui/render_pose.py) | `PosePoint / PoseRect / LimbPose / BodyPose / EyePose / WingPose / ScarfPose / RenderPose` 等不可变数据结构 + `PoseBuilder`：根据 `PetState` 与 `effective_stats()` 拼出当前帧的姿态；支持与前态 `blend` 插值。 |
| [main_window.py](desktop_sprite/ui/main_window.py) | `FluentWindow` 主窗口：9 个子页（启动/实时触发/养成/背包/全自动/辅助操控/调试/通知/设置），`FluentWindow` 风格的左侧导航；保存主窗口几何到 `ui_state.json`。 |
| [config_editor.py](desktop_sprite/ui/config_editor.py) | 键路径化的 `ConfigEditorWidget`：基于 `SettingCard` 把 `default.json` 渲染成可编辑控件，保存时仅写回 `user.json`（保留默认值）；支持撤销/恢复默认。 |
| [inventory_widget.py](desktop_sprite/ui/inventory_widget.py) | 分类页签（`SegmentedWidget`）+ 卡片网格 + `SmoothScrollArea`（支持鼠标拖动滚动）+ 详情卡（`InventoryDetailsCard`），纯 QPainter 自绘卡片背景与边框。 |
| [growth_widget.py](desktop_sprite/ui/growth_widget.py) | 养成：左栏 6 个属性（图标 + 名称 + 公式/加成 + 进度条）、右栏灵痕（5 个槽位卡片 + 操作按钮）。属性展示使用 `PET_ATTRIBUTE_DEFINITIONS`，灵痕操作走 `SpiritMarkInventory.equip/unequip/enhance/decompose` 等方法。 |
| [debug_widget.py](desktop_sprite/ui/debug_widget.py) | 调试页：调用 `app.on_debug_request_spirit_mark`（封装了 `grant_spirit_mark`）触发一次灵痕生成并显示结果。 |
| [show_overlay.py](desktop_sprite/ui/show_overlay.py) | Show 模式全屏覆盖：跟随角色 debug 状态、33ms 刷新，仅在 `PetMode.SHOW` 期间可见，绘制 `SHOW_TITLE` 文字（默认"苍翼裁决者"）。 |
| [target_selector.py](desktop_sprite/ui/target_selector.py) | `select_target_candidate` 计算点击位置下方/上方的可走平台候选，并提供 `TargetSelectorOverlay` 全屏选目标覆盖层。 |
| [tray_controller.py](desktop_sprite/ui/tray_controller.py) | `QSystemTrayIcon` 控制器：托盘菜单（展示 / 设置目标点 / 退出）、单击或双击托盘打开主窗口。 |

### utils · 配置/DPI/日志/平台工具

| 文件 | 职责 |
| --- | --- |
| [config.py](desktop_sprite/utils/config.py) | `AppConfig` 与各子 dataclass（`RuntimeConfig / PetConfig / PhysicsConfig / BehaviorConfig / AttributesConfig / InteractionConfig / CharacterConfig`），`load_config(path, user_path)` 解析默认+用户+角色档案三层合并并把 `pet` 段中的 `walk/climb/jump_speed_*` 注入到 `physics`。 |
| [dpi.py](desktop_sprite/utils/dpi.py) | Qt 主屏矩形 + `devicePixelRatio`、Win32 矩形→Qt 矩形归一化。 |
| [logger.py](desktop_sprite/utils/logger.py) | 标准 `logging.basicConfig`，按 `config.app.log_level` 调整级别。 |
| [win_api.py](desktop_sprite/utils/win_api.py) | 简单的 `is_windows()` 判定。 |

---

## 数据文件与存档

| 路径 | 说明 |
| --- | --- |
| `config/default.json` | 唯一默认配置；可手动编辑。 |
| `config/characters/pet.json` | 角色档案（尺寸/生成点/移动参数/翅膀/悬停）。 |
| `config/items.json` | 道具目录（分类 + 道具定义）。 |
| `config/user/user.json` | 用户配置覆盖，运行期由「设置」页写入。 |
| `config/user/inventory.json` | 背包条目，运行期由灵痕生成或后续玩法写入。 |
| `config/user/spirit_marks.json` | 灵痕存档，包含 marks + materials。 |
| `config/user/ui_state.json` | 管理界面（主窗口几何、设置卡片展开状态等）。 |
| `assets/spirit_mark/sanctum_radiance/*.png` | 灵痕图标（5 个部位）。 |
| `assets/test/sanctum_radiance/*.png` | 可堆叠的测试道具图标。 |

灵痕生成的入口是 [spirit_mark_service.grant_spirit_mark](desktop_sprite/models/spirit_mark_service.py#L30)：

```python
from desktop_sprite.models.spirit_mark import SpiritMarkGrantRequest, grant_spirit_mark

result = grant_spirit_mark(
    SpiritMarkGrantRequest(
        source_type="debug",
        source_id="management-debug",
        source_description="…",
        quality_hint="completed",  # 影响最低品质
        record_tags=("debug",),
    ),
    items_path="config/items.json",
    inventory_path="config/user/inventory.json",
    spirit_mark_path="config/user/spirit_marks.json",
)
# result.mark / result.inventory_snapshot / result.spirit_mark_inventory
```

生成的灵痕在被装备（`SpiritMarkInventory.equip`）后，其主副词条 + 套装 2 件套效果会自动转换为 `PetAttributeModifier`，并通过 `PetAttributeSheet.with_modifiers` 注入到 `PetAttributeSheet`，再由 `PetEffectiveStats.from_sheet` 影响实际的物理/体力/精力/展示参数。

---

## 测试

```powershell
pytest
```

21 个测试文件（[tests/](tests/)）覆盖：

- `test_geometry` —— `Rect`/`Vec2` 的几何方法；
- `test_screen_boundary` —— 屏幕/工作区夹紧；
- `test_platform_mapper` —— 窗口/任务栏 → 平台映射；
- `test_physics` —— 平台落地、掉落、攀爬支持、动态平台跟随；
- `test_pathfinding` —— 表面图、跨平台/跨墙跳跃、悬挂下落、不可达判定；
- `test_pet_controller_climb_reach` —— 桌宠是否能抓到墙；
- `test_state_machine` —— `PetState` 合法转换；
- `test_mode_and_orchestrator` —— `ModeController`/`BehaviorOrchestrator`；
- `test_pet_attribute` —— 属性 sheet、modifier、effective stats、resources 衰减；
- `test_spirit_mark` —— 生成/强化/分解/装备/属性聚合；
- `test_spirit_mark_service` —— `grant_spirit_mark` 端到端；
- `test_inventory` —— 目录与存档加载；
- `test_inventory_widget` —— 分类过滤、卡片构造；
- `test_growth_widget` —— 养成页 attribute 渲染；
- `test_pet_renderer` / `test_pose_builder` —— 渲染层；
- `test_target_selector` —— 候选平台过滤；
- `test_main_window` —— 9 个子页注册；
- `test_config_editor` —— JSON 键路径编辑、保存到 user.json；
- `test_debug_widget` —— 调试页的回调绑定；
- `test_app` —— 启动入口。

---

## 扩展指引

- **新增一种 PetState**：在 [state.py](desktop_sprite/models/state.py) 添加枚举值 → 在 [behavior_state_machine.py](desktop_sprite/core/behavior_state_machine.py) 的 `ALLOWED_TRANSITIONS` 中登记合法转换 → 在 [animation_player.py](desktop_sprite/core/animation_player.py) 的 `DEFAULT_ANIMATIONS` 中添加帧规格 → 在 [pet_controller.py](desktop_sprite/core/pet_controller.py) 中实现驱动逻辑 → 在 [pet_attribute.py](desktop_sprite/models/pet_attribute.py) 的 `_stamina_cost_for_state/_satiety_cost_for_state` 中加入资源消耗。
- **新增一种角色**：[character.py](desktop_sprite/core/character.py) 增加 `DesktopCharacter` 协议的实现 → [character_factory.py](desktop_sprite/core/character_factory.py) 在 `create_character` 中按 `--character` 名字分发 → 在 [config/characters/](config/characters/) 中添加新档案。
- **新增灵痕套装/部位**：[spirit_mark.py](desktop_sprite/models/spirit_mark.py) 中扩展 `SPIRIT_MARK_SLOTS`/`SPIRIT_MARK_SETS` 与 `PRIMARY_STAT_POOLS`；图标放到 `assets/spirit_mark/{set_id}/` 并在 [items.json](config/items.json) 中注册。
- **新增一种动作到 `TraversalAction`**：[pathfinding.py](desktop_sprite/core/pathfinding.py) 的 `SurfaceGraph` builder 中按规则连边 + 设置代价；[path_executor.py](desktop_sprite/core/path_executor.py) 增加执行分支；UI 调试覆盖层 `_graph_edge_color` 中加配色。
- **新增 Show 阶段**：在 [behavior_orchestrator.py](desktop_sprite/core/behavior_orchestrator.py) 的 `SHOW_PHASE_SEQUENCE` 与 `BehaviorPhaseName` 中插入；[pet_controller.py](desktop_sprite/core/pet_controller.py) 的 `_start_show_phase_ability` 中实现对应能力。
- **新增管理窗口子页**：在 [main_window.py](desktop_sprite/ui/main_window.py) 的 `_add_interfaces` 注册一个 `(page, icon, title, position)` 元组并实现 `_*_page` 工厂方法。

---

## 路线与 TODO

- [ ] 桌面快捷方式组：快速切换不同预设的快捷方式（如工作模式、娱乐模式等）。
- [ ] 进一步的寻路性能优化：空间索引、候选剪枝、增量图更新（参见 [PATHFINDING.md](PATHFINDING.md) 末尾的"二阶段增强"）。
- [ ] 自动运行策略页与辅助操控页从占位升级为真实功能。
- [ ] 通知中心页从占位升级为真实消息/提醒系统。
- [ ] 多分辨率/多显示器高 DPI 边界（参见 [system_design/](system_design/) 下的设计文档）。

---

### 相关设计文档

- [PATHFINDING.md](PATHFINDING.md) · 寻路系统重构方案
- [system_design/desktop_sprite_plan.md](system_design/desktop_sprite_plan.md) · 桌宠整体规划
- [system_design/桌宠属性.md](system_design/桌宠属性.md) · 属性体系设计
- [system_design/灵痕系统设计.md](system_design/灵痕系统设计.md) · 灵痕体系设计
- [system_design/专注系统设计.md](system_design/专注系统设计.md) · 专注模式设计
- [system_design/灵痕绘制prompt.md](system_design/灵痕绘制prompt.md) · 灵痕视觉规范
- [system_design/灵痕部位图标设计规范*.md](system_design/) · 灵痕图标规范
- [system_design/PBD史莱姆软体模拟技术方案.md](system_design/PBD史莱姆软体模拟技术方案.md) · 软体模拟方案
- [system_design/prompts.md](system_design/prompts.md) · 资源生成 prompt 记录
