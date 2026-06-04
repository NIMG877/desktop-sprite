# `desktop_sprite.models` — 不可变数据模型

所有 dataclass 均为 `frozen=True, slots=True`（除 `Pet` / `PetRuntimeResources` / `BehaviorPhase` 等运行时可变实体）；状态变更通过 `dataclasses.replace` 返回新对象，便于回退/撤销/差异测试。本包约 1700 行，9 个文件，不持有任何业务逻辑、只提供数据与少量纯函数。

> 与本 README 互补：
> - 行为编排 / 物理 / 寻路（消费本包的数据）见 [../core/README.md](../core/README.md)
> - 环境快照与平台派生（`EnvironmentSnapshot` / `Platform`）见 [../environment/README.md](../environment/README.md)
> - 加载入口（`load_config` 拼装 `AppConfig`）见 [../utils/README.md](../utils/README.md)

---

## 目录

- [文件清单](#文件清单)
- [核心 dataclass 总览](#核心-dataclass-总览)
- [几何原语](#几何原语)
- [桌宠实体与状态机](#桌宠实体与状态机)
- [窗口与平台](#窗口与平台)
- [16 项属性系统](#16-项属性系统)
- [物品 / 背包](#物品--背包)
- [灵痕](#灵痕)
- [灵痕发放服务](#灵痕发放服务)
- [持久化入口与文件映射](#持久化入口与文件映射)
- [跨包依赖图](#跨包依赖图)

---

## 文件清单

| 路径 | 内容定位 |
| --- | --- |
| `__init__.py` | 包级 `__all__`（按需透传主要 dataclass） |
| [`geometry.py`](geometry.py) | `Vec2` / `Rect` |
| [`state.py`](state.py) | `Pet`（可变实体）、`PetState` / `Facing` 枚举 |
| [`window_info.py`](window_info.py) | `WindowInfo` |
| [`platform.py`](platform.py) | `Platform` + `PlatformType` 枚举 |
| [`platform_topology.py`](platform_topology.py) | `PlatformTopology` 静态 ID 工厂 |
| [`pet_attribute.py`](pet_attribute.py) | 16 个属性定义 + `PetAttributeSheet` + `PetEffectiveStats` + `PetResourceInfluence` + `PetRuntimeResources` |
| [`inventory.py`](inventory.py) | 物品目录 + 库存加载 + 灵痕回填 |
| [`spirit_mark.py`](spirit_mark.py) | 灵痕数据 + 套装/槽位常量 + 强化/分解/收藏/属性化 |
| [`spirit_mark_service.py`](spirit_mark_service.py) | 灵痕发放（grant）编排 |

---

## 核心 dataclass 总览

| 路径 | 类型 | frozen | 备注 |
| --- | --- | --- | --- |
| `geometry.Vec2` | dataclass | — | 二维向量 |
| `geometry.Rect` | dataclass | ✓ | 矩形几何 |
| `state.Pet` | dataclass | — | 可变实体（位置/速度/状态/计时器/拖拽轨迹） |
| `window_info.WindowInfo` | dataclass | ✓ | OS 窗口快照 |
| `platform.Platform` | dataclass | ✓ | 可踩踏/可攀爬平台 |
| `pet_attribute.PetAttributeDefinition` | dataclass | ✓ | 单条属性元信息 |
| `pet_attribute.PetAttributeModifier` | dataclass | ✓ | 来自灵痕等源的属性修饰器 |
| `pet_attribute.PetAttributeValue` | dataclass | ✓ | 某条属性的基础值+加值/百分比加成 |
| `pet_attribute.PetAttributeSheet` | dataclass | ✓ | 属性表（基础值+修饰器聚合） |
| `pet_attribute.PetEffectiveStats` | dataclass | ✓ | 物理/行为参数最终值 |
| `pet_attribute.PetResourceInfluence` | dataclass | ✓ | 资源→行为/状态影响因子 |
| `pet_attribute.PetRuntimeResources` | dataclass | — | 可变：体力/精力/饱腹实时数值 |
| `inventory.ItemCategory` | dataclass | ✓ | 物品类目 |
| `inventory.ItemDefinition` | dataclass | ✓ | 物品目录定义 |
| `inventory.InventoryEntry` | dataclass | ✓ | 背包单条记录 |
| `inventory.InventorySnapshot` | dataclass | ✓ | 背包只读快照 |
| `spirit_mark.SpiritMarkSlot` | dataclass | ✓ | 灵痕槽位 |
| `spirit_mark.SpiritMarkSet` | dataclass | ✓ | 灵痕套装 |
| `spirit_mark.SpiritMarkStat` | dataclass | ✓ | 单条主/副词条 |
| `spirit_mark.SpiritMarkGrantRequest` | dataclass | ✓ | 生成灵痕时的请求参数 |
| `spirit_mark.SpiritMark` | dataclass | ✓ | 单条灵痕实例 |
| `spirit_mark.SpiritMarkMaterials` | dataclass | ✓ | 灵痕分解产出的养成材料 |
| `spirit_mark.SpiritMarkInventory` | dataclass | ✓ | 灵痕集合 + 材料池 |
| `spirit_mark_service.SpiritMarkGrantResult` | dataclass | ✓ | 授予服务返回 |

---

## 几何原语

[`geometry.py`](geometry.py)：

```python
@dataclass(slots=True)
class Vec2:
    x: float = 0.0
    y: float = 0.0
    def copy(self) -> "Vec2"

@dataclass(frozen=True, slots=True)
class Rect:
    left: float
    top: float
    right: float
    bottom: float

    @classmethod
    def from_xywh(cls, x, y, w, h) -> "Rect"        # 注意：含 x+w / y+h
    @property width / height
    @property center_x / center_y
    def moved_by(self, dx, dy) -> "Rect"
    def overlaps_x(self, other) -> bool
    def overlaps_y(self, other) -> bool
    def intersects(self, other) -> bool
    def contains_point(self, x, y) -> bool
    def clamp_point(self, x, y) -> tuple[float, float]
    def is_valid(self) -> bool                       # width > 0 && height > 0
```

---

## 桌宠实体与状态机

[`state.py`](state.py)：

### `PetState(StrEnum)`

| 名称 | 字符串值 |
| --- | --- |
| IDLE | `"idle"` |
| WALK | `"walk"` |
| JUMP | `"jump"` |
| CLIMB | `"climb"` |
| FALL | `"fall"` |
| DRAGGED | `"dragged"` |
| SLEEP | `"sleep"` |
| OPEN_WINGS | `"open_wings"` |
| FLY | `"fly"` |
| HOVER | `"hover"` |
| WING_LAND | `"wing_land"` |
| CLOSE_WINGS | `"close_wings"` |

### `Facing(StrEnum)`：`LEFT = "left"`、`RIGHT = "right"`。

### `Pet`（`@dataclass(slots=True)`，**非 frozen**）

| 字段 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `position` | `Vec2` | 必填 | 左上角位置 |
| `velocity` | `Vec2` | 必填 | 当前速度 |
| `width` | `int` | 必填 | 像素宽 |
| `height` | `int` | 必填 | 像素高 |
| `facing` | `Facing` | `RIGHT` | 朝向 |
| `state` | `PetState` | `FALL` | 行为状态机当前态 |
| `support_surface_id` | `str \| None` | `None` | 正在踩着的平台 id |
| `target_surface_id` | `str \| None` | `None` | 寻路目标平台 id |
| `target_window_id` | `int \| None` | `None` | 寻路目标窗口 hwnd |
| `state_time` | `float` | `0.0` | 当前状态已用秒数 |
| `idle_timer` | `float` | `0.0` | 待机累计秒数 |
| `drag_positions` | `list[tuple[float, float, float]]` | `[]` | 拖拽历史 `(x, y, t)` |

属性：`rect`（`Rect.from_xywh`）、`bottom = position.y + height`、`center_x = position.x + width/2`。

> `Pet.state` 的合法写源集中在 `PetStateMediator.transition`（见 [../core/README.md](../core/README.md)）。`Pet.state_time` 在状态切换时由 mediator 重置为 `0.0`。

---

## 窗口与平台

### [`window_info.py`](window_info.py)

```python
@dataclass(frozen=True, slots=True)
class WindowInfo:
    hwnd: int
    title: str
    rect: Rect
    visible: bool
    minimized: bool
    is_foreground: bool
    class_name: str = ""
```

### [`platform.py`](platform.py)

`PlatformType(StrEnum)`：`GROUND / TASKBAR / WINDOW_TOP / WINDOW_LEFT / WINDOW_RIGHT`。

```python
@dataclass(frozen=True, slots=True)
class Platform:
    id: str                                      # 必填（详见 environment README）
    type: PlatformType                           # 必填
    rect: Rect                                   # 必填
    walkable: bool                               # 必填
    climbable: bool                              # 必填
    dynamic: bool = False                        # 任务栏/窗口均为 True
    source_id: int | None = None                 # 窗口类平台为 hwnd
```

属性：`top_y = rect.top`。

### [`platform_topology.py`](platform_topology.py)

```python
class PlatformTopology:
    @staticmethod
    def window_top_id(hwnd: int) -> str          # "window:{hwnd}:top"
    @staticmethod
    def window_left_id(hwnd: int) -> str         # "window:{hwnd}:left"
    @staticmethod
    def window_right_id(hwnd: int) -> str        # "window:{hwnd}:right"
    @staticmethod
    def top_id_for_side_id(side_id: str) -> str
    @staticmethod
    def top_id_for_side(side: Platform) -> str
```

`top_id_for_side_id(side_id)` 用 `split(":")`，仅当 `len(parts) >= 3` 时返回 `f"{parts[0]}:{parts[1]}:top"`，否则原样返回（兼容未来非 `window:` 前缀）。

---

## 16 项属性系统

[`pet_attribute.py`](pet_attribute.py)：

### 类型别名

```python
BonusType = Literal["flat", "percent"]
AttributeValueFormat = Literal["number", "percent"]
AttributeCategory = Literal["basic", "visual", "special"]
```

### `PetAttributeDefinition`（`frozen=True, slots=True`）

| 字段 | 类型 | 默认 |
| --- | --- | --- |
| `id` | `str` | 必填 |
| `name` | `str` | 中文名（"机动"等） |
| `english_name` | `str` | 英文名 |
| `role` | `str` | 一句话作用 |
| `mapped_content` | `str` | 影响哪些运行参数 |
| `initial_source` | `str` | 初始值来源（config 字段名或 `fixed`） |
| `allowed_bonus_types` | `tuple[BonusType, ...]` | 修饰器允许类型 |
| `value_format` | `AttributeValueFormat` | `"number"` |
| `category` | `AttributeCategory` | `"basic"` |

### `PetAttributeModifier`（`frozen=True, slots=True`）

| 字段 | 类型 | 默认 |
| --- | --- | --- |
| `attribute_id` | `str` | 必填 |
| `value` | `float` | 必填 |
| `bonus_type` | `BonusType` | `"flat"` |
| `source_id` | `str` | `""`（如灵痕 `entry_id`） |
| `source_type` | `str` | `"manual"`（`"spirit_mark"` / `"spirit_mark_set"` 等） |

### `PetAttributeValue`（`frozen=True, slots=True`）

| 字段 | 类型 | 默认 |
| --- | --- | --- |
| `definition` | `PetAttributeDefinition` | 必填 |
| `base_value` | `float` | 必填 |
| `flat_bonus` | `float` | `0.0` |
| `percent_bonus` | `float` | `0.0` |

派生属性：

- `percent_bonus_value`：`value_format == "percent"` 时原样返回 `percent_bonus`，否则按 `base_value * percent_bonus / 100` 折算。
- `total_bonus = flat_bonus + percent_bonus_value`。
- `total = base_value + total_bonus`。
- 格式化方法（均按 `value_format` 加 `%` 后缀或不加）：`formatted_total / formatted_base / formatted_flat_bonus / formatted_percent_bonus_value / formatted_total_bonus / formatted_bonus / formatted_formula`。

### `PetAttributeSheet`（`frozen=True, slots=True`）

| 字段 | 类型 | 默认 |
| --- | --- | --- |
| `values` | `tuple[PetAttributeValue, ...]` | 必填（16 条） |
| `modifiers` | `tuple[PetAttributeModifier, ...]` | `()` |

方法：

| 签名 | 行为 |
| --- | --- |
| `from_config(config: AppConfig) -> PetAttributeSheet` | 按 16 个属性 ID 从 `config.physics` / `config.attributes` 取初值，其中 `leap = (\|jump_speed_x\| + \|jump_speed_y\|) / 2` |
| `value_for(attribute_id) -> PetAttributeValue` | 找不到抛 `KeyError` |
| `with_modifiers(modifiers) -> PetAttributeSheet` | 聚合同 ID 修饰器，跳过未注册 ID 和不允许的 `bonus_type`，重算 `flat_bonus / percent_bonus` 并以 `dataclasses.replace` 返回新表 |
| `add_modifier(modifier) -> PetAttributeSheet` | 在已有 `modifiers` 上追加并重算 |
| `remove_modifiers_from_source(source_id) -> PetAttributeSheet` | 过滤掉 `source_id` 不等的修饰器后重算（用于卸下某件灵痕） |

### `PetEffectiveStats`（`frozen=True, slots=True`）

字段：`physics`、`idle_min_seconds / idle_max_seconds`、`reachable_wander_probability`、`min_wander_distance_factor`、`flight_speed / landing_speed`、`wing_open_seconds / wing_close_seconds`、`hover_amplitude / hover_frequency`、`max_stamina / base_stamina / stamina_recovery`、`max_energy / base_energy / energy_recovery`、`satiety / base_satiety`。

构造：`from_sheet(config, sheet)`，按 6 个关键属性比值（被 `_clamp` 到 `[0.25, 3.0]`）缩放原 `PhysicsConfig` 和行为参数。

#### `from_sheet` 关键公式

| 目标字段 | 公式 |
| --- | --- |
| `physics.walk_speed` | `max(config.physics.walk_speed × mobility_ratio, 1.0)` |
| `physics.climb_speed` | `max(config.physics.climb_speed × cling_ratio, 1.0)` |
| `physics.jump_speed_x / y` | `config.physics.jump_speed_* × leap_ratio` |
| `idle_min/max_seconds` | `max(config.behavior.idle_{min,max} × (1 / wander_ratio), 0.1)` |
| `reachable_wander_probability` | `clamp(0.5 × wander_ratio, 0.05, 0.95)` |
| `flight_speed / landing_speed` | `max(config.pet.flight.{speed,landing_speed} × arcana_ratio, 1.0)` |
| `wing_open / close_seconds` | `max(config.pet.wings.{open,close}_seconds / attunement_ratio, 0.05)` |
| `hover_amplitude` | `max(config.pet.hover.amplitude × arcana_ratio, 0.0)` |
| `hover_frequency` | `max(config.pet.hover.frequency × attunement_ratio, 0.05)` |
| `max_stamina / base_stamina` | `max(vigor_total / base, 1.0)` |
| `stamina_recovery` | `max(recovery_total, 0.0)` |
| `max_energy / base_energy` | `max(awareness_total / base, 1.0)` |
| `energy_recovery` | `max(focus_total, 0.0)` |
| `satiety / base_satiety` | `max(satiety_total / base, 1.0)` |

> `*_ratio = clamp(attribute_total / max(|base|, 1.0), 0.25, 3.0)`；`leap` 基础值是 `(|jump_speed_x| + |jump_speed_y|) / 2`。

### `PetResourceInfluence`（`frozen=True, slots=True`）

字段：`movement_factor / climb_factor / jump_factor / wander_factor / special_factor / recovery_factor / sleep_pressure / feeding_pressure`（0.0–1.0 行为缩放与触发概率） + 6 个开关量 `should_sleep / should_wake / should_rest / should_stop_rest / should_seek_food / should_stop_seek_food`。

构造：`from_resources(resources, stats)`，用 `_smooth_ratio(ratio, start, end)` 在阈值区间做平滑插值，组合为各 factor。

| factor | 公式 |
| --- | --- |
| `movement_factor` | `clamp((0.70 + 0.30·stamina_ready) · (0.85 + 0.15·satiety_ready), 0.25, 1.0)` |
| `climb_factor` | `clamp((0.35 + 0.65·stamina_burst) · (0.85 + 0.15·satiety_ready), 0.25, 1.0)` |
| `jump_factor` | `clamp((0.40 + 0.60·stamina_burst) · (0.90 + 0.10·satiety_ready), 0.25, 1.0)` |
| `wander_factor` | `clamp((0.15 + 0.85·energy_ready) · (0.25 + 0.75·stamina_ready) · (0.35 + 0.65·satiety_ready), 0.0, 1.0)` |
| `special_factor` | `clamp((0.10 + 0.90·special_ready) · (0.50 + 0.50·satiety_ready), 0.0, 1.0)` |
| `recovery_factor` | `clamp(0.25 + 0.75·satiety_ready, 0.25, 1.0)` |
| `sleep_pressure` | `clamp(1 − smooth_ratio(energy_ratio, 0.10, 0.45), 0.0, 1.0)` |
| `feeding_pressure` | `clamp(1 − smooth_ratio(satiety_ratio, 0.10, 0.40), 0.0, 1.0)` |

阈值开关：

| 开关 | 触发 | 解除 |
| --- | --- | --- |
| `should_sleep` / `should_wake` | energy_ratio ≤ 0.10 | ≥ 0.45 |
| `should_rest` / `should_stop_rest` | stamina_ratio ≤ 0.15 | ≥ 0.40 |
| `should_seek_food` / `should_stop_seek_food` | satiety_ratio ≤ 0.10 | ≥ 0.35 |

### `PetRuntimeResources`（`@dataclass(slots=True)`，**可变**）

字段：`stamina / energy / satiety`（必填浮点）。

方法：

- `from_stats(stats) -> PetRuntimeResources`：满体力/精力/饱腹。
- `clamp_to_stats(stats) -> None`：截断到 `[0, max]`。
- `tick(state, dt, stats) -> None`：核心每秒资源扣减/恢复（详见下方）。
- `influence(stats) -> PetResourceInfluence`：包装 `PetResourceInfluence.from_resources`。
- `stamina_ratio(stats) / energy_ratio(stats) / satiety_ratio(stats)`：当前值 / `base_*`。

`tick` 规则（`dt = max(dt, 0.0)`）：

- `SLEEP`：`energy += stats.energy_recovery · recovery_factor · dt`；`stamina += stats.stamina_recovery · recovery_factor · dt`。
- `IDLE / DRAGGED`：`stamina += stats.stamina_recovery · recovery_factor · 0.5 · dt`；`energy -= 0.1 · (1 + feeding_pressure · 0.35) · dt`。
- 其它：`stamina -= _stamina_cost_for_state(state) · dt`；`energy -= 0.25 · (1 + feeding_pressure · 0.35) · dt`。
- 全部状态：`satiety -= _satiety_cost_for_state(state) · (100 / max(base_satiety, 1)) · dt`。
- 最后 `clamp_to_stats`。

消耗表（每秒）：

| 状态 | stamina/s | satiety/s |
| --- | --- | --- |
| SLEEP | （恢复） | 0.008 |
| IDLE / DRAGGED | （恢复 0.5×） | 0.012 |
| CLIMB | 2.5 | 0.035 |
| JUMP | 2.0 | 0.035 |
| FLY / HOVER / WING_LAND | 1.8 | 0.035 |
| WALK | 1.0 | 0.02 |
| 其余 | 0.5 | 0.016 |

### 模块级常量 / 字典

- `PET_ATTRIBUTE_DEFINITIONS: tuple[PetAttributeDefinition, ...]`（16 个）
- `PET_ATTRIBUTE_DEFINITIONS_BY_ID: dict[str, PetAttributeDefinition]`
- `PET_ATTRIBUTE_ID_BY_NAME` / `PET_ATTRIBUTE_ID_BY_ENGLISH_NAME`
- `attribute_id_for_name(name: str) -> str | None`：先查中文，再查英文

### 16 个属性一览

| id | 中文 | 英文 | 类别 | allowed_bonus_types | value_format |
| --- | --- | --- | --- | --- | --- |
| mobility | 机动 | Mobility | basic | flat, percent | number |
| cling | 攀附 | Cling | basic | flat, percent | number |
| leap | 腾跃 | Leap | basic | flat, percent | number |
| wander | 巡游 | Wander | basic | flat | number |
| vigor | 元气 | Vigor | basic | flat | number |
| recovery | 生息 | Recovery | basic | flat | number |
| awareness | 灵识 | Awareness | basic | flat | number |
| focus | 凝神 | Focus | basic | flat | number |
| satiety | 饱腹 | Satiety | basic | flat | number |
| spark | 迸发 | Spark | visual | percent | percent |
| radiance | 辉映 | Radiance | visual | flat | number |
| trail | 留痕 | Trail | visual | flat | number |
| resonance | 共鸣 | Resonance | visual | flat | number |
| aura | 灵韵 | Aura | visual | flat | number |
| arcana | 异能 | Arcana | special | flat | number |
| attunement | 调律 | Attunement | special | flat | number |

---

## 物品 / 背包

[`inventory.py`](inventory.py)：

```python
Details = tuple[tuple[str, str], ...]  # 小写 detail 键 → 值

@dataclass(frozen=True, slots=True)
class ItemCategory:
    id: str
    name: str
    order: int

@dataclass(frozen=True, slots=True)
class ItemDefinition:
    id: str
    category_id: str
    name: str
    description: str
    image: Path         # 解析为绝对路径
    stackable: bool
    details: Details    # 默认 ()

@dataclass(frozen=True, slots=True)
class InventoryEntry:
    entry_id: str
    item_id: str
    quantity: int = 1
    details: Details = ()

@dataclass(frozen=True, slots=True)
class InventorySnapshot:
    categories: tuple[ItemCategory, ...] = ()
    item_definitions: dict[str, ItemDefinition] = {}
    entries: tuple[InventoryEntry, ...] = ()
```

`InventorySnapshot` 方法：

- `empty()` → `InventorySnapshot()`。
- `entries_for_category(category_id)`：按 `item_definitions[entry.item_id].category_id` 过滤。
- `definition_for(entry)` / `details_for(entry)`：合并 `definition.details` + `entry.details`（后者覆盖前者）。

模块级公开函数：

```python
def load_inventory(items_path, inventory_path=None, spirit_mark_path=None) -> InventorySnapshot
def append_inventory_entry(path, entry) -> None
def spirit_mark_item_id_for_slot(snapshot, slot_id) -> str
def apply_spirit_mark_details(definitions, entries, spirit_marks) -> tuple[dict, tuple]
```

- `load_inventory` 默认布局：`items_path` 同级 `user/inventory.json` 与 `user/spirit_marks.json`；任何文件异常（`OSError` / `json.JSONDecodeError` / `InventoryValidationError`）被记录并回退到空目录 / 已有目录。
- `append_inventory_entry` 写入策略：`quantity == 1` 不写字段；`details` 为空不写；`entry_id` 重复抛 `InventoryValidationError`；写入 JSON 用 `ensure_ascii=False, indent=2`，结尾换行。
- `spirit_mark_item_id_for_slot`：先以 `id` 后缀 `.{slot_id}` 匹配，再以 detail 中 `部位 == slot_name` 匹配；都没有抛 `InventoryValidationError`。
- `apply_spirit_mark_details`：内存版回填（与文件 I/O 无关），为每个已装备灵痕生成 `instance_definition`（id 为 `{base.id}#{entry_id}`），并把 `entry.item_id` 改写为实例 id。

`InventoryValidationError(ValueError)`：唯一公开异常。

---

## 灵痕

[`spirit_mark.py`](spirit_mark.py)：

### 模块级常量

- `SPIRIT_MARK_CATEGORY_ID = "spirit_mark"`
- `SPIRIT_MARK_SLOTS`：5 槽位（`core` / `form` / `meridian` / `edge` / `echo`）— 灵核 / 形骸 / 脉络 / 锋质 / 余响
- `SPIRIT_MARK_SETS`：5 套装（`silent_guardian` / `stardust_echo` / `windfarer` / `falling_echo` / `flowing_mirage`）— 静默守护 / 星尘余响 / 破风远行 / 坠落回响 / 幻形流转
- `PRIMARY_STAT_POOLS`：按槽位 → 4 个主词条候选
- `ALL_STATS = tuple(definition.name for definition in PET_ATTRIBUTE_DEFINITIONS)`
- `STYLE_SET_HINTS`：风格关键字 → 套装 ID 映射（`ambient` / `quiet` → `silent_guardian` 等）

### 关键 dataclass

```python
@dataclass(frozen=True, slots=True)
class SpiritMarkSlot:    id / name / description

@dataclass(frozen=True, slots=True)
class SpiritMarkSet:     id / name / style / two_piece_stat / two_piece_value
                        / two_piece_bonus_type / four_piece_description

@dataclass(frozen=True, slots=True)
class SpiritMarkStat:    name / value / bonus_type: BonusType = "flat"

@dataclass(frozen=True, slots=True)
class SpiritMarkGrantRequest:
    entry_id: str = ""
    source_type: str = "manual"
    source_id: str = ""
    source_description: str = "这道灵痕来自一次手动纪念。"
    quality_hint: str = ""                       # "completed" / "excellent" → 最低 3 星
    style_hint: str = ""                          # 走 STYLE_SET_HINTS
    set_hint: str = ""                            # 命中 SPIRIT_MARK_SETS 则强制套装
    rarity_hint: str | int = ""                   # 整数 / 数字串 → 1–5
    record_tags: tuple[str, ...] = ()

@dataclass(frozen=True, slots=True)
class SpiritMark:
    entry_id / name / slot_id / set_id / rarity
    main_stat: SpiritMarkStat
    sub_stats: tuple[SpiritMarkStat, ...]
    level: int = 0
    source_type: str = "manual"
    source_id: str = ""
    source_description: str = ""
    created_at: str = ""
    favorite: bool = False
    equipped: bool = False
    fractured: bool = False
    record_tags: tuple[str, ...] = ()
```

属性：`max_level = max_level_for_rarity(rarity) = 4 + min(5, max(1, rarity)) * 2`（即 1→6、2→8、3→10、4→12、5→14）。

### `SpiritMarkMaterials`（`frozen=True, slots=True`）

`spirit_dust: int = 0`、`essence: int = 0`、`stardust_core: int = 0`、`remnant: int = 0`、`set_dust: dict[str, int] = {}`。当前生产代码不消费，但被 `decompose()` 返回并被测试断言。

### `SpiritMarkInventory`（`frozen=True, slots=True`）

| 字段 | 类型 | 默认 |
| --- | --- | --- |
| `marks` | `tuple[SpiritMark, ...]` | `()` |
| `materials` | `SpiritMarkMaterials` | `SpiritMarkMaterials()` |

方法（**全部为纯函数式** — 返回新 `SpiritMarkInventory`）：

| 签名 | 行为 |
| --- | --- |
| `mark_by_entry_id(entry_id)` | 找不到返回 `None` |
| `equipped_marks()` | 过滤 `equipped=True` |
| `equip(entry_id) -> SpiritMarkInventory` | 把同 `slot_id` 已装备全部卸下（`equipped=False`），再把目标 `entry_id` 置为装备 |
| `unequip(entry_id) -> SpiritMarkInventory` | 仅把目标 `entry_id` 的 `equipped` 置 `False` |
| `set_favorite(entry_id, favorite=True) -> SpiritMarkInventory` | 切换收藏 |
| `enhance(entry_id, *, rng=None) -> SpiritMarkInventory` | 到 `max_level` 抛 `SpiritMarkError`；主词条 `value += 1 + (1 if rng.random() < 0.25 + rarity*0.03 else 0)`；副词条轮询位置 `level % max(1, len(sub_stats))` 加 1 |
| `decompose(entry_id) -> tuple[SpiritMarkInventory, SpiritMarkMaterials]` | 收藏的灵痕禁止分解；按公式产出材料（见下） |
| `stat_totals() -> dict[str, int]` | 键格式 `"{name}:{bonus_type}"`；仅统计已装备 + 套装 2 件奖励 |
| `formatted_stat_totals() -> tuple[str, ...]` | 按名称排序后 `format_spirit_mark_stat` |
| `attribute_modifiers() -> tuple[PetAttributeModifier, ...]` | `stat_totals` → 属性修饰器；套装奖励 `source_id = "set:{set_id}:2"`，`source_type = "spirit_mark_set"`，过滤掉 `attribute_id == ""` 的无效项 |
| `set_counts() -> dict[str, int]` | 已装备灵痕的套装计数 |

### 灵痕业务规则

- **槽位互斥**：`equip()` 先把同 `slot_id` 已装备的全部卸下，再置目标为装备。
- **强化上限**：`enhance()` 到达 `max_level_for_rarity(rarity)` 后抛 `SpiritMarkError`。
- **强化收益**：主词条额外加 1 的概率为 `0.25 + rarity*0.03`；副词条按 `level % max(1, len(sub_stats))` 轮询加 1。
- **收藏**：仅阻止 `decompose()`；不影响 `enhance()` / `equip()`。
- **分解禁止**：`favorite=True` 抛 `SpiritMarkError`。
- **分解公式**：
  - `spirit_dust = rarity*6 + level*3`
  - `essence = max(0, rarity-2) + level // 4`
  - `stardust_core = 1 if rarity >= 5 else 0`
  - `remnant = 2 if fractured else 0`
  - `set_dust = {set_id: max(1, level // 3)}` 当 `level > 0`，否则 `{}`
- **套装奖励**：2 件套触发 — 来自 `SPIRIT_MARK_SETS[*].two_piece_stat / value / bonus_type`；4 件套尚未实现数值化（只保留 `four_piece_description` 文本描述）。
- **灵痕→属性转换**：`attribute_modifiers()` 是 `stat_totals()` 的别名翻译；中文名经 `attribute_id_for_name()` 查 id，未知属性返回 `attribute_id=""` 并在结果中被过滤。

`SpiritMarkError(ValueError)`：灵痕相关错误。

### 公开函数

```python
def generate_spirit_mark(request, *, rng=None, now=None) -> SpiritMark
def max_level_for_rarity(rarity: int) -> int
def format_spirit_mark_stat(stat) -> str                    # percent → "name +value%"，否则 "name +value"
def load_spirit_mark_inventory(path) -> SpiritMarkInventory
def save_spirit_mark_inventory(path, inventory) -> None
def spirit_mark_inventory_from_dict(data) -> SpiritMarkInventory
def spirit_mark_inventory_to_dict(inventory) -> dict
def spirit_mark_from_dict(data) -> SpiritMark
def spirit_mark_to_dict(mark) -> dict
```

`generate_spirit_mark` 关键流程：

1. `slot_id = rng.choice(tuple(SPIRIT_MARK_SLOTS))`。
2. `set_id` 优先 `set_hint`，其次 `style_hint` 走 `STYLE_SET_HINTS`，最后随机。
3. `rarity`：`rarity_hint` 为整数或数字串时夹到 1–5；否则 `quality_hint in {"completed","excellent"}` 时保底 3 星，权重 `[30,28,22,14,6]` 抽 1–5。
4. `fractured = quality_hint in {"interrupted","failed","fractured"}`。
5. `main_name` 从 `PRIMARY_STAT_POOLS[slot_id]` 随机；`main_bonus_type` 按 `_select_bonus_type` 选。
6. `sub_count = max(1, min(4, rarity-1))`，从其余属性中无放回抽样后逐个 roll。
7. `entry_id` 缺省时用 `f"sm-{YYYYMMDDHHMMSS}-{randrange(1000,10000)}"`。
8. `name = f"{set.name}·{slot.name}"`，`created_at = now.isoformat()`。

---

## 灵痕发放服务

[`spirit_mark_service.py`](spirit_mark_service.py)：

```python
@dataclass(frozen=True, slots=True)
class SpiritMarkGrantResult:
    mark: SpiritMark
    inventory_snapshot: InventorySnapshot
    spirit_mark_inventory: SpiritMarkInventory

def grant_spirit_mark(
    request: SpiritMarkGrantRequest,
    *,
    items_path: str | Path,
    inventory_path: str | Path,
    spirit_mark_path: str | Path,
) -> SpiritMarkGrantResult
```

`grant_spirit_mark` 流程（2 次磁盘写）：

1. `_load_catalog(items)` + `load_spirit_mark_inventory(spirit_mark_file)` 各一次磁盘读。
2. `generate_spirit_mark(request)` 生成新灵痕，`_find_item_id_for_slot(definitions, mark.slot_id)` 找目录 id。
3. `append_inventory_entry(inventory_file, InventoryEntry(mark.entry_id, item_id))`：原样追加无富化的条目。
4. 构造 `new_spirit_marks = SpiritMarkInventory((*current.marks, mark), current.materials)`。
5. 内存 `_ensure_inventory_file` + `_read_object` 读 inventory，再用 `apply_spirit_mark_details(definitions, base_entries, new_spirit_marks)` 构造富化 `InventorySnapshot`。
6. `save_spirit_mark_inventory(spirit_mark_file, new_spirit_marks)` 落盘。
7. 返回 `SpiritMarkGrantResult`。

私有：`_find_item_id_for_slot(definitions, slot_id)`（不导出）。

---

## 持久化入口与文件映射

| 入口 | 文件（默认） | 写入 JSON 风格 | 关键方法 |
| --- | --- | --- | --- |
| `load_inventory(items_path, inventory_path=None, spirit_mark_path=None)` | `items.json` + `user/inventory.json` + `user/spirit_marks.json` | `ensure_ascii=False, indent=2` | 顶层 / `append_inventory_entry` / `apply_spirit_mark_details` |
| `load_spirit_mark_inventory(path)` / `save_spirit_mark_inventory(path, inventory)` | `user/spirit_marks.json` | `ensure_ascii=False, indent=2`，结尾 `\n` | 顶部 `_ensure_spirit_mark_file` 写入空 schema：`{"marks": [], "materials": {...}}` |
| `grant_spirit_mark(request, *, items_path, inventory_path, spirit_mark_path)` | 上述三处 | 1 次 `append_inventory_entry` + 1 次 `save_spirit_mark_inventory` | 返回 `SpiritMarkGrantResult` |

补充：

- inventory / spirit_mark 文件不存在时 `_ensure_*_file` 会 `mkdir(parents=True, exist_ok=True)` 并写入空 schema。
- 灵痕材料的 `set_dust` 是 `dict[str, int]`，序列化时保持键为字符串。
- `append_inventory_entry` 不做原子重命名（直写），生产侧如需崩溃一致性可在外层包裹 `tempfile + os.replace`。

---

## 跨包依赖图

```
state.py
  └── geometry.py
window_info.py
  └── geometry.py
platform.py
  └── geometry.py
platform_topology.py
  └── platform.py
pet_attribute.py
  ├── state.py
  └── utils.config.{AppConfig, PhysicsConfig}
inventory.py
  ├── spirit_mark.py
  └── (间接) pet_attribute.py
spirit_mark.py
  ├── pet_attribute.py
  └── (json, random, datetime)
spirit_mark_service.py
  ├── inventory.py
  └── spirit_mark.py
```

外部依赖（`utils/`）：`utils.config.{AppConfig, PhysicsConfig, BehaviorConfig, PetConfig, FlightConfig, WingsConfig, HoverConfig, AttributesConfig}`（详见 [../utils/README.md](../utils/README.md)）。
