# 寻路系统说明

本文档描述当前项目中的寻路系统实现。系统以 `Surface Graph` 为核心，把可移动的水平平台和竖直墙面统一建模为 `Surface`，再通过事件点节点和动作边生成可搜索路径。路径搜索只负责在图上找最短动作序列，路径执行器只根据动作类型解释 `PathStep`。

## 总体流程

当前寻路系统主要分为五个阶段：

1. 从环境快照生成 Surface
2. 构建 Surface Graph
3. 在图上搜索最短路径
4. 将图边映射为 PathStep
5. PathExecutor 按 PathStep 执行动作

### 1. Surface 生成

环境层提供的是 `Platform`，寻路层通过 `Surface.from_platform()` 将其转换为统一的 `Surface`。

水平 surface：

- 来源：地面、任务栏、窗口顶部等 `walkable` 平台
- 方向：`SurfaceOrientation.HORIZONTAL`
- 能力：`MOVE`、`FALL`、`JUMP_TARGET`
- anchor 含义：`anchor_t` 表示角色左上角的 `x`

竖直 surface：

- 来源：窗口左右边缘等 `climbable` 墙面
- 方向：`SurfaceOrientation.VERTICAL`
- 能力：`MOVE`、`TRANSFORM`、`JUMP_TARGET`
- anchor 含义：`anchor_t` 表示角色的 `bottom`，即角色底部所在的世界 y 坐标

Surface 是当前寻路系统的统一拓扑单元。水平移动和竖直移动都被视为在某个 surface 上进行 `MOVE`，区别只在于移动轴和速度不同。

### 2. Surface Graph 构建

`PathFinder.build_surface_graph()` 根据当前宠物、环境快照和物理配置生成 `SurfaceGraph`。

图构建的核心原则是：节点只出现在跨 surface 行为或路径端点需要的位置。同一 surface 内的连续移动不生成密集网格，而是在事件点之间自动连线。

图构建会生成以下动作边：

- `MOVE`
- `TRANSFORM`
- `FALL`
- `JUMP`

每次向某个 surface 添加节点时，系统会调用 `_rewire_surface_move()`。该函数收集同一 surface 上的所有节点，按 `anchor_t` 排序，然后在相邻节点之间生成双向 `MOVE` 边。

### 3. 路径搜索

当需要去某个 surface 的某个 anchor 时，调用：

```python
PathFinder.find_path_to_surface_point(...)
```

流程如下：

1. 从 `pet.support_surface_id` 获取当前支撑 surface
2. 将目标 anchor 通过 `_clamp_anchor()` 限制到目标 surface 可用范围内
3. 如果起点和目标在同一个 surface，直接返回单步 `MOVE`
4. 否则构建 `SurfaceGraph`
5. 在图中插入当前点和目标点
6. 使用 `GraphPlanner.shortest_path_tree()` 进行最短路径搜索
7. 将搜索得到的 `NavEdge` 序列转换为 `PathStep`
8. 合并连续同 surface 的 `MOVE` step
9. 返回 `PathPlan`

按窗口寻路的入口是：

```python
PathFinder.find_path(...)
```

它会把目标窗口映射到窗口顶部 surface，并把目标 anchor 设为窗口顶部中心附近。

### 4. PathStep 映射

图搜索返回的是 `NavEdge`，执行器使用的是 `PathStep`。转换由 `_to_path_step()` 完成。

`MOVE` step 的目标是目标节点的 `anchor_t`。

`JUMP`、`FALL`、`TRANSFORM` step 会记录：

- `target_t`：起跳、下落或转换前需要先移动到的源 surface anchor
- `land_t`：动作完成后落到目标 surface 的 anchor
- `approach_point`：动作开始前的世界坐标
- `land_point`：动作完成后的世界坐标

这样执行器不需要重新推断跳跃或转换终点，而是直接执行计划中记录的点。

### 5. 路径执行

`PathExecutor.execute_path_plan()` 每帧读取 `PathPlan.current_step` 并按动作类型执行。

执行前会检查：

- 当前 step 的 source surface 是否仍存在
- target surface 是否仍存在
- `contact_surface_id` 是否仍存在
- 宠物当前支撑 surface 是否与 step 的 `from_surface_id` 匹配

如果检查失败，路径计划会被取消。

## 数据结构

### Surface

```python
Surface(
    id: str,
    rect,
    orientation: SurfaceOrientation,
    capabilities: frozenset[SurfaceCapability],
    dynamic: bool,
    source_id: int | None,
    type: PlatformType | None,
)
```

含义：

- `id`：surface 唯一标识
- `rect`：世界坐标矩形
- `orientation`：水平或竖直
- `capabilities`：该 surface 支持的动作能力
- `dynamic`：是否来自动态窗口
- `source_id`：所属窗口 id
- `type`：来源平台类型

### SurfaceOrientation

```python
HORIZONTAL
VERTICAL
```

水平 surface 的移动轴是 x，竖直 surface 的移动轴是 y。

### SurfaceCapability

```python
MOVE
JUMP_TARGET
FALL
TRANSFORM
```

能力用于描述 surface 可以参与哪些动作。

### TraversalAction

```python
MOVE
JUMP
TRANSFORM
FALL
```

这是路径中的动作类型，也是图边和执行 step 的动作枚举。

### NavNode

```python
NavNode(
    id: str,
    surface_id: str,
    anchor_t: float,
    role: NavNodeKind,
    x: float,
    y: float,
)
```

含义：

- `surface_id`：节点所在 surface
- `anchor_t`：节点在 surface 上的参数位置
- `role`：事件点类型
- `x/y`：该 anchor 对应的角色左上角世界坐标

节点不是任意采样点，而是跨 surface 行为、起点、终点等事件点。

### NavNodeKind

```python
EVENT_POINT
DROP_POINT
JUMP_POINT
TRANSFORM_POINT
```

含义：

- `EVENT_POINT`：通用事件点
- `DROP_POINT`：下落事件点
- `JUMP_POINT`：跳跃事件点
- `TRANSFORM_POINT`：surface 转换事件点

### NavEdge

```python
NavEdge(
    from_node_id: str,
    to_node_id: str,
    action: TraversalAction,
    cost: float,
    contact_surface_id: str | None = None,
    meta: dict[str, float | str] = {},
)
```

`NavEdge` 是图搜索使用的边。它连接两个 `NavNode`，表示一个可执行动作。

### SurfaceGraph

```python
SurfaceGraph(
    nodes: dict[str, NavNode],
    adjacency: dict[str, list[NavEdge]],
    surfaces: dict[str, Surface],
)
```

含义：

- `surfaces`：所有参与寻路的 surface
- `nodes`：事件点节点
- `adjacency`：有向邻接表
- `edges`：从邻接表展开得到的所有边

### PathStep

```python
PathStep(
    action: TraversalAction,
    from_surface_id: str,
    to_surface_id: str,
    target_t: float,
    cost: float,
    contact_surface_id: str | None = None,
    land_t: float | None = None,
    approach_point: tuple[float, float] | None = None,
    land_point: tuple[float, float] | None = None,
)
```

`PathStep` 是执行器消费的路径步骤。

字段含义：

- `action`：动作类型
- `from_surface_id`：动作起始 surface
- `to_surface_id`：动作目标 surface
- `target_t`：执行动作前需要先移动到的 source anchor
- `cost`：搜索成本
- `contact_surface_id`：转换或接触相关 surface
- `land_t`：动作完成后的目标 anchor
- `approach_point`：动作开始点的世界坐标
- `land_point`：动作完成点的世界坐标

### PathPlan

```python
PathPlan(
    steps: list[PathStep],
    current_index: int,
    target_window_id: int | None,
    snapshot_timestamp: float,
    target_surface_id: str | None,
    target_anchor_t: float | None,
)
```

`PathPlan` 保存完整路径和当前执行进度。

核心属性：

- `steps`：路径步骤列表
- `current_index`：当前执行到第几个 step
- `current_step`：当前 step
- `is_complete`：是否执行完成

## 动作边生成规则

### MOVE

`MOVE` 表示同一 surface 内移动。

生成方式：

1. 每个 surface 上可能有多个事件节点
2. `_rewire_surface_move()` 按 `anchor_t` 排序
3. 相邻节点之间生成双向 `MOVE`

成本：

```python
abs(to_t - from_t) / move_speed
```

速度选择：

- 水平 surface 使用 `walk_speed`
- 竖直 surface 使用 `climb_speed`

执行效果：

- 水平 `MOVE` 改变 x，进入 `PetState.WALK`
- 竖直 `MOVE` 改变 y，进入 `PetState.CLIMB`

### TRANSFORM

`TRANSFORM` 表示两个直接接触或相交的 surface 之间的切换。

生成条件：

- source 和 target 方向不同
- 二者矩形相交

典型情况：

- 窗口顶部 surface 与窗口侧墙 surface 互相转换
- 平台与相交墙面转换

转换点计算：

- 水平 anchor 取竖直 surface 中心对应的 x
- 竖直 anchor 取水平 surface 顶部对应的 y
- 两者都经过 `_clamp_anchor()` 限制到 surface 范围内

成本：

```python
0.0
```

执行效果：

- 目标是竖直 surface：设置支撑和目标为墙面，进入 `CLIMB`
- 目标是水平 surface：设置支撑为平台，清空目标 surface，进入 `WALK`

### FALL

`FALL` 表示从水平 surface 边缘垂直下落到下方水平 surface。

生成条件：

- 只从水平 surface 左右边缘生成
- 边缘外侧必须有足够空间
- 垂直射线必须命中下方最近的水平 surface

下落点：

- 左边缘使用 `source.rect.left - pet.width`
- 右边缘使用 `source.rect.right`

成本：

```python
sqrt(2 * vertical_distance / gravity)
```

执行效果：

1. 先在 source surface 上 `MOVE` 到下落点
2. 清空 `support_surface_id`
3. 设置 `target_surface_id`
4. 进入 `PetState.FALL`

### JUMP

`JUMP` 表示从水平 surface 跳到另一个 surface。

生成条件：

- source 必须是水平 surface
- target 可以是水平 surface 或竖直 surface
- 不支持竖直 surface 作为跳跃起点
- 同一窗口内部不生成跳跃
- 如果两个 surface 已经可以通过直接 `TRANSFORM` 连接，则不生成跳跃
- 如果水平目标可以通过下落到达，则不生成跳跃
- 候选点必须通过 `_jump_reachable()` 的抛体可达性检查

跳跃点选择：

- 水平到水平：在两个水平 anchor 区间之间选择最近点对
- 水平到竖直：源点选择离墙 x 最近的可起跳点，目标 y 选择离源 y 最近的墙面可接触点
- 所有 anchor 都会通过 `_clamp_anchor()` 限制到 surface 范围内

可达性检查：

`_jump_reachable()` 使用当前物理参数判断起终点在最大水平速度、最大竖直速度和重力下是否可达。

使用参数：

- `jump_speed_x`
- `jump_speed_y`
- `gravity`
- `edge_snap_distance`

检查思路：

1. 将 source anchor 和 target anchor 转成世界坐标
2. 用水平距离和最大水平速度估算飞行时间
3. 根据抛体公式计算所需竖直初速度
4. 如果需要的水平速度或竖直速度超过上限，则不可达
5. 同层贴近或重叠的水平 surface 不使用跳跃

执行效果：

1. 先在 source surface 上 `MOVE` 到起跳点
2. 根据 `land_point` 计算跳跃初速度
3. 清空支撑 surface
4. 设置目标 surface
5. 进入 `PetState.JUMP`
6. 如果目标是墙面，控制器会在跳跃过程中根据计划落点尝试抓墙

## 执行器行为

路径执行由 `PathExecutor` 完成。

### execute_path_plan()

每帧执行当前 `PathPlan.current_step`。

执行前检查：

- step 是否存在
- step 中的 source surface 是否仍存在
- step 中的 target surface 是否仍存在
- step 的 contact surface 是否仍存在
- 当前支撑 surface 是否匹配 step 的 source surface

如果当前支撑 surface 已经等于 step 的 target surface，且 step 不是 `MOVE`，执行器会直接推进到下一步。

### move_along_surface()

统一处理水平和竖直 surface 内移动。

水平 surface：

- 目标值是 x
- 设置 `velocity.x`
- 清空 `velocity.y`
- 进入 `WALK`

竖直 surface：

- 目标值是 `target_t - pet.height`
- 设置 `velocity.y`
- 清空 `velocity.x`
- 设置当前支撑和目标 surface
- 进入 `CLIMB`

到达或越过目标时，会直接 snap 到目标位置并清零对应速度。

### JUMP 执行

`start_jump_toward_surface()` 使用 `PathStep.land_point` 作为跳跃目标点。

目标是水平 surface 时，会把 x 限制在目标 surface 可站立范围内。

目标是竖直 surface 时，直接使用计划中的墙面接触点。

### TRANSFORM 执行

`execute_transform_step()` 根据目标 surface 类型切换状态。

目标是竖直 surface：

- 位置设置到 `land_point`
- 支撑 surface 设置为目标 surface
- 目标 surface 设置为目标 surface
- 进入 `CLIMB`

目标是水平 surface：

- 位置设置到 `land_point`
- 支撑 surface 设置为目标 surface
- 清空目标 surface
- 进入 `WALK`

## 控制器职责

`PetController` 不直接构造跨 surface 行为，而是：

- 请求 `PathFinder` 生成 `PathPlan`
- 调用 `PathExecutor` 执行当前 step
- 在环境刷新后验证当前 step 仍有效
- 在 `JUMP` 状态下处理计划内的墙面抓取
- 在空闲时通过 Surface Graph 选择随机可达水平 surface

控制器中的路径验证只检查当前 step 依赖的 surface 是否仍存在。若当前 surface 消失，路径会被取消。

## Debug 显示

debug overlay 直接读取当前 `SurfaceGraph` 和 `PathPlan`。

显示内容包括：

- 当前状态
- 位置、速度、支撑 surface
- surface 数量
- graph 节点数和边数
- MOVE / FALL / JUMP / TRANSFORM 边统计
- 当前 path step 进度
- 每个 step 的动作、目标 surface、anchor 和世界坐标

图形绘制：

- surface 显示为平台或墙面的矩形
- graph 节点显示在事件点位置
- graph 边用虚线显示
- 当前路径用更醒目的线条显示
- 路径绘制使用 `PathStep.approach_point` 和 `PathStep.land_point`，不重新猜测跳跃或转换终点

## 当前效果

当前寻路系统达到了以下效果：

- 水平平台和竖直墙面统一进入 Surface Graph
- 水平移动和竖直移动统一为 `MOVE`
- 平台与墙面的接入统一为 `TRANSFORM`
- 下落行为统一为 `FALL`
- 跳跃行为统一为 `JUMP`
- 图构建只生成可执行动作边
- 搜索层只做最短路径搜索
- 执行层只按 `PathStep` 动作解释路径
- 竖直墙面移动由路径执行器控制，不由物理系统自动爬顶
- 跳到墙面时使用计划中的落点，而不是固定墙底
- 路径中的 surface 消失时，计划会被取消
- debug 显示可以直接反映 Surface Graph 与 PathStep 的实际内容

整体上，当前系统把“平台行走”和“墙面攀爬”统一成同一种 surface 内移动模型，把跨 surface 的行为收敛为少数动作类型，从而让图构建、路径搜索和路径执行的职责更清晰。
