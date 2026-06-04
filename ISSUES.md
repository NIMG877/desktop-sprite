# 框架体检 · 逻辑变扭 / 实现过重 / 功能冗余

> 对当前桌宠项目（`d:\PythonProjects\DesktopSprite`）逐模块的批判性分析。  
> 重点不在功能正确性（寻路、物理、状态机、灵痕数据流没有发现真实错误），而在**结构、抽象与可维护性**上的问题。  
> 配套文档：[README.md](README.md) · [PATHFINDING.md](PATHFINDING.md) · [PLAN.md](PLAN.md)

---

## 目录

- [总览：三个主要病灶](#总览三个主要病灶)
- [1. 入口与装配层：上帝 `main()` + 闭包地狱](#1-入口与装配层上帝-main--闭包地狱)
- [2. 角色协议：抽象价值为 0](#2-角色协议抽象价值为-0)
- [3. `PetController`：800 行的"超级控制器"](#3-petcontroller800-行的超级控制器)
- [4. 状态机：三个真理源互相写](#4-状态机三个真理源互相写)
- [5. 寻路系统：能力评估与图构建有重复](#5-寻路系统能力评估与图构建有重复)
- [6. 物理引擎：会改状态的开关 + 死字段](#6-物理引擎会改状态的开关--死字段)
- [7. 行为编排：Phase 与 Show 能力是隐式耦合](#7-行为编排phase-与-show-能力是隐式耦合)
- [8. 资源/属性/灵痕：data class 重，重复实现多](#8-资源属性灵痕data-class-重重复实现多)
- [9. 环境感知：双路径实现 + ID 字符串散落](#9-环境感知双路径实现--id-字符串散落)
- [10. UI 层：自绘与 Fluent 混用 + 无意义反射](#10-ui-层自绘与-fluent-混用--无意义反射)
- [11. 配置层：同一参数出现 3 处](#11-配置层同一参数出现-3-处)
- [12. `runtime_physics` 与基础 `PhysicsConfig`：双物理概念](#12-runtime_physics-与基础-physicsconfig双物理概念)
- [13. 动画 / 渲染](#13-动画--渲染)
- [14. 测试覆盖空白](#14-测试覆盖空白)
- [15. 问题总表](#15-问题总表)
- [16. 推荐的"砍 / 合 / 拆"清单（按 ROI 排序）](#16-推荐的砍--合--拆清单按-roi-排序)
- [17. 真正建议先做的 3 件事](#17-真正建议先做的-3-件事)
- [18. 一些"不是问题，只是被误读"的地方](#18-一些不是问题只是被误读的地方)
- [19. 结论](#19-结论)

---

## 总览：三个主要病灶

| 类型 | 描述 |
| --- | --- |
| **控制器膨胀** | `PetController` 与 `main()` 两个超大入口承担了过多职责，扩展新角色或新行为模式时吃力 |
| **状态分散** | `Pet.state` / `BehaviorStateMachine.state` / `BehaviorOrchestrator.phase` 三处并行的状态字段；物理引擎与控制器并行修状态 |
| **配置/代码耦合** | `load_config` 静默把 `pet` 段字段搬到 `physics` 段；3 处配置可写同一参数；UI 反射调用不存在的 Protocol 方法 |

---

## 1. 入口与装配层：上帝 `main()` + 闭包地狱

[desktop_sprite/app.py:39](desktop_sprite/app.py) 的 `main()` 接近 200 行，单一函数内：

- 加载默认配置 + 用户配置 + 灵痕存档；
- 装配 `QApplication`、`SpriteWindow`、`TargetSelectorOverlay`、`ShowOverlayWindow`、`TrayController`；
- 闭包内联定义 `start_show / close_pet_runtime / quit_app / restart_pet / apply_runtime_config / open_main_window / request_debug_spirit_mark / save_updated_spirit_marks`；
- 闭包之间通过 `nonlocal config, character, window, target_selector, show_overlay, main_window, inventory, spirit_marks` 互相读写。

**问题：**

- `nonlocal` 满天飞导致闭包之间的数据流是隐式的——例如 `request_debug_spirit_mark` 既写 `inventory` 又写 `spirit_marks`，并通过 `nonlocal` 改写外层状态；
- "重启桌宠 / 应用配置 / 退出 / 调试请求" 4 类运行时行为挤在一个函数里，重构或单测都困难；
- 真正承担职责的 `AppController`/`Runtime` 类被压成了闭包工厂。

外层 [app.py](app.py) 是 `from desktop_sprite.app import main` 的纯转发，目前没有任何附加价值，可视为冗余壳。

**解决方案：**

```python
# desktop_sprite/app.py  (重构后)
class AppRuntime:
    def __init__(self, config_path, user_config_path, user_inventory_path, user_spirit_mark_path):
        self.config = load_config(config_path, user_config_path)
        self.character: PetController
        self.window: SpriteWindow
        self.target_selector: TargetSelectorOverlay
        self.show_overlay: ShowOverlayWindow
        self.tray: TrayController
        self.main_window: MainWindow | None = None

    def start(self) -> int:
        ...     # 装配 QApplication 与上述字段

    def restart_pet(self) -> None: ...
    def apply_runtime_config(self) -> None: ...
    def open_main_window(self) -> None: ...
    def quit(self) -> None: ...
    def request_debug_spirit_mark(self) -> str: ...
```

各方法显式 `self.xxx` 读写，闭包之间的隐式数据流全部消失，单元测试可以通过构造假 `QApplication` 或 mock 子模块完成。

---

## 2. 角色协议：抽象价值为 0

[desktop_sprite/core/character.py:51](desktop_sprite/core/character.py#L51) 定义了 `DesktopCharacter` Protocol（`set_own_window_handle / apply_config / tick / start_drag / drag_to / release_drag / poke / sleep / set_target_surface_point / start_show / render_state / debug_state` 等），但：

- 只有一个实现 [PetController](desktop_sprite/core/pet_controller.py)；
- [character_factory.py](desktop_sprite/core/character_factory.py) 永远只 `return PetController(config)`，`character_type` 参数从未被分发；
- UI 层通过 `getattr(character, "paint", None)` 反射调用一个 **Protocol 里不存在的方法**——抽象既没保护调用方，也没被实现遵守。

**问题：** 抽象没有约束力，且 UI 反射绕过抽象。

**解决方案：**

1. 在 `DesktopCharacter` Protocol 中显式声明 `paint(painter, width, height) -> bool` 扩展点；或删反射分支；
2. `character_factory.create_character` 实现真正的 `--character` 分发（即使现在只支持 `pet`，也要写分发骨架）；
3. 准备好下一种角色（`CatController / DragonController`）的最小骨架（`class CatController: implements DesktopCharacter`）作为长期占位。

---

## 3. `PetController`：800 行的"超级控制器"

[desktop_sprite/core/pet_controller.py](desktop_sprite/core/pet_controller.py) 一个文件 800+ 行，单一类型承担：

- 物理 tick 入口（`_update_behavior / _update_show / _apply_motion_events`）；
- 状态机过渡（`_transition`）；
- 行为相位推进（与 `BehaviorOrchestrator` 重复）；
- 寻路执行（与 `PathExecutor` 重复）；
- Show 序列的具体能力（`WingAbility/FlightAbility/HoverAbility` 的 dataclass 定义与生命周期）；
- 随机游走目标生成（`_random_reachable_platform_plan / _random_point_plan / _random_x_on_platform`）；
- 资源影响决策（`_apply_resource_behavior`）；
- 拖拽/投掷记录与速度估算（`_record_drag / _drag_throw_velocity`）；
- 动画相位与 pose 同步。

### 3.1 内部边界被反复突破

`PathExecutor` 持有 `controller` 引用并直接调用：

```python
controller._clear_path_plan()
controller._transition(PetState.CLIMB)
controller._walk_toward_x(target_x)
controller._executor()
controller._is_path_step_present(step)
controller._finish_path_plan(finish_climb=True)
controller.path_plan
```

执行器自己应该不依赖控制器的内部状态，但目前它把控制器当 service locator 用。

### 3.2 Show 能力 dataclass 错位

`WingAbility/FlightAbility/HoverAbility` 定义在 `PetController` 顶部，但本质是动画播放器的子状态——动画相位管理已经被切到 `AnimationPlayer`，但 Show 能力没有同步切走，模型被劈成两半。

### 3.3 散落的 bool 状态

`_landed_on_platform_last_tick / _auto_sleeping / _resource_resting / _seeking_food` 这 4 个布尔分散在多个方法中跟踪"上一帧/资源/行为意图"。`PetResourceInfluence.should_sleep` 等布尔输出"建议"，但 `PetController` 又自己记状态——两个真理源。

### 3.4 `__init__` 与 `_ensure_runtime_layers` 的兜底

```python
if not hasattr(self, "mode_controller"):
    self.mode_controller = ModeController(PetMode.IDLE)
```

这种 lazy 初始化表明构造时序不清晰，是给"老实例迁移"留的补丁。

**解决方案（拆 `PetController`）：**

```python
# desktop_sprite/core/pet/
class PetDecisionController:        # 决策层：行为相位 + 状态机过渡
    def tick(self, dt, snapshot, pet): ...
    def pick_next_idle_goal(self, support, stats): ...
    def should_auto_sleep(self, resources): ...

class PetPathDriver:                # 路径执行调度
    def __init__(self, path_executor, controller_facade): ...
    def execute_plan(self, plan): ...
    def clear(self): ...

class PetShowDirector:              # Show 序列
    def __init__(self): ...
    def start_show(self, pet, snapshot): ...
    def update(self, dt, snapshot, pet) -> bool: ...

class PetResourceSystem:            # 属性 + 资源 + 影响
    def __init__(self, sheet, stats): ...
    def tick(self, state, dt): ...
    def influence(self) -> PetResourceInfluence: ...

class PetController(DesktopCharacter):   # 纯装配
    def __init__(self, config):
        self.decision = PetDecisionController(...)
        self.path_driver = PetPathDriver(...)
        self.show_director = PetShowDirector(...)
        self.resources = PetResourceSystem(...)
    def tick(self, dt): self.decision.tick(dt, ...)
```

`PathExecutor` 通过构造期注入的 `controller_facade`（公开方法的小接口）调用，不再回写控制器内部状态。

---

## 4. 状态机：三个真理源互相写

整个系统对"桌宠当前在做什么"有 **3 套并行的状态字段**：

- `Pet.state`（[models/state.py:36](desktop_sprite/models/state.py)）—— 真实状态枚举值；
- `BehaviorStateMachine.state`（[core/behavior_state_machine.py:22](desktop_sprite/core/behavior_state_machine.py)）—— 状态机内部；
- `BehaviorOrchestrator.phase.name`（[core/behavior_orchestrator.py:38](desktop_sprite/core/behavior_orchestrator.py)）—— 行为相位。

且三者在 [pet_controller.py:758](desktop_sprite/core/pet_controller.py#L758) `_transition` 中被串行手写同步：

```python
self.state_machine.state = self.pet.state
if self.state_machine.transition(state):
    self.pet.state = state
    self.pet.state_time = 0.0
```

**问题：**

- 状态机既被当作"过滤器"又被当作"存储器"——但实际"合法转换表"只有 `ALLOWED_TRANSITIONS` 在用，`state` 字段基本被复制粘贴；
- `transition` 没有任何副作用（不会自动重置 `state_time`），所以"重置 state_time"的责任外泄给调用方；
- 状态机的存在价值已经被三处显式赋值稀释。

**解决方案：**

1. 删 `BehaviorStateMachine.state` 实例字段，只保留 `ALLOWED_TRANSITIONS` 表与 `can_transition` 查询方法；
2. `Pet.state` 作为唯一真理源；
3. `BehaviorOrchestrator.phase` 仅承担"高层进度提示"角色，不参与 dispatch（见 §7）；
4. 状态变更通过单一函数 `controller.change_state(new_state)` 集中处理，自动重置 `state_time`、发信号给动画播放器、通知资源系统。

```python
# desktop_sprite/core/state_change.py
class StateChange:
    @staticmethod
    def apply(pet: Pet, new_state: PetState, allowed: dict[PetState, set[PetState]]) -> bool:
        if new_state == pet.state:
            return True
        if new_state not in allowed.get(pet.state, set()):
            return False
        pet.state = new_state
        pet.state_time = 0.0
        return True
```

---

## 5. 寻路系统：能力评估与图构建有重复

[core/pathfinding.py](desktop_sprite/core/pathfinding.py) 的 `PathFinder` 自带 `_jump_reachable / _can_move_between_horizontals / _can_fall_between_horizontals / _horizontal_gap` 等判定方法。同时 [core/reachability_policy.py](desktop_sprite/core/reachability_policy.py) 又定义了几乎同名/同义的 `can_jump_between / can_walk_transfer / can_drop / max_jump_height / max_jump_distance`——**两边是平行的能力评估实现，policy 没人用**。

### 5.1 `build_surface_graph` 单方法 100+ 行

`build_surface_graph` 单方法 100+ 行，五种建边规则（FALL/HORIZONTAL_MOVE/HORIZONTAL_JUMP/VERTICAL_JUMP/TRANSFORM）混在一起，函数级别就违反了单一职责。

### 5.2 `PathStep` 字段命名混乱

`PathStep` 字段命名混乱：
- `target_t`（行走的最终位置参数）
- `land_t`（跳跃/落地的参数）
- `approach_point`（出发点）
- `land_point`（落点）

4 个字段都看一遍代码才知道分别指什么。

### 5.3 `PathStep` 合并是图生成后做的

`_merge_consecutive_same_surface_move_steps` 是图生成后对结果做"剪枝"——但完全可以在建图阶段避免生成这种多跳节点。

### 5.4 `PlatformTopology` 工具类无人用

[models/platform_topology.py](desktop_sprite/models/platform_topology.py) 提供 `window_top_id / window_left_id / window_right_id`，但 `PathFinder` 自己用 f-string 拼 `window:{hwnd}:top`，**`PlatformTopology` 工具类只有 `PlatformMapper` 在用**——命名约定被破坏。

**解决方案：**

1. **删 `ReachabilityPolicy`**，所有可达性判定统一在 `PathFinder._reaches_*` 内部；`max_jump_height / max_jump_distance` 用 `@staticmethod` 暴露；
2. **拆 `build_surface_graph`** 为多个 builder：

   ```python
   class SurfaceGraphBuilder:
       def __init__(self, pet, snapshot, physics): ...
       def build(self) -> SurfaceGraph: ...    # 主流程
       def _add_fall_edges(self): ...
       def _add_transform_edges(self): ...
       def _add_horizontal_jump_edges(self): ...
       def _add_vertical_jump_edges(self): ...
       def _add_move_edges(self): ...
   ```

3. **`PathStep` 字段重命名**：`target_t` ↔ `land_t` 二选一；`approach_point` ↔ `land_point` 拆为 `start_xy / end_xy`；
4. **统一 ID 拼写**：`PathFinder` 内部全部改用 `PlatformTopology.window_top_id(...)`；
5. **建图阶段直接合并同表面内 MOVE 节点**——避免 `_merge_consecutive_same_surface_move_steps` 后处理。

---

## 6. 物理引擎：会改状态的开关 + 死字段

[core/physics_engine.py](desktop_sprite/core/physics_engine.py) 的设计变扭体现在两点：

### 6.1 `apply_state_transitions: bool` 是死开关

构造时 `PetController` 传 `False`（[pet_controller.py:93](desktop_sprite/core/pet_controller.py#L93)），但代码里到处是 `if self.apply_state_transitions: pet.state = ...`。`True` 路径根本没人走，是为"老调用方"留的兼容位。

### 6.2 `MotionEvents` 字段大多被忽略

```python
@dataclass(slots=True)
class MotionEvents:
    landed_on: str | None = None
    support_lost: bool = False
    climb_completed: bool = False       # 无人读取
    clamped_to_ground: bool = False     # 无人读取
    clamped_to_screen: bool = False     # 无人读取
```

`PetController._apply_motion_events` 只消费了 `support_lost` 与 `landed_on` 两个字段（[pet_controller.py:766](desktop_sprite/core/pet_controller.py#L766)），其余都是死字段。

### 6.3 物理引擎和控制器两条并行的"修改状态"路径

- 物理引擎如果 `apply_state_transitions=True` 会把 `pet.state = FALL/IDLE`；
- `PetController.tick` 走的是 `state_machine.transition`；

两条路并存，状态修改语义被切成两半。

**解决方案：**

1. **删 `apply_state_transitions` 开关**：`PhysicsEngine` 不再修改 `Pet.state`；
2. **删 `MotionEvents` 的死字段**：只保留 `landed_on` / `support_lost`，其余并入 `pet.state` 上下文；
3. 所有状态变更必须经控制器 → state_check → `Pet.state` 单一路径。

---

## 7. 行为编排：Phase 与 Show 能力是隐式耦合

[core/behavior_orchestrator.py](desktop_sprite/core/behavior_orchestrator.py) 同时承担"普通相位（IDLE_WAIT/PATH_*）"和 "Show 序列（SHOW_*）"：

- `phase_duration()` 永远返回 `None`，意味着普通 phase 没有"自动推进"；
- Show 序列的推进依赖 `PetController._update_show` 主动调 `advance_sequence`，ability 完成与 phase 推进是**两个独立信号**，靠"先看 ability_done，再 advance_sequence"两步拼出；
- `SHOW_OPEN_WINGS` 这种 phase 名既被 orchestrator 持有（用于 phase 显示），又被 `_start_show_phase_ability` 当作字典 key（用于能力选择）—— Phase 的语义从"进度提示"变成了"能力 dispatch key"，两种职责耦合。

`pet_mode.py` 的 `ModeController.is_show()` + `PetController._is_show_mode()` 又是两层判断入口。

**解决方案：**

1. **拆 `BehaviorOrchestrator`** 为两个角色：
   - `BehaviorPhaseTracker`：仅跟踪 IDLE_WAIT/PATH_* 等高层相位（无 dispatch 责任）；
   - `ShowSequenceDirector`：管理 SHOW_* 序列，自身持有 ability 推进逻辑，不再依赖 phase 名字。
2. **删 `BehaviorOrchestrator.phase_duration`**——返回 `None` 是历史包袱。
3. **Show 阶段不暴露 phase name 给 dispatch**——dispatch key 改为 enum（`ShowPhase.OPEN_WINGS / FLY / ...`），`ShowSequenceDirector` 内部映射。

```python
# desktop_sprite/core/show_director.py
class ShowPhase(StrEnum):
    OPEN_WINGS = "open_wings"
    FLY = "fly"
    HOVER = "hover"
    TITLE = "title"
    LAND = "land"
    CLOSE_WINGS = "close_wings"

class ShowSequenceDirector:
    def __init__(self): self._phase: ShowPhase | None = None
    def start(self, context: ShowContext) -> None: ...
    def tick(self, dt, pet, stats) -> bool:    # True 表示完成
        handler = self._HANDLERS[self._phase]
        done = handler(pet, dt, stats)
        if done: self._advance()
        return self._phase is None
```

---

## 8. 资源/属性/灵痕：data class 重，重复实现多

### 8.1 属性层

- **`PetAttributeSheet.with_modifiers` 的 modifier 聚合写了三遍**：

  ```python
  grouped.get(value.definition.id, (0.0, 0.0))[0]   # 第一次
  grouped.get(value.definition.id, (0.0, 0.0))[1]   # 第二次
  ```

  本可一次解构，少两次 dict 查找。

  **解法：**

  ```python
  for value in self.values:
      flat, percent = grouped.get(value.definition.id, (0.0, 0.0))
      values.append(replace(value, flat_bonus=flat, percent_bonus=percent))
  ```

- **`PetEffectiveStats.from_sheet`** 调 `_attribute_total / _attribute_base / _attribute_ratio` 三个 helper，每个都套了 `try/except KeyError`——但 sheet 是从定义表生成的，理论不会缺 key，防御代码是噪音。

  **解法：** 删 try/except；定义一个内部 `_safe` 包装仅用于外部输入（如调试热改），不影响主路径。

- **`PetResourceInfluence` 一次输出 6 个布尔**，`should_sleep / should_wake / should_rest / should_stop_rest / should_seek_food / should_stop_seek_food` 调用方（`_apply_resource_behavior`）必须自己持有 `_auto_sleeping / _resource_resting / _seeking_food` 3 个状态去推边沿——Influence 是个纯函数，但被当成"建议型状态机"用了。

  **解法：** 把这些布尔 + 状态机搬到 `PetResourceSystem` 内部，外部只调 `resource.update(pet, dt)` 与 `resource.is_auto_sleeping / is_resting / is_seeking_food`。

### 8.2 灵痕层

- **`SpiritMarkInventory.equip` 一行公式**：

  ```python
  replace(other, equipped=(other.entry_id == entry_id or (other.equipped and other.slot_id != mark.slot_id)))
  ```

  读三遍才能理解"目标槽位先清空再赋给当前 mark"——明显可拆成两步。

  **解法：**

  ```python
  def equip(self, entry_id):
      mark = self._require_mark(entry_id)
      marks = tuple(
          replace(m, equipped=False)
          if m.slot_id == mark.slot_id
          else m
          for m in self.marks
      )
      marks = tuple(
          replace(m, equipped=True) if m.entry_id == entry_id else m
          for m in marks
      )
      return replace(self, marks=marks)
  ```

- **`SpiritMarkInventory.enhance` 的 `growth = 1 + (1 if rng.random() < 0.25 + mark.rarity * 0.03 else 0)`** 概率不直观，缺注释。

  **解法：** 抽常量 `_ENHANCE_DOUBLE_CHANCE_BASE = 0.25` / `_ENHANCE_DOUBLE_CHANCE_RARITY = 0.03`，加注释说明"稀有度每 +1，double 概率 +3%"。

- **`SpiritMarkService.grant_spirit_mark` 一次调用 5+ 次 IO**：

  1. `load_inventory` 读目录+存档（IO 1）
  2. `load_spirit_mark_inventory` 读灵痕（IO 2）
  3. `append_inventory_entry` 读 inventory + 改 + 写（IO 3+4）
  4. `save_spirit_mark_inventory` 写灵痕（IO 5）
  5. `load_inventory` 再读一次构造 `inventory_snapshot`（IO 6）

  **解法：**

  ```python
  def grant_spirit_mark(request, items_path, inventory_path, spirit_mark_path):
      # 一次性加载
      current_snapshot = load_inventory(items_path, inventory_path, spirit_mark_path)
      current_spirit = load_spirit_mark_inventory(spirit_mark_path)
      mark = generate_spirit_mark(request)
      # 内存操作
      new_entries = current_snapshot.entries + (InventoryEntry(mark.entry_id, item_id),)
      new_spirit = SpiritMarkInventory((*current_spirit.marks, mark), current_spirit.materials)
      new_snapshot = replace(current_snapshot, entries=new_entries)
      # 一次性写
      save_inventory(inventory_path, new_snapshot)
      save_spirit_mark_inventory(spirit_mark_path, new_spirit)
      return SpiritMarkGrantResult(mark, new_snapshot, new_spirit)
  ```

- **`SpiritMarkMaterials` 完整定义但 UI 完全不消费**——`SpiritMarkInventory.enhance` 也不消耗它，是"留给以后"的占位字段。

  **解法：** 保留但显式标记"UI 暂未启用"；在 [growth_widget.py](desktop_sprite/ui/growth_widget.py) 加"材料不足"提示（即使功能未完整，UI 占位先到位）。

- **灵痕 `entry_id` 容易冲突**：`f"sm-{stamp}-{randrange(1000, 10000)}"` 与 inventory 的 `entry_id` 命名约定撞车，存档后没有冲突检测。

  **解法：** `append_inventory_entry` 写前先查重（已部分实现），灵痕生成后做一次双层冲突检测。

---

## 9. 环境感知：双路径实现 + ID 字符串散落

- **[screen_sensor.py](desktop_sprite/environment/screen_sensor.py) 提供 Qt 优先 + Win32 兜底**。但 `ScreenSensor` 只在 `DesktopEnvironment` 构造时被 new 一次，此时 QApplication 必然存在——Win32 分支永远不执行，是死代码。

  **解法：** 保留作为单元测试入口（不构造 QApplication 也能用），但加注释说明用途。

- **[window_sensor.py](desktop_sprite/environment/window_sensor.py) 排除窗口的类名是硬编码**（`Progman/WorkerW/Shell_TrayWnd/...`），无配置化。

  **解法：** `IGNORED_CLASSES` 移到 `config/window_filter.json`，可热改：

  ```json
  {
    "ignored_classes": ["Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Button", "Windows.UI.Core.CoreWindow"],
    "min_window_size": [120, 80]
  }
  ```

- **`EnvironmentSnapshot.foreground_window` 与 `WindowSensor.get_foreground_window()` 两个 API 入口**返回同样的东西。

  **解法：** 保留 `WindowSensor` 单例入口，Snapshot 只做数据；调用方统一用 `desktop_environment.window_sensor.get_foreground_window()`。

- **平台 ID 字符串 `window:{hwnd}:top/left/right`** 在 `PlatformMapper`（通过 `PlatformTopology.window_top_id`）和 `PathFinder`（直接 f-string）两处拼写。

  **解法：** 强制所有调用走 `PlatformTopology.window_top_id(hwnd)`，PathFinder 内部全替换。

---

## 10. UI 层：自绘与 Fluent 混用 + 无意义反射

- **`MainWindow._page / _hero / _action_card` 全部自渲染**（[main_window.py:194](desktop_sprite/ui/main_window.py#L194)），但承载它的 `FluentWindow` 又提供主题与导航——风格不统一。

  **解法：** 全部改用 `qfluentwidgets` 的 `CardWidget / SimpleExpandGroupSettingCard / SettingCard` 等；自渲染仅保留调试覆盖层（其性质决定必须自绘）。

- **`InventoryWidget` 90% 都是自绘卡片背景**，但顶部用了 qfluentwidgets 的 `SegmentedWidget/SmoothScrollArea`——拼装感强。

  **解法：** 卡片用 `CardWidget` 承载，背景由主题决定，删除自绘 `_draw_card`。

- **`SpriteWindow.paintEvent` 反射调用**：

  ```python
  paint_fn = getattr(self.character, "paint", None)
  if callable(paint_fn) and paint_fn(painter, self.width(), self.height()):
      return
  ```

  `DesktopCharacter` Protocol 根本没有 `paint` 方法，`getattr(..., default=None)` 永远拿到 `None`，所以 `if` 永远 False——反射调一个不存在的扩展点。

  **解法：** 删 `getattr` 反射，删 `if` 短路；或者把 `paint` 加进 Protocol（且给一个 `PetController.paint` 默认实现）。

- **`ShowOverlayWindow` 自己有 33ms 定时器**（[show_overlay.py:38](desktop_sprite/ui/show_overlay.py#L38)），而桌宠主窗口本身每帧 `update()`——`ShowOverlayWindow` 完全可以订阅桌宠的 `update` 信号，没必要再起一个 timer。

  **解法：** `ShowOverlayWindow.update` 改为被动：桌宠主窗口在 `paintEvent` 中检测到 `mode == SHOW` 时 `self.show_overlay.update()`。

- **`MainWindow.setTheme(Theme.DARK)` 在 `__init__` 顶部硬编码**（[main_window.py:55](desktop_sprite/ui/main_window.py#L55)）。

  **解法：** 主题作为 `RuntimeConfig.theme` 字段，可热切换。

- **`ConfigEditorWidget` 保存/IO 逻辑和 `MainWindow._save_window_geometry` 各自实现一份"读 state → merge → 写"**。

  **解法：** 抽 `JsonStateFile` 工具类，统一管理 `user.json` / `ui_state.json` 的读写。

- **三个占位页（`全自动/辅助操控/通知`）已经是真实注册但只有占位文字**（[main_window.py:173](desktop_sprite/ui/main_window.py#L173)）。

  **解法：** 标题加灰 + 副标题写"即将推出"；不放在导航 TOP 位置，挪到 BOTTOM 或独立折叠组。

- **`SpriteWindow._tick` 走 `try/except KeyboardInterrupt`** 捕获后调用 `QApplication.quit()`——在 QTimer 槽函数里抛 KeyboardInterrupt 的可能性几乎为 0。

  **解法：** 删 try/except；`SIGINT` 已经通过 `signal.signal` 单独处理。

---

## 11. 配置层：同一参数出现 3 处

[config/default.json](config/default.json) 里有 `physics` 段但**没有** `walk_speed/climb_speed/jump_*`——`load_config` 通过这段代码补全：

```python
# desktop_sprite/utils/config.py:141
for motion_key in ("walk_speed", "climb_speed", "jump_speed_x", "jump_speed_y"):
    if motion_key in pet_data:
        physics_data[motion_key] = pet_data.pop(motion_key)
```

也就是说 `pet.walk_speed`（在 `pet.json` 和 `default.json` 的 `pet` 段都有）会被**静默搬到 `physics` 段**——但用户改 `pet.walk_speed` 后想确认它"是否生效"必须看 `physics` 段。

三处配置位置：

- `default.json:pet.walk_speed`（会被搬走）
- `default.json:physics.walk_speed`（如果存在就覆盖）
- `characters/pet.json:pet.walk_speed`（最终胜出者）

没有注释说明，用户改其中一个看另一个没变会迷惑。

### 11.1 其它配置层问题

- **`BehaviorConfig.sleep_after_seconds` 字段被定义、配置里写了**，但**没有任何代码消费**。
- **`pet.json` 里也写了 `walk_speed / climb_speed / jump_speed_x / jump_speed_y`**，但 `default.json:physics` 也有——三层覆盖关系对用户不透明。
- **`user.json` 与 `default.json` 的合并是浅 dict merge**，遇到嵌套 dict 会递归，但"用户只覆盖 physics 的一部分字段、其余用 default"这种"partial override"的实际行为在 `ConfigEditorWidget` 里没显式提示。
- **字段 `interaction.target_search_down_distance / target_search_up_distance`** 在 `load_config` 中通过 `setdefault` 补默认值（[config.py:133](desktop_sprite/utils/config.py#L133)），但 `InteractionConfig` dataclass 又**没有**默认值——意味着如果 config 文件忘写这两个键，dataclass 构造会缺字段。这种"setdefault 兜底 + 必填 dataclass"是隐式契约。

**解决方案：**

1. **把 `walk_speed/climb_speed/jump_*` 完全从 `physics` 段删掉**，只保留在 `pet` 段；`load_config` 不再做静默搬移；
2. **显式分层文档化**：
   - `config/default.json` —— 程序启动默认值
   - `config/characters/{name}.json` —— 角色基础档案（覆盖 default 中同字段）
   - `config/user/user.json` —— 用户修改（最高优先级）
3. **删 `BehaviorConfig.sleep_after_seconds`**（除非准备实现睡眠自动触发）；
4. **`InteractionConfig` 字段加默认值**（或用 `**kwargs` 模式 dataclass 接收），删 `setdefault` 兜底。

---

## 12. `runtime_physics` 与基础 `PhysicsConfig`：双物理概念

- `AppConfig.physics` 是基础物理值（来自配置文件）；
- `PetController.runtime_physics()` 用 `replace_physics_movement` 在 `PhysicsEngine` 调用前**临时把 walk/climb/jump 速度按资源影响打折**；
- `PhysicsEngine.config` 字段是公开可写，每帧 `tick` 都被 `self.physics.config = self.runtime_physics()` 重设（[pet_controller.py:159](desktop_sprite/core/pet_controller.py#L159)）；
- 但 `physics.update` 内部又使用 `self.config`——结果是"基础值在 AppConfig、运行时值在 PhysicsEngine 实例、每帧重建"，三个地方有"物理速度"概念。

`RuntimeConfig` 本身只表示"启动配置"，但 `runtime_physics` 名字又暗示"运行时物理"——重名。

**解决方案：**

1. 把 `PhysicsEngine.config` 改为 immutable（构造期注入，运行期不修改）；
2. 资源影响下发的物理参数通过 `PhysicsEngine.apply_motion_modifier(modifier)` 显式下发，引擎内部按 modifier 临时调整；
3. 删 `runtime_physics()` / `replace_physics_movement` 工具函数。

```python
# 伪代码
class MotionModifier:
    walk_factor: float
    climb_factor: float
    jump_factor: float

class PhysicsEngine:
    def __init__(self, base_config): self._base = base_config
    def apply_modifier(self, mod: MotionModifier): self._mod = mod
    def _effective_walk_speed(self) -> float:
        return self._base.walk_speed * self._mod.walk_factor
```

---

## 13. 动画 / 渲染

- [animation_player.py](desktop_sprite/core/animation_player.py) 提供了 `phase / previous_phase / blend_alpha`，但 `SpriteWindow.paintEvent` 没用 `previous_phase` 做插值（[sprite_window.py:101](desktop_sprite/ui/sprite_window.py#L101)）——只有 `blend_alpha` 用了，前态直接被重新调用 `build` 然后 `blend`，多了一倍 pose 计算。
- **`PoseBuilder` 实例在 [sprite_window.py:46](desktop_sprite/ui/sprite_window.py#L46) 每帧根据 `effective_stats().wing_open_seconds` 重新 new 一次**——`pose_builder.wing_open_seconds = ...` 直接赋值字段，因为 `PoseBuilder` 是 mutable 的 dataclass（不是 frozen），破坏了"有状态对象"的封装。
- **`pet_renderer._draw_feathered_wing` 在 `opacity <= 0` 时仍然绘制基线羽翼**：

  ```python
  self._draw_primary_feathers(...)
  self._draw_secondary_feathers(...)
  ```

  `_draw_wings` 顶部的 `if pose.wings is None or pose.wings.opacity <= 0: return` 只挡了 wing 整体，但没有给"翅膀还在但正在收起"的状态做特殊化。

**解决方案：**

1. 删 `SpriteWindow` 中重复 `build` 前态再 `blend` 的逻辑，直接用 `animation_player.blend_alpha`；
2. `PoseBuilder` 改成 frozen + 显式 `with_phase_config(wing_open, wing_close)` 工厂方法；
3. `_draw_feathered_wing` 顶部判断 `if openness < 0.1: return`（避免淡出时画残影）。

---

## 14. 测试覆盖空白

`tests/` 21 个文件覆盖几何/物理/寻路/属性/灵痕/UI 部件，但：

- 没有 `test_app` 之外的应用层集成测试——`main()` 的闭包地狱几乎不可单测；
- 没有针对 `PetController` 整段的端到端测试（`_update_behavior / _execute_path_plan` 的多步交互）；
- `test_pet_controller_climb_reach` 只是"能否抓到墙"，没有覆盖 Show 模式全流程；
- `ShowOverlayWindow` 和 `DebugOverlayWindow` 两个全屏 widget 没有专门的 widget 测试。

**解决方案：**

`test_app` 已经存在但只是简单启动测试。补充以下测试：

- `test_app_runtime.py` —— 拆 `AppRuntime` 后用 mock 子模块测试 `restart_pet / apply_config / quit`；
- `test_pet_controller_e2e.py` —— 整段 tick + 行为决策 + 路径执行 + 资源 tick；
- `test_show_full_flow.py` —— `start_show` → 序列推进 → `_finish_show` 全流程；
- `test_show_overlay_widget.py` / `test_debug_overlay_widget.py` —— 用 `QApplication` 启动 widget 并断言绘制调用。

---

## 15. 问题总表

| 类型 | 具体问题 | 严重度 |
| --- | --- | --- |
| **逻辑变扭** | `PetController` 既是控制器又是动画/能力/行为编排的宿主 | 高 |
| | 三处并行的"状态"字段（Pet.state / state_machine.state / orchestrator.phase） | 高 |
| | 物理引擎 `apply_state_transitions` 死开关 + 控制器走状态机 两条改状态路径 | 中 |
| | `ModeController.is_show()` 与 `PetController._is_show_mode()` 双层判断 | 中 |
| | `BehaviorOrchestrator` 的 phase 名同时承担"展示 + dispatch key"两种职责 | 中 |
| | 寻路"能力评估"在 `ReachabilityPolicy` 与 `PathFinder` 中重复实现 | 中 |
| | `PhysicsEngine` 与 `PetController` 两条并行的状态修改路径 | 中 |
| | `SpiritMarkInventory.equip` 一行公式难读 | 中 |
| | `with_modifiers` 一次 dict 查找 2 次 | 低 |
| **实现过重** | `main()` 单函数 200 行 + 闭包互引 nonlocal 满天飞 | 高 |
| | `PetController` 800+ 行 6 大职责合一 | 高 |
| | `MotionEvents` 5 个字段只有 2 个被消费 | 中 |
| | `build_surface_graph` 单方法 100+ 行 | 中 |
| | `with_modifiers` 重复 dict 查找；`enhance` 概率公式不直观 | 低 |
| | 防御性 `try/except KeyError` 在属性 helper 中堆叠 | 低 |
| | `SpriteWindow` 反射调用不存在的 `character.paint` | 低 |
| | `ShowOverlayWindow` 与桌宠主窗口维护两套定时器 | 低 |
| | `app.py` 顶层纯转发 | 低 |
| | `SpriteWindow._tick` 冗余 `try/except KeyboardInterrupt` | 低 |
| **功能冗余** | `WindowSensor.get_foreground_window` 与 `EnvironmentSnapshot.foreground_window` | 中 |
| | `PlatformTopology` 只有 `PlatformMapper` 真正在用，`PathFinder` 直接 f-string | 中 |
| | `BehaviorConfig.sleep_after_seconds` 字段定义但零调用 | 中 |
| | `SpiritMarkMaterials` 完整定义但 UI 与 enhance 都不消费 | 中 |
| | `interaction.target_*` 走 `setdefault` 兜底，缺字段会 dataclass 报错 | 低 |
| | `MainWindow.setTheme(Theme.DARK)` 硬编码主题 | 低 |
| | 灵痕目录中 `test.sanctum_radiance.*` 与正式灵痕平级 | 低 |
| | 三层配置（default/pet/user）合并路径与覆盖优先级对用户不透明 | 中 |
| | `PoserBuilder` 每帧 mutable 字段直接赋值 | 低 |

---

## 16. 推荐的"砍 / 合 / 拆"清单（按 ROI 排序）

| 优先级 | 改动 | 说明 |
| --- | --- | --- |
| **P0** | 拆 `main()` 为 `AppRuntime` 类 | 把 200 行闭包拆成显式字段 + 方法；`restart_pet / apply_config / quit / open_main_window` 都变成类方法，单元可注入 fake window |
| **P0** | 拆 `PetController` | 抽 `PetDecisionController`（决策）+ `PetPathDriver`（路径执行调度）+ `PetShowDirector`（Show 序列）+ `PetResourceSystem`（属性 + 资源 + 影响），控制器只做装配；`PathExecutor` 不再回写控制器内部状态 |
| **P0** | 统一"状态"真理源 | 删 `BehaviorStateMachine.state`（只留 `ALLOWED_TRANSITIONS` 表），`transition` 改为 pure check；`Pet.state` 是唯一真理；`BehaviorOrchestrator.phase` 只作为"高层进度提示"使用，不参与 dispatch |
| **P0** | 删 `apply_state_transitions` 死开关 | `PhysicsEngine` 不再修改 `Pet.state`，所有状态变更必须经控制器 → state_check → `Pet.state` |
| **P0** | 删 `MotionEvents` 的死字段 | 只保留 `landed_on` / `support_lost`，其余并入 `pet.state` 上下文 |
| **P1** | 合并 `PathFinder` 与 `ReachabilityPolicy` | 删 `ReachabilityPolicy`，所有可达性判定统一在 `PathFinder._reaches_*` 内部；`max_jump_height / max_jump_distance` 用 `@staticmethod` 暴露 |
| **P1** | 删 `PathStep` 重复字段或改命名 | `target_t` ↔ `land_t` 二选一；`approach_point` ↔ `land_point` 拆为 `start_xy / end_xy`，去掉同义别名 |
| **P1** | Show 序列能力迁出 `PetController` | 把 `WingAbility/FlightAbility/HoverAbility` 搬进 `PetShowDirector`，`BehaviorOrchestrator` 只持有进度；`advance_sequence` 与 `ability_done` 的关系改成 `ShowDirector` 内部 state |
| **P1** | 配置三层关系文档化 + 单一真源 | 把 `walk_speed/climb_speed/jump_*` 完全从 `physics` 段删掉，只保留在 `pet` 段；`load_config` 不再做静默搬移；UI 提示"角色档案 > user.json > default.json" |
| **P1** | 删 `BehaviorConfig.sleep_after_seconds` 与 `SpiritMarkMaterials` 等未消费字段 | 或在 UI 显式标记"暂未启用"，避免读者困惑 |
| **P2** | `MainWindow.setTheme(Theme.DARK)` 走配置 | 主题作为 `RuntimeConfig.theme` 字段，可热切换 |
| **P2** | `SpriteWindow` 反射调用删掉 | 直接 `self.pet_renderer.draw_pose(...)`，不要再 `getattr` 调不存在的 `paint` |
| **P2** | `ShowOverlayWindow` 删自己的 timer | 改成 `sprite_window.update` 信号 → 槽，或直接在 `SpriteWindow.paintEvent` 里调它的 `update()` |
| **P2** | `WindowSensor` 排除规则配置化 | `IGNORED_CLASSES` 移到 `config/window_filter.json`，可热改 |
| **P2** | `EnvironmentSnapshot.foreground_window` 与 `WindowSensor.get_foreground_window` 二选一 | 推荐保留 `WindowSensor` 单例入口，Snapshot 只做数据 |
| **P2** | `PlatformTopology` 强制所有 ID 拼写 | 删 `PathFinder` 内部的 f-string，统用 `PlatformTopology.window_top_id` |
| **P2** | `SpiritMarkService.grant_spirit_mark` 减 IO | 5 次 IO 压成 2 次（inventory 用内存对象，结束时统一写一次） |
| **P2** | `SpiritMarkInventory.equip` 拆两步 | 第一步"同槽位移除 equipped"，第二步"目标 mark 置 equipped"，可读性 ↑ |
| **P2** | `PetAttributeSheet.with_modifiers` 解构一次 | `flat, percent = grouped.get(...)` 一次查表 |
| **P2** | `PetEffectiveStats` 删 try/except 兜底 | sheet 由定义表生成，删防御代码 |
| **P2** | `PoseBuilder` 改成 frozen + 显式 `with_phase_config()` | 避免 `sprite_window.paintEvent` 里 `pose_builder.wing_open_seconds = ...` 这种破封装赋值 |
| **P3** | `ScreenSensor` 删 Win32 兜底分支 | 程序已运行在 QApplication 里，Qt 路径必然成功 |
| **P3** | `app.py` 删掉或改成 `desktop_sprite.app.main()` 的别名 | 现在无附加价值 |
| **P3** | `items.json` 把 `test.*` 分类移到 `dev/` 子目录 | 避免污染正式目录；或加 `category.dev_only = true` 标记 |
| **P3** | 灵痕 `entry_id` 加冲突检测 | `append_inventory_entry` 在写前先 `if entry.entry_id in existing` 报错 |
| **P3** | `DesktopCharacter.paint` 要么补上 Protocol 方法要么删反射 | 留反射意味着对实现方没有约束，删掉则更诚实 |
| **P3** | `MainWindow._add_interfaces` 占位页标灰 | 占位页当前外观与正式页一样，用户以为有功能 |
| **P3** | `SpriteWindow._tick` 删 `try/except KeyboardInterrupt` | QTimer 槽内不会自然抛 KeyboardInterrupt，且与 `signal.signal(SIGINT, ...)` 重复 |

---

## 17. 真正建议先做的 3 件事

如果只挑三件最高 ROI 的事，我会选：

1. **拆 `PetController` + 重构 `main()`**——把"上帝类 + 闭包 main"这两个最阻碍后续扩展的部分同时处理。完成后单测覆盖率可以上一个台阶。
2. **统一状态真理源 + 删物理死开关**——这两处去掉之后，状态机调试难度会显著下降，调试覆盖层的 `behavior: idle` 文本再也不会和 `pet.state` 错位。
3. **配置三层文档化 + 删静默搬移**——纯文档 + 字段清理，不改逻辑，但用户改配置时不再有"改了不生效"的怀疑。

剩下的（合并 policy、删反射、统一 ID 拼写、减 IO）都是局部清理，可以在那 3 件完成之后按模块逐步推进。

---

## 18. 一些"不是问题，只是被误读"的地方

为了避免矫枉过正，以下几处看起来像问题，但其实是合理设计或暂未启用的占位：

- **`DesktopCharacter` Protocol 即使只有一个实现**也建议保留——只要未来要加 `CatController / DragonController` 就直接派上用场，且 IDE/类型检查能立即受益。问题不在协议本身，而在工厂函数没分派。
- **`SpiritMarkMaterials` 字段不消费**不是冗余，是预留玩法（强化/分解已经写好，UI 还没接）。建议保留并显式标记 "UI 暂未启用"。
- **占位页（`全自动/辅助操控/通知`）已经注册**——这是骨架先行，行为后续；只是 UI 应该明确告诉用户"暂未实现"。
- **`ScreenSensor` 的 Win32 兜底**——虽然 QApplication 启动后永远走 Qt 路径，但保留 Win32 分支让 `ScreenSensor` 在测试中（不构造 QApplication）也能用，有其价值。
- **`Set`/`Dict` 排序稳定性**——`SpiritMarkInventory.equip` 用了一行 set 表达式，乍看难读，但实际语义清晰，重构时只需要加注释而非拆方法。

---

## 19. 结论

整体上，这个项目实现了一个**有真实物理 + 寻路 + 桌面感知 + 灵痕装备**的完整桌宠引擎，可玩性骨架已经具备。问题主要集中在三方面：

1. **"控制器膨胀"**——`PetController` / `main()` 两个超大入口承担了过多职责，扩展新角色或新行为模式时明显吃力；
2. **"状态分散"**——状态字段在 `Pet / state_machine / orchestrator` 三处写，物理引擎与控制器并行修状态，调试时容易错位；
3. **"配置与代码耦合"**——`load_config` 静默把 `pet` 段字段搬到 `physics` 段、3 处配置可写同一参数、UI 反射调用不存在的 Protocol 方法，让"用户改了配置不生效"或"开发者改了字段没生效"都难定位。

按 P0 → P1 → P2 顺序清理后，框架的可维护性和扩展性会上一个台阶，但**功能层面**（寻路正确性、状态机合法性、属性/灵痕数据流）目前没有发现真正错误，主要是结构上的"实现过重"和"逻辑变扭"。

---

### 相关文档

- [README.md](README.md) · 项目总览
- [PATHFINDING.md](PATHFINDING.md) · 寻路系统重构方案
- [PLAN.md](PLAN.md) · 旧版寻路系统方案
- [system_design/](system_design/) · 属性/灵痕/专注/软体模拟等设计文档
