# `desktop_sprite.core` — 桌宠核心域模型

将桌宠的"状态机 + 行为编排 + 物理 + 寻路 + 路径执行 + 动画"拆分到无 UI 依赖的纯 Python 类中，供 `character_factory` 装配成 `DesktopCharacter` 协议对象。本包约 3500 行，14 个文件；外部只应该 import `PetController`（通过 `core/__init__.py` re-export）或通过 `core.character_factory.create_character` 拿到协议对象。

> 与本 README 互补：
> - 数据模型（`Pet` / `PetState` / 16 个属性 / 灵痕领域）见 [../models/README.md](../models/README.md)
> - 环境感知（`EnvironmentSnapshot` / `PlatformMapper`）见 [../environment/README.md](../environment/README.md)
> - 配置 dataclass 与 `load_config` 见 [../utils/README.md](../utils/README.md)

---

## 目录

- [文件清单](#文件清单)
- [核心门面：`PetController`](#核心门面petcontroller)
- [Show 子系统：`PetShowDirector`](#show-子系统petshowdirector)
- [状态/相位协调者：`PetStateMediator`](#状态相位协调者petstatemediator)
- [行为编排：`BehaviorOrchestrator` + `BehaviorPhaseTracker` + `BehaviorSequence`](#行为编排behaviororchestrator--behaviorphasetracker--behaviorsquence)
- [物理 + 状态机 + 模式锁](#物理--状态机--模式锁)
- [寻路 + 路径执行 + 图算法](#寻路--路径执行--图算法)
- [动画 + 角色协议 + 工厂](#动画--角色协议--工厂)
- [包内模块依赖图](#包内模块依赖图)
- [公开 API vs 内部 API](#公开-api-vs-内部-api)
- [算法复杂度汇总](#算法复杂度汇总)
- [反射式测试访问入口](#反射式测试访问入口)

---

## 文件清单

| 路径 | 角色 | 行数级 |
| --- | --- | --- |
| `__init__.py` | 仅 re-export `PetController` | 极小 |
| [`pet_controller.py`](pet_controller.py) | 顶层 Facade，唯一 `DesktopCharacter` 协议实现 | 800 |
| [`pet_state_mediator.py`](pet_state_mediator.py) | 状态/相位/模式协调者 | 140 |
| [`pet_show_director.py`](pet_show_director.py) | Show 序列（展翅→飞→悬停→标题→着陆→收翅）导演 | 306 |
| [`show_phase_durations.py`](show_phase_durations.py) | Show 调参常量 | 23 |
| [`behavior_orchestrator.py`](behavior_orchestrator.py) | 相位门面（`BehaviorPhaseTracker` + `BehaviorSequence`） | 205 |
| [`behavior_state_machine.py`](behavior_state_machine.py) | 纯 `PetState` 合法转移表 | 33 |
| [`pet_mode.py`](pet_mode.py) | 粗粒度模式锁 | 37 |
| [`physics_engine.py`](physics_engine.py) | 物理积分 + 平台求交 | 202 |
| [`pathfinding.py`](pathfinding.py) | 寻路（surface graph + Dijkstra） | 646 |
| [`path_executor.py`](path_executor.py) | 路径执行 + 跳跃速度解算 | 235 |
| [`planner.py`](planner.py) | 纯算法 Dijkstra | 37 |
| [`animation_player.py`](animation_player.py) | 帧动画 + 两态插值 | 85 |
| [`character.py`](character.py) | `DesktopCharacter` 协议 + 渲染/调试状态 | 65 |
| [`character_factory.py`](character_factory.py) | `create_character(config)` 工厂 | 9 |

---

## 核心门面：`PetController`

`PetController` 是 `DesktopCharacter` 协议的唯一实现。它聚合 physics / pathfinder / path_executor / mediator / show-director / animation / environment snapshot；将用户交互（拖、戳、睡）映射为状态机迁移 + 路径规划 + 物理更新 + 动画帧推进。

### 公开方法

| 签名 | 行为 |
| --- | --- |
| `__init__(self, config: AppConfig)` | 构造：建 mediator / show_director / path_finder / path_executor / physics / animation_player |
| `set_own_window_handle(self, hwnd: int \| None)` | 把自己窗口的 hwnd 透传给 `environment` 采集层（用于窗口枚举时剔除自己） |
| `apply_config(self, config: AppConfig)` | 替换 `AppConfig` 后重算 effective stats |
| `set_attribute_sheet(self, sheet: PetAttributeSheet)` | 用 `sheet.with_modifiers(...)` 重算属性 |
| `effective_stats(self) -> PetEffectiveStats` | 当前生效的属性→物理/行为参数 |
| `runtime_physics(self) -> PhysicsConfig` | 在 `effective_stats().physics` 上叠 `PetResourceInfluence` 后的最终 physics |
| `tick(self, dt: float)` | 每帧：刷 physics config → `orchestrator.tick` → 必要时 refresh environment → show 模式调 `_update_show`、否则 `_update_behavior` + physics + motion-events 应用 + 资源 tick + animation |
| `start_drag / drag_to / release_drag(mouse_x, mouse_y)` | 拖拽三段 |
| `poke(self)` | 双击 / 戳 |
| `sleep(self) -> bool` | 切到 SLEEP（条件：未锁模式 + stamina 不足） |
| `set_target_surface_point(self, surface_id, anchor_t) -> bool` | 调 `PathFinder.find_path_to_surface_point` 然后 `_start_path_plan` |
| `start_show(self) -> bool` | 构造 `ShowContext`（`SHOW_RENDER_SCALE_X/Y` 放大渲染尺寸）→ `mode_controller.set_mode(SHOW, force=True, lock=True)` → `orchestrator.begin_show()` → `PetShowDirector.start(self, ctx)` |
| `render_state(self) -> CharacterRenderState` | Show 模式下放大 `width/height` 并加 `body_offset_*` |
| `debug_state(self) -> CharacterDebugState` | 暴露 `snapshot/pathfinder/path_plan/physics/mode/phase/phase_elapsed` |

### 类常量

- `WALK_TARGET_ARRIVAL_DISTANCE = 0.8`
- `PetAbility = WingAbility | FlightAbility | HoverAbility`（类型别名，从 `pet_show_director` 透传）

### 私有方法（核心实现 + 8 个 Show 转发方法）

**核心域逻辑**：`_ensure_runtime_layers`、`_refresh_environment_if_needed`、`_update_behavior`、`_execute_path_plan`、`_walk_toward_x`、`_advance_path_if_reached`、`_finish_path_plan`、`_validate_path_plan`、`_start_path_plan`、`_clear_path_plan`、`_enter_idle_mode`、`_is_path_step_present`、`_is_show_mode`、`_update_show`、`_finish_show`、`_executor`、`_maybe_grab_climb_side_while_jumping`、`_snap_to_climb_side`、`_keep_walking_on_platform`、`_start_random_wander`、`_random_reachable_platform_plan`、`_random_point_plan`、`_reachable_surface_ids`、`_random_x_on_platform`、`_pick_new_idle_goal`、`_transition`、`_apply_motion_events`、`_record_drag`、`_drag_throw_velocity`、`_refresh_effective_stats`、`_tick_resources`、`_resource_influence`、`_apply_resource_behavior`。

**Show 转发方法**（`PetShowDirector` 公开 API 的薄包装，行为仅为"转发到 director"）：`_start_show_phase_ability`、`_start_open_wings`、`_start_close_wings`、`_start_flight_to`、`_start_hover`、`_update_pet_ability`、`_update_flight_ability`、`_update_hover_ability`。

### 模块级函数

```python
def replace_physics_movement(physics: PhysicsConfig, influence: PetResourceInfluence) -> PhysicsConfig
```

把 `PetResourceInfluence` 的 `movement_factor / climb_factor / jump_factor` 应用到原始 physics 副本。

### `__getattr__` 转发

```python
_MEDIATOR_FORWARD = frozenset({"mediator", "state_machine", "orchestrator", "mode_controller"})

def __getattr__(self, name: str):
    if name in _MEDIATOR_FORWARD and "mediator" not in self.__dict__:
        raise AttributeError(name)
    if name in _MEDIATOR_FORWARD:
        mediator = self.__dict__["mediator"]
        return getattr(mediator, name)  # 转发
    raise AttributeError(name)
```

转发 `{mediator / state_machine / orchestrator / mode_controller}` 四个 mediator 子字段。**生产代码应直接读 `self.mediator`，不要依赖转发**；该转发支持 `test_pet_controller_climb_reach.py` 等反射式访问。

---

## Show 子系统：`PetShowDirector`

[`pet_show_director.py`](pet_show_director.py) 是 Show 序列（OPEN_WINGS → FLY → HOVER → TITLE → LAND → CLOSE_WINGS）的导演。导演无自有状态，只在 `start/update/finish` 中改写 controller 的 `pet` / `_active_pet_ability` / mode / orchestrator。

### 公开 dataclass

| 类型 | 字段 |
| --- | --- |
| `ShowContext` | `start_x/y`、`hover_x/y`、`land_x/y`、`render_width/height` |
| `WingAbility` | `state: PetState`、`duration: float`、`elapsed: float = 0.0` |
| `FlightAbility` | `start_x/y`、`target_x/y`、`speed: float`、`state: PetState` |
| `HoverAbility` | `base_x/y`、`duration: float \| None = None`、`elapsed: float = 0.0` |

`PetAbility = WingAbility | FlightAbility | HoverAbility`。

### `PetShowDirector` 公开方法

| 签名 | 行为 |
| --- | --- |
| `start(self, controller, context: ShowContext) -> None` | 重置 controller 的 `path_plan` / 目标 / 速度 / `_active_pet_ability`，启动 `SHOW_OPEN_WINGS` 阶段 |
| `update(self, controller, dt: float) -> bool` | 返回 `True` 表示序列结束。特殊处理：`SHOW_HOVER` 阶段在 `elapsed >= SHOW_HOVER_SECONDS` 时主动 `advance_sequence`，确保标题能浮现 |
| `finish(self, controller) -> None` | 落点定位 → 解锁 mode → 切回 IDLE |

私有 phase-dispatch 段：`_start_phase_ability`、`_start_open_wings`、`_start_close_wings`、`_start_flight_to`、`_start_hover`、`_update_ability`、`_update_flight`、`_update_hover`。

### Re-export（`pet_controller` 顶部）

`pet_controller.py` 顶部 `from desktop_sprite.core.pet_show_director import HoverAbility, WingAbility, SHOW_HOVER_SECONDS` 透传给 `from desktop_sprite.core.pet_controller import ...` 的导入路径。

### 常量

[`show_phase_durations.py`](show_phase_durations.py)：

```python
SHOW_RENDER_SCALE_X = 4.6
SHOW_RENDER_SCALE_Y = 3.8
SHOW_HOVER_SECONDS = 0.5
SHOW_TITLE_SECONDS = 3.2
```

---

## 状态/相位协调者：`PetStateMediator`

[`pet_state_mediator.py`](pet_state_mediator.py) 是 `Pet.state` 的合法写源，集中维护 `Pet.state` ↔ `BehaviorStateMachine.state` ↔ `BehaviorOrchestrator.phase` ↔ `ModeController.mode/locked` 的同步。

### `PetStateMediator` 公开 API

| 签名 | 行为 |
| --- | --- |
| `__init__(pet, state_machine, orchestrator, mode_controller)` | 持有四个相关对象 |
| `transition(target: PetState) -> bool` | `state_machine.state = self.pet.state` → `state_machine.transition(target)` → 成功时写回 `pet.state` + `pet.state_time = 0.0` |
| `snapshot_state() -> None` | 仅在外部（physics 引擎等）绕过 mediator 改过 `pet.state` 时使用 |
| `is_show / is_dragged / mode / mode_locked / phase_name / phase_elapsed`（property） | 便捷查询 |
| `begin_phase(name) / advance_phase(name)` | 调 `orchestrator.begin / advance` |
| `begin_show() / advance_sequence() / is_sequence_complete()` | Show 序列推进 |
| `set_mode(mode, *, force=False, lock=False) -> bool` | 模式锁切换 |
| `unlock() / unlock_and_idle()` | Show 模式 teardown 辅助 |

---

## 行为编排：`BehaviorOrchestrator` + `BehaviorPhaseTracker` + `BehaviorSequence`

[`behavior_orchestrator.py`](behavior_orchestrator.py) 把"当前阶段"和"Show 序列"两职责分配给两个协作者，外加 facade：

### 枚举与常量

```python
class BehaviorPhaseName(StrEnum):
    IDLE_WAIT / PATH_PLANNING / PATH_EXECUTING / PATH_FINISHED
    SHOW_OPEN_WINGS / SHOW_FLY / SHOW_HOVER / SHOW_TITLE / SHOW_LAND / SHOW_CLOSE_WINGS

SHOW_PHASE_SEQUENCE: tuple[BehaviorPhaseName, ...]  # Show 阶段定长序列
```

### 三层结构

| 组件 | 角色 | 公开 API |
| --- | --- | --- |
| `BehaviorPhase`（`slots=True`） | 当前相位数据 | `name`、`elapsed: float = 0.0` |
| `BehaviorPhaseTracker` | 纯进度跟踪 | `__init__(initial_phase=IDLE_WAIT)`、`begin(name)`、`advance(name)`（同 begin）、`tick(dt)`（`elapsed += max(dt, 0.0)`）、`reset()` |
| `BehaviorSequence` | 纯 Show 序列指针 | `begin_show()`、`reset()`、`is_complete() -> bool`、`current_phase_name() -> BehaviorPhaseName \| None`、`advance()`（末步后置 `_complete = True`） |
| `BehaviorOrchestrator`（facade） | 对外统一入口 | `begin / begin_show / advance_sequence / reset`（双写 tracker+sequence）；`@property phase / @phase.setter`（读写 tracker.phase）；`__getattr__` 转发 `tick / advance → tracker`、`is_sequence_complete → self.sequence.is_complete`（命名翻译） |

### `__getattr__` 转发集

```python
_TRACKER_FORWARDED: frozenset[str] = {"tick", "advance"}
```

外部应使用 facade 已暴露的公共名（`tick / advance / is_sequence_complete`）。

---

## 物理 + 状态机 + 模式锁

### [`physics_engine.py`](physics_engine.py)

纯位置积分 + AABB 平台着陆/支撑验证 + 上下界夹紧；无资源/属性耦合，仅消费 `PhysicsConfig`。

```python
@dataclass(slots=True)
class MotionEvents:
    landed_on: str | None = None
    support_lost: bool = False

class PhysicsEngine:
    def __init__(self, config: PhysicsConfig) -> None
    def reconcile_platform_motion(self, pet, previous_snapshot, current_snapshot) -> None  # 动态平台位移补偿
    def update(self, pet, snapshot, dt) -> MotionEvents
```

`update` 主流程：DRAGGED 仅夹紧；CLIMB 校验支持并按速度积分；普通：重力/速度积分 → `_clamp_to_work_area` → `_resolve_platform_landing` → 再夹紧 → `_clamp_to_screen`。

私有方法（全部真实实现）：`_validate_climb_support`、`_resolve_platform_landing`、`_clamp_horizontal`、`_validate_support`、`_clamp_to_work_area`、`_resolve_ceiling_boundary`、`_resolve_floor_boundary`、`_clamp_to_screen`、`_top_platform_id_for`（封装 `PlatformTopology.top_id_for_side`）。

### [`behavior_state_machine.py`](behavior_state_machine.py)

```python
ALLOWED_TRANSITIONS: dict[PetState, set[PetState]]  # 12 个状态全覆盖

class BehaviorStateMachine:
    def __init__(self, initial_state: PetState = FALL) -> None
    def can_transition(self, target: PetState) -> bool
    def transition(self, target: PetState) -> bool
```

无 `_` 前缀私有方法；`state` 字段由 `PetStateMediator.transition` 写入，`snapshot_state()` 是直写专用通道。

### [`pet_mode.py`](pet_mode.py)

```python
class PetMode(StrEnum):
    IDLE = "idle"
    GO_TO_TARGET = "go_to_target"
    SHOW = "show"

class ModeController:
    def __init__(self, initial_mode: PetMode = IDLE) -> None
    def set_mode(self, mode, *, force=False, lock=False) -> bool
    def unlock(self) -> None
    def is_idle(self) / is_go_to_target() / is_show() -> bool
```

字段：`mode`、`locked`。

---

## 寻路 + 路径执行 + 图算法

### [`pathfinding.py`](pathfinding.py) — 寻路（surface graph + Dijkstra）

**枚举**：`SurfaceOrientation`（HORIZONTAL/VERTICAL）、`TraversalAction`（MOVE/JUMP/TRANSFORM/FALL）、`NavNodeKind`。

**frozen dataclass**：`Surface`、`NavNode`、`NavEdge`、`PathStep`。

**`SurfaceGraph`（`slots=True`）**：`nodes`、`adjacency`、`surfaces`；`@property edges`（推导）。

**`PathPlan`（`slots=True`）**：`steps`、`current_index = 0`、`target_window_id`、`snapshot_timestamp`、`target_surface_id`、`target_anchor_t`；`@property current_step / is_complete`、`def advance()`。

**`PathFinder`** 公开方法：

| 签名 | 行为 |
| --- | --- |
| `find_path(self, pet, snapshot, target_window_id, physics) -> PathPlan \| None` | 入口：把"目标窗口"翻译为"窗口顶面 surface + 中心 anchor"后调 `find_path_to_surface_point` |
| `find_path_to_surface_point(self, pet, snapshot, target_surface_id, target_anchor_t, physics, target_window_id=None) -> PathPlan \| None` | 起点终点相同则返回单步 MOVE；否则 `build_surface_graph` → `_ensure_node`(start,target) → `_search` → `_map_edges` → `_merge_consecutive_same_surface_move_steps` |
| `build_surface_graph(self, pet, snapshot, physics) -> SurfaceGraph` | 建图核心：对每条水平 surface 探测左右 DROP；对每对 surface 探测 TRANSFORM（横↔竖）、水平 MOVE（同高度+小缝）、JUMP（解析运动学可达性） |

私有方法（真实实现）：`_ensure_node`、`_rewire_surface_move`、`_search`（委托 `planner.shortest_path_tree`）、`_map_edges`、`_to_path_step`、`_point_move_step`、`_merge_consecutive_same_surface_move_steps`、`_first_horizontal_hit_below`、`_is_drop_side_valid`、`_jump_candidate`、`_jump_reachable`（运动学判可达）、`_can_move_between_horizontals`、`_can_transform_between_surfaces`、`_transform_anchors`、`_can_fall_between_horizontals`、`_horizontal_gap`、`_anchor_interval`、`_closest_values_between_intervals`、`_clamp_value`、`_clamp_anchor`、`_pet_anchor_t`、`_point_for_anchor`、`_move_speed`、`_move_cost`、`_jump_cost`、`_fall_cost`。

### [`path_executor.py`](path_executor.py) — 路径执行

消费 `PathPlan`，逐 `PathStep` 调 pet 速度/状态机；用运动学反解 `compute_jump_velocity_to` 计算抛跳初速度。

```python
class PathExecutor:
    def __init__(self, controller) -> None
    def execute_path_plan(self) -> bool           # 按 current_step.action 分派 TRANSFORM/MOVE/FALL/JUMP
    def walk_toward_x(self, target_x: float) -> bool   # 自由空间兜底"朝 X 走"逻辑
    def move_along_surface(self, surface, target_t) -> bool  # 走水平或爬垂直
```

私有方法（真实实现）：`_move_along_axis`、`execute_move_step`、`start_jump_toward_surface`、`execute_transform_step`、`compute_jump_velocity_to`。

### [`planner.py`](planner.py) — 纯算法 Dijkstra

```python
class GraphPlanner:
    def shortest_path_tree(
        self,
        adjacency: Mapping[str, Sequence["NavEdge"]],
        start_id: str,
        target_id: str,
    ) -> dict[str, tuple[str, "NavEdge"]] | None
```

返回 `{to_id: (parent_id, edge)}`，未找到时 `None`。`PathFinder` 把图结构传进来即可。

---

## 动画 + 角色协议 + 工厂

### [`animation_player.py`](animation_player.py)

```python
@dataclass(frozen=True, slots=True)
class AnimationSpec:
    fps: float
    frame_count: int
    loop: bool = True

DEFAULT_ANIMATIONS: dict[PetState, AnimationSpec]  # 12 个状态全覆盖

class AnimationPlayer:
    def __init__(self) -> None
    def set_state(self, state: PetState) -> None
    def update(self, dt: float) -> int       # 返回新 frame_index
    @property phase / previous_phase / blend_alpha  # smoothstep 缓动
```

字段：`state / previous_state / elapsed / previous_elapsed / transition_elapsed / transition_duration = 0.14 / frame_index = 0`。

### [`character.py`](character.py)

```python
@dataclass(frozen=True, slots=True)
class CharacterRenderState:
    x / y / width / height / body / animation / payload
    body_width / body_height / body_offset_x / body_offset_y

@dataclass(frozen=True, slots=True)
class CharacterDebugState:
    snapshot / pathfinder / path_plan / physics / mode / phase / phase_elapsed

class DesktopCharacter(Protocol):
    def set_own_window_handle(...) / apply_config / set_attribute_sheet
    def effective_stats(...) / tick / start_drag / drag_to / release_drag
    def poke / sleep / set_target_surface_point / start_show
    def render_state(...) / debug_state(...)
```

### [`character_factory.py`](character_factory.py)

```python
def create_character(config: AppConfig, character_type: str | None = None) -> DesktopCharacter
```

仅当 `character_type in {"pet", None}` 时返回 `PetController(config)`（仓库当前实现）。

---

## 包内模块依赖图

```
core/
├── __init__.py ─────────────────► pet_controller (re-export PetController)
│
├── pet_controller.py ─┬─► animation_player
│                       ├─► behavior_orchestrator
│                       ├─► behavior_state_machine
│                       ├─► character
│                       ├─► pathfinding
│                       ├─► path_executor
│                       ├─► pet_mode
│                       ├─► pet_show_director
│                       ├─► pet_state_mediator      ← 惰性 import（避免构造期循环）
│                       ├─► physics_engine
│                       └─► show_phase_durations
│
├── pet_state_mediator.py ─┬─► behavior_orchestrator
│                          ├─► behavior_state_machine
│                          └─► pet_mode
│
├── pet_show_director.py ──┬─► behavior_orchestrator
│                          ├─► pet_mode
│                          └─► show_phase_durations
│
├── show_phase_durations.py     (无 core 内依赖)
├── behavior_orchestrator.py    (无 core 内依赖)
├── behavior_state_machine.py   (仅用 PetState)
├── pet_mode.py                 (无 core 内依赖)
├── physics_engine.py           (依赖 environment / models / utils)
│
├── pathfinding.py ────────► planner
├── path_executor.py ──────► pathfinding
├── planner.py                  (无 core 内 import)
├── animation_player.py         (仅依赖 models.state)
├── character.py ────────► animation_player, behavior_orchestrator, pathfinding, pet_mode
└── character_factory.py ────► character, pet_controller
```

**环路检查**：无循环依赖。`pet_controller` → `pet_state_mediator`（惰性 import 避免构造期循环）；`character_factory` → `pet_controller` → 一切。

---

## 公开 API vs 内部 API

### 外部应该 import

| 用途 | 入口 |
| --- | --- |
| 装配桌宠 | `desktop_sprite.core.character_factory.create_character(config, character_type="pet")` |
| 类型注解 / 协议 | `DesktopCharacter`、`CharacterRenderState`、`CharacterDebugState` |
| 枚举/常量 | `BehaviorPhaseName`、`PetMode`、`PetState`、`PetAbility`、`ShowContext`、`SHOW_HOVER_SECONDS` / `SHOW_TITLE_SECONDS` / `SHOW_RENDER_SCALE_*` |
| 扩展点 | `AnimationSpec` / `DEFAULT_ANIMATIONS`（新动画）、`GraphPlanner`（自定义最短路算法） |

### 外部不应该用

| 名字 | 为什么 |
| --- | --- |
| `PetController.__getattr__` 转发集（`mediator / state_machine / orchestrator / mode_controller`） | 反射式访问入口；生产代码直接 `controller.mediator` |
| `PetController._start_open_wings / _start_close_wings / _start_flight_to / _start_hover / _start_show_phase_ability / _update_pet_ability / _update_flight_ability / _update_hover_ability` | Show 转发方法；外部应让 `controller.tick` 自动驱动 |
| `PetController._is_show_mode / _ensure_runtime_layers / _transition` | 实现细节 |
| `pet_show_director._update_flight / _update_hover / _update_ability` | Director 内部用 |
| `PathFinder._*` 全套私有算法 | 寻路细节，请走 `find_path / find_path_to_surface_point` |
| `BehaviorOrchestrator.__getattr__` | 协议层转发；请用 `tick / advance / is_sequence_complete` |
| `BehaviorStateMachine.state` 字段直写 | 写操作请走 `mediator.transition()` |
| `PetShowDirector.start / update / finish` 单独使用 | 应由 `PetController.start_show / tick` 间接驱动 |

---

## 算法复杂度汇总

| 模块 / 函数 | 复杂度 |
| --- | --- |
| `PathFinder.build_surface_graph` | `O(S² · K)`（S=surface 数，K=jump/transform 探测常数） |
| `PathFinder._search` / `GraphPlanner.shortest_path_tree` | Dijkstra `O((V + E) log V)` |
| `PathExecutor.execute_path_plan` | 与步数线性 `O(\|steps\|)` |
| `PathExecutor.compute_jump_velocity_to` | 闭式 `O(1)` |
| `PhysicsEngine.update` | `O(P)`（P=平台数，做 AABB 命中扫描） |
| `BehaviorOrchestrator.tick` / `AnimationPlayer.update` | `O(1)` |
| `_reachable_surface_ids` | DFS `O(V + E)`（局部图上） |

---

## 反射式测试访问入口

`tests/test_pet_controller_climb_reach.py`（730 行）通过 `PetController.__new__` 跳过 `__init__`、直接读写 15+ 私有成员。本包提供的访问入口：

1. **`PetController.__getattr__` 转发** — `{mediator / state_machine / orchestrator / mode_controller}` 四个 mediator 子字段均可通过 `controller.state_machine` 等反射访问。
2. **8 个 Show 转发方法** — `_start_open_wings` 等方法行为为"转发到 `self._show_director._start_open_wings(self)`"。
3. **`_ensure_runtime_layers`** — 为 `__new__` 构造的测试实例补 `mediator / _show_director` 字段。
4. **`HoverAbility / WingAbility / SHOW_HOVER_SECONDS` re-export** — `pet_controller.py` 顶部从 `pet_show_director` 透传；`from desktop_sprite.core.pet_controller import HoverAbility, WingAbility, SHOW_HOVER_SECONDS` 可拿到对应对象。
