## 寻路系统重构方案：统一“表面图”模型（平台/墙同构）

### Summary
将当前“平台+墙特判”的寻路重构为统一的**Surface Graph（表面图）**：水平平台与竖直墙都视为 `Surface`，只用“方向（horizontal/vertical）+可用动作能力”区分。  
采用你选择的方案：`事件点图`。目标是减少分支特判、统一边生成规则、提升可读性和可维护性，同时保持现有行为能力（走/跳/爬/下落）。

### Key Changes
- 核心建模统一
  - 新增统一类型：`Surface`（替代“walkable/climbable 分裂语义”），字段包含 `id/rect/orientation(owner window)/capabilities`。
  - 定义 `SurfaceOrientation = HORIZONTAL | VERTICAL`。
  - 定义 `TraversalAction = MOVE | JUMP | TRANSFORM | FALL`。
  - 统一节点：`NavNode(surface_id, anchor_t, role)`，其中 `anchor_t` 为表面参数坐标（水平表面用 x，竖直表面用 y）。
- 图构建规则（事件点图）
  - 节点只在事件点创建：仅保留不同Surface之间的联系节点：下落起点，下落终点，跳跃起点，跳跃终点，攀爬终点（没有攀爬起点，因为墙内的移动无需导航，处理逻辑和平台一致）。
  - 同表面内部连接统一为 `MOVE` 边（不再区分“平台 walk/墙 climb”的内部连通差异）。
  - `JUMP` 统一规则：任意表面（平台/墙）到任意表面（平台/墙）可尝试建边（但是需要不同窗口，因为对于同一窗口没有必要建立跳跃联系），受跳高/水平位移/可达时间窗约束。
  - `TRANSFORM` 规则：只在竖直墙与其相邻可转移水平表面间建边（如墙顶接入平台、平台接触墙），该边长度为0，仅建立了墙和平台之间的连接。
  - `FALL` 规则：仅从水平表面边缘向下做射线命中生成 `FALL` 边（保持你定义的平台下落联系语义）。
- 路径搜索与执行解耦
  - 搜索层仅处理 `NavEdge(action,cost,from_node,to_node)`，不再掺杂动作执行细节。
  - 执行层按动作分派：
    - `MOVE`：沿当前表面参数前进；
    - `JUMP`：弹道解算到目标事件点；
    - `TRANSFORM`：在墙和平台之间切换；
    - `FALL`：切换到自由落体并锁定目标命中表面窗口。
- 成本模型统一，通过一个统一的函数计算，目前仅包含各种行为所需的时间成本：
  - `MOVE`：表面参数距离 / move_speed。
  - `TRANSFORM`：0。
  - `JUMP`：飞行时间。
  - `FALL`：下落时间。
- 兼容与迁移
  - 保留对外接口 `find_path_to_point(...) -> PathPlan`，但 `PathEdge` 切换为基于 `surface_id` 与 `TraversalAction`。
  - 旧字段 `from_platform_id/to_platform_id/side_platform_id` 迁移为 `from_surface_id/to_surface_id/contact_surface_id?`。
  - `PlatformTopology` 收敛为 `SurfaceTopology`，仅做窗口几何关系映射，不承载动作语义。

### Public Interfaces / Types
- 新增/替换的关键类型
  - `Surface`, `SurfaceOrientation`, `TraversalAction`, `NavNode(anchor_t)`, `NavEdge`, `PathStep`（替代 `PathEdge`）。
- `PathFinder` 新职责
  - `build_surface_graph(snapshot, pet, physics) -> SurfaceGraph`
  - `find_path_to_surface_point(...target_surface_id, target_anchor_t...) -> PathPlan`
- `PathExecutor` 新职责
  - `execute_step(step)` 按 `TraversalAction` 分发；移除平台/墙分支特判。

### Test Plan
- 单元测试（图构建）
  - 水平->水平：相邻 `MOVE`，隔断可达 `JUMP`，超范围不可达。
  - 水平->竖直、竖直->水平、竖直->竖直：均可生成合法 `JUMP`（在能力范围内）。
  - `FALL` 仅从水平边缘命中下方表面时生成。
  - `TRANSFORM` 仅在墙与可接触表面间生成，不跨无接触几何关系。
- 单元测试（搜索与映射）
  - 最短路选择符合代价模型。
- 集成测试（执行）
  - 原有场景回归：地面到低窗、经中间窗到高窗、缝隙跳跃、不可达判定。
  - 新增场景：墙到墙跳跃、墙到平台跳跃、平台到墙跳跃。
- 验收标准
  - 现有 `test_pathfinding` 语义保留并扩展；新行为测试全部通过。
  - 重构后 `PathFinder` 中平台/墙分支数量显著下降（目标：动作规则集中到统一 builder 中）。

### Assumptions
- 采用你已确认的默认：`事件点图`。
- 物理参数沿用现有配置（`jump_speed_x/y`, `gravity`, `climb_speed`, `edge_snap_distance`）。
- 本次重构优先“逻辑统一与清晰”，性能优化（如空间索引、候选剪枝）作为二阶段增强。
