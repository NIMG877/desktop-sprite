# `desktop_sprite.ui` — PySide6 + Fluent 界面层

桌面宠物的全部窗口与控件，基于 PySide6 + qfluentwidgets。约 4200 行，11 个文件；不持有任何业务状态，全部由回调 + 数据驱动（`AppRuntime` 注入回调，`models` 注入数据）。

> 与本 README 互补：
> - 桌宠核心（被本层渲染与交互）见 [../core/README.md](../core/README.md)
> - 数据模型（被本层显示）见 [../models/README.md](../models/README.md)
> - 环境采集（被 `TargetSelectorOverlay` 与 `DebugOverlay` 消费）见 [../environment/README.md](../environment/README.md)
> - 配置加载与持久化入口见 [../utils/README.md](../utils/README.md)

---

## 目录

- [文件清单](#文件清单)
- [架构层级](#架构层级)
- [主题安全 API 用法](#主题安全-api-用法)
- [每个文件详细说明](#每个文件详细说明)
- [自定义控件 → Qt 父类与信号清单](#自定义控件--qt-父类与信号清单)
- [跨包依赖图](#跨包依赖图)

---

## 文件清单

| 路径 | 角色 | 行数级 |
| --- | --- | --- |
| `__init__.py` | re-export `SpriteWindow` | 极小 |
| [`main_window.py`](main_window.py) | `MainWindow(FluentWindow)`：唯一主入口 | 465 |
| [`sprite_window.py`](sprite_window.py) | 桌宠主窗口 + `DebugOverlayWindow` | 698 |
| [`show_overlay.py`](show_overlay.py) | Show 模式全屏遮罩 | 102 |
| [`target_selector.py`](target_selector.py) | 目标点选择器 | 151 |
| [`growth_widget.py`](growth_widget.py) | 养成页（属性 + 灵痕装备） | 708 |
| [`inventory_widget.py`](inventory_widget.py) | 背包页 + 通用卡片 | 505 |
| [`config_editor.py`](config_editor.py) | 设置页（配置树编辑器） | 578 |
| [`debug_widget.py`](debug_widget.py) | 调试页（请求生成灵痕） | 46 |
| [`tray_controller.py`](tray_controller.py) | 系统托盘 | 90 |
| [`pet_renderer.py`](pet_renderer.py) | 桌宠绘制器 | 311 |
| [`render_pose.py`](render_pose.py) | 姿态模型 + `PoseBuilder` | 578 |
| `TRAY.md` | 托盘模块的设计说明 | — |

---

## 架构层级

```
FluentWindow (MainWindow)
├── home_page            (Hero + 主题 ComboBox + 重启/退出 action card)
├── realtime_page        (展示 / 设置目标点 / 睡觉 action card)
├── growth_page          (PetGrowthWidget)
│   ├── attributes_page  (PetAttributesPage: summary_page / detail_page)
│   └── equipment_page   (SpiritMarkEquipmentPage: overview_page / slot_page)
├── inventory_page       (InventoryWidget)
├── debug_page           (DebugWidget)
├── placeholder 全自动 / 辅助操控 / 通知
└── settings_page        (ConfigEditorWidget，按需懒加载)
```

桌宠主窗口独立于 `MainWindow`：

```
SpriteWindow (QWidget, 桌宠本体)
├── PetRenderer
├── PoseBuilder
├── DebugOverlayWindow       (可选, debug_draw=True)
└── ShowOverlayWindow        (由 AppRuntime 后置挂上)

ShowOverlayWindow (QWidget, 全屏半透明遮罩)
TargetSelectorOverlay (QWidget, 全屏选点浮层)
TrayController (QSystemTrayIcon)
```

---

## 主题安全 API 用法

qfluentwidgets 在 `themeChanged` 时会对注册过的 label 调 `widget.setStyleSheet(...)`，**覆盖** `setStyleSheet` 设的字色/字重。因此本层 **禁止** 用 `setStyleSheet("color: ...; font-weight: ...")` 写颜色或粗体。

| 文件 | 走 `setTextColor` / `QFont`（推荐） | 走 `setStyleSheet`（仅限与主题色无关的属性） |
| --- | --- | --- |
| [`growth_widget.py`](growth_widget.py) | `label.setTextColor(QColor("#2e7d32"), QColor("#7ddc5c"))`（加成值亮/暗色）；`QFont.DemiBold` 应用于 `_category_label` | `SpiritMarkOverviewSlotCard` 用 `setStyleSheet("background: transparent; border: none;")`（去 Card 默认外观） |
| [`inventory_widget.py`](inventory_widget.py) | `BodyLabel / SubtitleLabel / CaptionLabel` 自身主题色 | `quantity_label.setStyleSheet("background: rgba(0,0,0,180); border-radius: 8px; padding: 2px 6px;")`（徽标深色背景）；选中描边 `QColor("#60cdff")`（硬编码强调色） |
| [`main_window.py`](main_window.py) | `setTheme(Theme.DARK / LIGHT / AUTO)` 在构造期 + 主题切换时调用 | 不使用 |
| `sprite_window.py` / `show_overlay.py` / `target_selector.py` / `debug_widget.py` / `tray_controller.py` / `pet_renderer.py` / `render_pose.py` | 主题不适用（自绘） | `target_selector` 旗子用 `QColor(170,20,20)` 系列硬编码强调色；`tray_controller` 走 `FluentIcon` |

`growth_widget.py` 的代码注释记录了本层颜色/字重的选型原则：qfluentwidgets 主题切换时调 `widget.setStyleSheet(...)` 会覆盖 label 上的字色与字重，而 `QFont` 属于 widget property 不受影响。

---

## 每个文件详细说明

### [`main_window.py`](main_window.py) — 主窗口

```python
class MainWindow(FluentWindow):
    def __init__(
        self,
        config_path, on_set_target, on_show, on_sleep=None,
        user_config_path=None, on_restart=None, on_apply_config=None, on_quit=None,
        inventory_snapshot=None, spirit_mark_inventory=None,
        pet_attribute_sheet=None, on_spirit_marks_changed=None,
        on_debug_request_spirit_mark=None, parent=None,
    ) -> None
```

- 关键属性：`config_path`, `user_config_path`, `ui_state_path`（位于 `config_path.parent / USER_CONFIG_DIRNAME / UI_STATE_FILENAME`，即 `config/user/ui_state.json`），`theme_combo`, `config_editor`, `settings_layout`, `home_page / realtime_page / growth_page / inventory_page / debug_page / settings_page`, `_saved_geometry`。
- 公开方法：`show_settings()`, `open_home()`, `update_inventory_and_spirit_marks(snapshot, marks)`。
- 生命周期：`closeEvent` 不退出，仅 `hide()`；`_save_window_geometry` 写入 base64；`_load_saved_geometry` 读回。
- 主题机制：`_THEME_OPTIONS = (("深色", Theme.DARK), ("浅色", Theme.LIGHT), ("跟随系统", Theme.AUTO))`；`setTheme(self._current_theme)` 在子控件创建前调用；切换时写 `ui_state.json["theme"]`。
- 导航装配（`_add_interfaces`）：9 个子页面按 `FluentIcon + 标题 + NavigationItemPosition` 注册：
  1. 启动（PLAY）
  2. 实时触发（SYNC）— 含展示 / 设置目标点 / 睡觉 三个动作卡片
  3. 养成（CHECKBOX）— `PetGrowthWidget`
  4. 背包（SHOPPING_CART）— `InventoryWidget`
  5. 全自动（ROBOT）— 占位
  6. 辅助操控（GAME）— 占位
  7. 调试（SPEED_HIGH）— `DebugWidget`
  8. 通知（RINGER）— 占位
  9. 设置（SETTING，BOTTOM）— 首次 `_ensure_config_editor()` 时延迟挂载 `ConfigEditorWidget`

#### 信号/槽（关键）

- `theme_combo.currentTextChanged → self._on_theme_changed → setTheme(theme) + _save_theme(theme)`
- `config_editor.dirtyChanged(bool) → self._set_config_actions_enabled`（控制保存/撤销按钮 enabled）
- `restore_defaults_button.clicked → _restore_default_config`（成功则回调 `on_apply_config`）
- `save_apply_button.clicked → _save_and_apply_config`（内部 `config_editor.save() + on_apply_config`）
- `undo_button.clicked → _undo_config_changes`
- 每个 action card 按钮 `.clicked → callback`（`on_show` / `on_set_target` / `on_sleep` / `on_restart` / `on_quit`）

### [`sprite_window.py`](sprite_window.py) — 桌宠主窗口 + 调试覆盖窗

#### `SpriteWindow(QWidget)`

- 构造：`__init__(character: DesktopCharacter, config: AppConfig)`。
- 窗口标志：`FramelessWindowHint | Tool`，按 `config.app.always_on_top` 加 `WindowStaysOnTopHint`；属性 `WA_TranslucentBackground`，`setMouseTracking(True)`。
- 持有 `PetRenderer`、`PoseBuilder`、可选 `DebugOverlayWindow`、`show_overlay: ShowOverlayWindow | None`（由 `AppRuntime` 后置挂上）。
- `QTimer`：`timer.timeout → _tick`，周期 `max(1000/fps, 1)` ms。
- 公开方法：
  - `apply_config(config: AppConfig)`：重建 `PoseBuilder`、更新 timer 周期、刷新置顶标志、按需创建/销毁/同步 `debug_overlay`，并 `self.show()` 重新生效。
- `_tick()`：节流到 0.05s、推进 `character.tick(dt)`、按 `render_state` 调整大小/位置、`update()`、SHOW 模式 `raise_()`、驱动 `show_overlay.sync()` 与 `debug_overlay.sync_to_snapshot()`。
- `paintEvent`：调 `PoseBuilder.build` → 旧状态混合（`previous_pose.blend(pose, blend_alpha)`）→ `PetRenderer.draw_pose`；`debug_draw` 时画 2px 红色虚线窗口边界。
- 鼠标交互：`mousePressEvent` / `mouseMoveEvent` / `mouseReleaseEvent` 实现左键拖拽（写入 `character.start_drag/drag_to/release_drag`）；`mouseDoubleClickEvent` 调 `character.poke()`。
- `closeEvent` 同步关闭 `debug_overlay`。

#### `DebugOverlayWindow(QWidget)`（同文件）

- 构造：`__init__(character, config)`。标志：`FramelessWindowHint | Tool | WindowDoesNotAcceptFocus | WindowTransparentForInput`，按需 `WindowStaysOnTopHint`；属性：`WA_TranslucentBackground`, `WA_TransparentForMouseEvents`, `WA_ShowWithoutActivating`。
- 公开方法：
  - `apply_config(config)`：更新置顶标志并 `show()`。
  - `sync_to_snapshot()`：以 `debug_state.snapshot.screen_rect` 同步 `setGeometry` 与 `update()`。
  - `paintEvent`：用 `screen_rect` 做 `painter.translate`，依次画导航地图 / surface graph / 碰撞箱 / 完整路径 / 调试文本。
- 内部工具：`_draw_navigation_map`（屏幕 + work-area 虚线 + 所有 platform）、`_draw_platform`（walkable 蓝、climbable 绿、其它灰）、`_draw_node_marker / _draw_climb_marker`、`_draw_surface_graph`（点状连线 + 箭头）、`_draw_collision_box`、`_draw_complete_path`（当前边实线、非当前虚线、终点圆 + 标签）、`_draw_path_labels`、`_draw_debug_info`（Consolas 8pt 圆角白底文本框）、`_debug_lines`（附带 `scale=` 由 `utils.dpi.qt_primary_screen_scale()` 提供）。

### [`show_overlay.py`](show_overlay.py) — Show 模式全屏遮罩

- 模块常量：`SHOW_TITLE = "苍翼裁决者"`。
- `ShowOverlayWindow(QWidget)`：
  - 构造：`__init__(character)`；标志 `FramelessWindowHint | Tool | WindowStaysOnTopHint | WindowDoesNotAcceptFocus | WindowTransparentForInput`；属性 `WA_TranslucentBackground / WA_TransparentForMouseEvents / WA_ShowWithoutActivating`。
  - 公开方法：
    - `start()`：调用 `_sync_geometry` 后 `show() + raise_()`。
    - `stop()`：`hide()`。
    - `sync()`：由 `SpriteWindow._tick` 每帧驱动；若 `debug.mode != PetMode.SHOW` 自动 `hide()`；否则刷新几何并 `update()`。
  - `_sync_geometry`：取 `debug_state.snapshot.screen_rect` 设置 `setGeometry`。
  - `paintEvent`：仅 SHOW 阶段画 `QColor(0,0,0,170)` 半透明遮罩 + `phase == SHOW_TITLE` 时画 128pt Microsoft YaHei Bold 居中标题。

### [`target_selector.py`](target_selector.py) — 目标点选择器

```python
@dataclass(frozen=True, slots=True)
class TargetCandidate:
    platform: Platform
    anchor_t: float
    flag_x: float
    flag_y: float

def select_target_candidate(
    snapshot, cursor_x, cursor_y, pet_width, search_down_distance, search_up_distance,
) -> TargetCandidate | None

class TargetSelectorOverlay(QWidget):
    def __init__(self, character, config) -> None
    def start() / apply_config(config) / stop()
```

- `select_target_candidate`：遍历 `snapshot.platforms`，过滤 `walkable` 且 x 范围覆盖 `cursor_x`、纵向距离在 `[−search_up_distance, search_down_distance]` 内的 platform；计算 `anchor_t = clamp(cursor_x − pet_width/2, anchor_left, anchor_right)`；返回 `|flag_y − cursor_y|` 最小者。
- `TargetSelectorOverlay`：标志 `FramelessWindowHint | Tool | WindowStaysOnTopHint`；`WA_TranslucentBackground`，`setMouseTracking(True)`，`setCursor(CrossCursor)`。
  - `mouseMoveEvent(globalPosition) → _update_candidate`。
  - `mousePressEvent`：左键 `character.set_target_surface_point(candidate.platform.id, candidate.anchor_t)` 成功则 `stop()`；右键直接 `stop()`。
  - `paintEvent`：用 `QColor(0,0,0,1)` 全屏填底（亚透明），`candidate is not None` 时画红杆（28px 高）+ 红旗（三角）+ 红点（6px 椭圆）。

### [`growth_widget.py`](growth_widget.py) — 养成页

模块常量：

- `ATTRIBUTE_CATEGORY_TITLES = {"basic": "基础属性", "visual": "视觉呈现", "special": "特殊能力"}`
- `SUMMARY_ATTRIBUTE_CATEGORY = "basic"`
- `ATTRIBUTE_ICONS`：13 个属性 id → `FluentIcon` 映射

#### `PetGrowthWidget(QWidget)`

- 构造：`__init__(inventory_snapshot, spirit_mark_inventory, pet_attribute_sheet=None, on_spirit_marks_changed=None, parent=None)`。
- 主体：`QVBoxLayout` → `TitleLabel("桌宠养成")` → `SegmentedWidget`（`attributes` / `spiritMarks` 段）→ `QStackedWidget` 装两个子页。
- 公开方法：
  - `set_data(inventory_snapshot, spirit_mark_inventory)`：刷新两个子页。
  - `select_section` 由 `SegmentedWidget.currentItemChanged` 触发。
- 内部：`_handle_spirit_marks_changed` 重新构造 `attribute_sheet.with_modifiers(spirit_mark_inventory.attribute_modifiers())` 并上抛回调。

#### `PetAttributesPage(QWidget)`

- 构造：`__init__(attribute_sheet, parent=None)`；左右两栏：
  - 左：`CardWidget("petAttributePreviewCard")`（占位 `TitleLabel("桌宠形象") + BodyLabel("预留展示区")`）。
  - 右：`QStackedWidget`，装入 `_create_summary_page` 与 `_create_detail_page`。
- 公开方法：
  - `set_sheet(attribute_sheet)`：清空 `summary_layout` / `detail_layout` 重新构造 summary / detail 行，结尾 `addStretch(1)` 并 `_refresh_values()`。
  - `show_summary() / show_details()`：切 `QStackedWidget` 当前页。
- 行构造：
  - `_summary_row`：`IconWidget` + `BodyLabel(name)` + 右对齐 `BodyLabel(value)`，存入 `_summary_value_labels`。
  - `_detail_row`：图标 + 名 + 基础值 + 加成值 + `IconWidget(FIF.QUESTION)` 配 `ToolTipFilter`（300ms, TOP），hint 文本为 `definition.role + mapped_content`。
- **主题安全点**：
  - `_category_label` 加粗用 `QFont.DemiBold` 而非 `setStyleSheet("font-weight:...")`。
  - `_detail_number_label`：加成值用 `label.setTextColor(QColor("#2e7d32"), QColor("#7ddc5c"))` 设置主题感知颜色；基础值走 `BodyLabel` 自带主题色。

#### `SpiritMarkEquipmentPage(QWidget)`

- 构造：`__init__(inventory_snapshot, spirit_mark_inventory, on_spirit_marks_changed=None, parent=None)`。
- 主体：`QStackedWidget` 装两个子页 `overview_page`（5 个槽位卡 + 摘要 + 套装状态）和 `slot_page`（左侧 `SegmentedWidget` 槽位导航 + 候选 grid；右侧 `InventoryDetailsCard` + `PrimaryPushButton` 装备/卸下/替换）。
- 公开方法：
  - `set_data(...)`：刷新内部索引、丢失选中时回退到第一个候选。
  - `open_slot(slot_id)` / `show_overview()`。
  - `equip_selected() / unequip_selected()`：修改 `spirit_mark_inventory` 并 `_commit_changes`（回调 + refresh）。
  - `select_entry(entry_id)`：更新候选卡选中态、刷新详情与按钮文案。

#### `SpiritMarkOverviewSlotCard(CardWidget)`

- 信号：`slotClicked = Signal(str)`（`slot_id`）。
- 构造：`__init__(slot_id, parent=None)`；`setStyleSheet("background: transparent; border: none;")`（去 Card 背景，**与主题色无关**）。
- `show_mark(mark, definition)`：从 definition 读图片，用 `_load_pixmap` 加载。
- `mouseReleaseEvent`：左键 `emit(self.slot_id)`。

复用依赖：从 [`inventory_widget.py`](inventory_widget.py) 引入 `DraggableSmoothScrollArea / InventoryDetailsCard / InventoryItemCard / _load_pixmap`。

### [`inventory_widget.py`](inventory_widget.py) — 背包页 + 通用卡片

模块常量：`ITEM_CARD_MIN_SIZE=80`、`ITEM_CARD_MAX_SIZE=112`、`GRID_SPACING=10`、`ITEM_CARD_MARGIN=8`、`GRID_RESIZE_DEBOUNCE_MS=60`。

#### `DraggableSmoothScrollArea(SmoothScrollArea)`

- 自定义：除 qfluentwidgets 平滑滚动外，按住左键拖动视口；阈值走 `QApplication.startDragDistance()`。
- `setWidget`：递归 `_watch_tree` 给所有子控件 `installEventFilter(self)`，新加的子控件通过 `QEvent.ChildAdded` 同步挂监听。
- `eventFilter` 处理 `MouseButtonPress / MouseMove / MouseButtonRelease`，命中 `_is_scroll_surface(viewport | content | content 后代)` 时接管滚动并 `event.accept()`。

#### `InventoryItemCard(CardWidget)`

- 信号：`entryClicked = Signal(str)`（`entry.entry_id`）。
- 构造：`__init__(entry, definition, parent=None, edge=ITEM_CARD_MAX_SIZE)`。
- 布局：竖排 image_container（`QGridLayout` 装 `image_label` + 右下角 `quantity_label`，背景 `setStyleSheet("background: rgba(0,0,0,180); border-radius: 8px; padding: 2px 6px;")`，仅用于徽标背景）。
- 公开方法：
  - `set_card_size(edge)`：固定 `setFixedSize(edge, edge)` 并重载 `image_label` 的 pixmap。
  - `set_selected(selected)`：置位后 `update()`。
- `mouseReleaseEvent`：左键 `emit(entry.entry_id)`。
- `paintEvent`（追加）：选中态额外画 `QColor("#60cdff")` 2px 圆角描边。

#### `InventoryDetailsCard(CardWidget)`

- 构造：宽 236–300 之间的 `CardWidget`；内容是 `DraggableSmoothScrollArea` + `image_label`（220 高）+ `name_label` (`SubtitleLabel`) + `category_label` (`CaptionLabel`) + `description_label` (`BodyLabel`) + 动态 `details_layout`。
- 公开方法：
  - `show_entry(entry, definition, category, details)`：填图、名称、分类、描述，逐行 `BodyLabel(f"{key}：{value}")` 写入 details。
  - `clear()`：清空所有 label 与动态 detail。
- 内部 `_clear_details()` 负责删除 details 子行。

#### `InventoryWidget(QWidget)`

- 构造：`__init__(snapshot, parent=None)`。
- 主体：`QVBoxLayout` → `TitleLabel("背包")` → `SegmentedWidget`（按 `snapshot.categories` 顺序加项）→ 下方 `QHBoxLayout` 装 `grid_area`（含 `DraggableSmoothScrollArea` + `QGridLayout`）和 `InventoryDetailsCard`。
- 关键状态：`current_category_id`、`selected_entry_id`、`cards`、`_entries_by_id`、`_categories_by_id`、`_cards_by_category`（按 category 缓存的 `InventoryItemCard` 列表）。
- 公开方法：
  - `set_snapshot(snapshot)`：尽量保留之前的 category / entry 选择；类别/条目不匹配时回退到首个类别。
  - `select_category(category_id)` / `select_entry(entry_id)`。
- 内部：
  - `eventFilter` 监听 `QEvent.Resize` → 触发 `_grid_rebuild_timer`（60ms 防抖）→ `_rebuild_grid`。
  - `_replace_cards(entries)`：停 timer → 隐藏旧卡 → 从 `_cards_by_category` 取/构造 `InventoryItemCard` → `_rebuild_grid`。
  - `_rebuild_grid`：重算 `_grid_metrics`（列数 + 卡片边长，列数最多使卡片 ≥ 80px），列数变化时重排 grid，列数不变时只调 `set_card_size`。
  - `_grid_metrics`：用 `viewport_width / (ITEM_CARD_MAX_SIZE + GRID_SPACING)` 上取整得到列数，再反向求 `card_size` 并夹在 [80, 112]。
  - `_discard_cached_cards()`：清空所有缓存 `InventoryItemCard`（用于 `set_snapshot` 整体替换）。

#### 模块级辅助

- `_load_pixmap(path, size) -> QPixmap`：转字符串后调 `_load_scaled_pixmap`。
- `@lru_cache(maxsize=256) _load_scaled_pixmap(path, w, h) -> QPixmap`：从 `_load_source_pixmap` 取原图并 `KeepAspectRatio + SmoothTransformation` 缩放。
- `@lru_cache(maxsize=32) _load_source_pixmap(path) -> QPixmap`：直接 `QPixmap(path)`。

### [`config_editor.py`](config_editor.py) — 设置页（配置树编辑器）

模块常量：

- `JsonPath = tuple[str, ...]`
- `UI_STATE_FILENAME = "ui_state.json"`
- `USER_CONFIG_DIRNAME = "user"`（在 [`main_window.py`](main_window.py) 中通过此名定位 `ui_state.json`）

私有 dataclass：`_Document(slots=True)`：`label`、`path: Path`、`data: dict`、`saved_data: dict`。

#### `ConfigEditorWidget(QWidget)`

- 信号：`dirtyChanged = Signal(bool)`。
- 构造：`__init__(config_path, user_config_path=None, parent=None)`；可容错地把第二个 `QWidget` 形参当作 `parent`。
- 主体：`QVBoxLayout` → 提示 `BodyLabel` → `SmoothScrollArea` 装 `content_layout`。
- 公开方法：
  - `reload()`：重新读盘 + 重建树 + `_set_dirty(False)`。
  - `save() -> bool`：无 `user_config_path` 时把每个 `_Document` 各自写回 `document.path`；否则只写一份合并后的 `user_config_path`。`TypeError` / `OSError` 弹 `QMessageBox.critical`。
  - `restore_defaults() -> bool`：若 `user_config_path` 存在则 `unlink` 后重新 `_load_documents` + 重建树。
  - `undo_changes()`：把每个 `document.data` 还原为 `document.saved_data`（深拷贝），并 `_reset_document_editors` 把所有编辑器恢复。
  - `is_dirty`（property）。
- 加载流程（`_load_documents`）：
  1. 读 `config_path` 得到 `root_data`。
  2. 若 `user_config_path` 存在，读出 `user_data`，先用 `root_data` 的键过滤 `user_data`（`if key in document_data`），merge 进 `root_data`。
  3. 构造 `_Document("default", config_path, root_data, deepcopy(root_data))`。
  4. 遍历 `root_data["character"]["profile_files"]`（若为 dict），每个相对路径解析后 `_load_json_object`，追加为 `_Document`。
  5. 最后再调用 `_apply_user_config` 把 `user_data`（再次以根级键匹配的方式过滤后 merge）应用到所有 `_Document`；并把每个 `document.saved_data` 同步成 `document.data` 的深拷贝。
- UI 状态：`_load_or_create_ui_state` 维护 `ui_state.json["settings"]["expanded"]`，缺失/多余键分别补齐/清理，必要时写回。`_set_section_expanded(key, expanded)` 单点更新。
- 树渲染（`_build_tree`）：先画 `default` 根，再画 `characters` 段（每个角色档一个子段）。`_add_config_node` 递归：值是 dict → 递归；值是叶子 → `_create_value_row`。
- 编辑器工厂（`_create_value_editor`）：
  - `bool` → `SwitchButton`。
  - `int` → `_NoWheelSpinBox`（`SpinBox` 子类，吃掉 `wheelEvent`）。
  - `float` → `_NoWheelDoubleSpinBox`（`DoubleSpinBox` 子类，同上）。
  - `str` → `LineEdit`。
  - 其它 → `PlainTextEdit` + 450ms `QTimer` 防抖 → 调 `_commit_json_text`（解析失败静默）。
- dirty 机制：每个编辑器在 setter 注册到 `_value_setters` 与 `_value_widgets`；`_update_value` 写回 `document.data` 并 `_set_dirty(self._has_unsaved_changes())`；`_has_unsaved_changes` 逐 doc 比较 `data != saved_data`。

#### 私有类

- `_ConfigGroupCard(SimpleExpandGroupSettingCard)`：
  - 信号：`expandChanged = Signal(bool)`、`heightChanged = Signal()`。
  - `setExpand` 包装父类，变化时 `expandChanged.emit`；`addGroupWidget` 对子组 `heightChanged` 接线 `_adjustViewSize`；`_onExpandValueChanged / _adjustViewSize` 转发 `heightChanged`。
- `_ValueSettingCard(SettingCard)`：包一个 `editor: QWidget`，左缩进 `16 + indent*18`；`paintEvent = pass`。
- `_NoWheelSpinBox(SpinBox)` / `_NoWheelDoubleSpinBox(DoubleSpinBox)`：禁用按钮并 `wheelEvent.ignore()`，避免误触。

模块私有：`_merge_dict(target, source)`（与 `utils.config` 中同名函数逻辑相同，递归浅 merge，非 dict 覆盖）。

### [`debug_widget.py`](debug_widget.py) — 调试页

```python
class DebugWidget(QWidget):
    def __init__(self, on_request_spirit_mark=None, parent=None)
    def request_spirit_mark()  # 捕获 on_request_spirit_mark() 的异常并写入 status_label
```

垂直布局：`TitleLabel("调试")` + `_spirit_mark_card`（`SubtitleLabel("请求生成灵痕")` + `BodyLabel` 状态 + `PrimaryPushButton(FIF.ADD, "生成")`）。

### [`tray_controller.py`](tray_controller.py) — 系统托盘

```python
class TrayController:
    def __init__(self, window, on_set_target=None, on_show=None, on_open_window=None, owner=None)
    def show()            # 若 QSystemTrayIcon.isSystemTrayAvailable() 为假，记录 warning 后直接 return
    def set_window(window)
    def quit()            # 隐藏 tray → 关闭主窗 → QApplication.quit()
```

- 内部：`self.tray = QSystemTrayIcon(self._create_icon(), self.owner)`、`setContextMenu(self.menu)`、`tray.activated → _on_activated`。
- 菜单（`_create_menu`）：按 `on_show / on_set_target` 是否提供决定显示项；提供目标点时插入分隔符；必有 `退出` 项（图标 `FIF.POWER_BUTTON`）。
- 托盘激活（`_on_activated`）：`Trigger` 或 `DoubleClick` → `on_open_window()`。
- 图标（`_create_icon`）：32×32 透明画布，`QPainter` 画绿色椭圆 + 两个点（眼睛）+ 弧形（嘴）。

### [`pet_renderer.py`](pet_renderer.py) — 桌宠绘制器

```python
class PetRenderer:
    def draw_pose(self, painter: QPainter, pose: RenderPose, width: int, height: int) -> None
```

- 流程：`save()` → `translate(width/2 + offset.x, height/2 + offset.y)` → 若 `pose.facing == "left"` 则 `scale(-1, 1)` → `rotate(pose.rotation)` → `translate(-width/2, -height/2)`。
- 绘制顺序：`_draw_shadow → _draw_wings → _draw_limbs → _draw_body → _draw_scarf → _draw_eyes`，最后 `restore()`。
- 私有绘制：
  - `_draw_shadow`：半透明深色椭圆。
  - `_draw_wings`：当 `pose.wings` 为空或 `opacity <= 0` 直接返回；左右两侧各调 `_draw_feathered_wing(side=-1/+1)`。
  - `_draw_feathered_wing`：算 `span / drop / lift` 与 `wing_alpha` 后调用 `_draw_primary_feathers` + `_draw_secondary_feathers`。
  - `_draw_feather`：用 `base → tip` 的法线生成 5 点多边形 + 一条羽轴 `vein` 直线。
  - `_draw_limb`：圆头笔 (`Qt.PenCapStyle.RoundCap`) 两段折线 + 末端半椭圆。
  - `_draw_body`：三色椭圆（深→中→亮）。
  - `_draw_scarf`：圆角矩形围巾带 + 三角尾巴。
  - `_draw_eyes`：睡眠态画水平线（`drawLine`），否则填充眼 + 高亮椭圆。

### [`render_pose.py`](render_pose.py) — 姿态模型 + 构造器

工具函数：`clamp(value, minimum, maximum)`、`lerp(a, b, t)`。

不可变 dataclass（均 `@dataclass(frozen=True, slots=True)`，支持 `blend` 与 `moved_by`）：

| 类型 | 字段 |
| --- | --- |
| `PosePoint` | `x, y` |
| `PoseRect` | `x, y, width, height` |
| `LimbPose` | `root, joint, end: PosePoint`、`radius, terminal_radius: float` |
| `BodyPose` | `back, front, highlight: PoseRect` |
| `EyePose` | `left, right, left_highlight, right_highlight: PoseRect`、`sleeping: bool=False` |
| `ScarfPose` | `band: PoseRect`、`tail_a, tail_tip, tail_b: PosePoint` |
| `ShadowPose` | `ellipse: PoseRect`、`opacity: int` |
| `WingPose` | `left_root, left_tip, left_lower, right_root, right_tip, right_lower: PosePoint`、`opacity: int`、`openness: float=1.0`、`flap: float=0.0` |
| `RenderPose` | `facing: Facing`、`offset: PosePoint`、`rotation: float`、`body, eyes, scarf, shadow`、`limbs: tuple[LimbPose, LimbPose, LimbPose, LimbPose]`、`wings: WingPose \| None`、`edge_line: tuple \| None`；`blend` 中 `_blend_wings` 处理 wings 出现/消失的混合（用 `t >= 0.5` 选其一） |

#### `PoseBuilder`

- 构造：`__init__(wing_open_seconds=0.7, wing_close_seconds=0.7)`；构造时把两个值 `max(_, 0.001)` 保护；不暴露 setter。
- 公开方法：
  - `build(pet, phase, width, height, state=None, state_elapsed=None, wing_open_seconds=None, wing_close_seconds=None) -> RenderPose`
    - 解决 `state / state_elapsed` 默认值；`cycle = phase * math.tau`；`speed = clamp(|velocity.x|/160, 0, 1.6)`；`fall_strength = clamp(max(velocity.y, 0)/1000, 0, 1.25)`。
    - 构造 `body / offset / rotation / limbs / scarf / eyes / shadow / wings`，`wings` 总是基于 `wing_open_seconds / wing_close_seconds` 解决（参数可覆盖 builder 默认值）。
- 内部函数（节选）：`_is_show_state`（OPEN_WINGS / FLY / HOVER / WING_LAND / CLOSE_WINGS）；`_offset / _rotation / _body / _limbs / _idle_style_limbs / _scarf / _eyes / _shadow` 按 `PetState` 枚举分支；`_wings` 在非 show 状态返回 `None`；OPEN_WINGS 用 `state_elapsed / open_seconds`，CLOSE_WINGS 用 `1 − state_elapsed / close_seconds`，否则固定 1.0；`flap` 走 `_wing_flap`（downstroke 占 0.32，`smoothstep` 在 `up_peak` 与 `down_peak` 之间往返，FLY 状态振幅更大）；`_wing_flap / _smoothstep` 是纯函数工具。

---

## 自定义控件 → Qt 父类与信号清单

| 自定义类 | 父类 | 自定义信号 |
| --- | --- | --- |
| `DraggableSmoothScrollArea` | `qfluentwidgets.SmoothScrollArea` | — |
| `InventoryItemCard` | `qfluentwidgets.CardWidget` | `entryClicked(str)` |
| `InventoryDetailsCard` | `qfluentwidgets.CardWidget` | — |
| `InventoryWidget` | `QWidget` | — |
| `PetGrowthWidget` | `QWidget` | — |
| `PetAttributesPage` | `QWidget` | — |
| `SpiritMarkEquipmentPage` | `QWidget` | — |
| `SpiritMarkOverviewSlotCard` | `qfluentwidgets.CardWidget` | `slotClicked(str)` |
| `ConfigEditorWidget` | `QWidget` | `dirtyChanged(bool)` |
| `_ConfigGroupCard` | `qfluentwidgets.SimpleExpandGroupSettingCard` | `expandChanged(bool)`, `heightChanged()` |
| `_ValueSettingCard` | `qfluentwidgets.SettingCard` | — |
| `_NoWheelSpinBox` | `qfluentwidgets.SpinBox` | — |
| `_NoWheelDoubleSpinBox` | `qfluentwidgets.DoubleSpinBox` | — |
| `DebugWidget` | `QWidget` | — |
| `MainWindow` | `qfluentwidgets.FluentWindow` | — |
| `SpriteWindow` | `QWidget` | — |
| `DebugOverlayWindow` | `QWidget` | — |
| `ShowOverlayWindow` | `QWidget` | — |
| `TargetSelectorOverlay` | `QWidget` | — |
| `PetRenderer` | （普通类，非 QObject） | — |
| `TrayController` | （普通类，非 QObject） | — |
| `PoseBuilder` | （普通类） | — |

---

## 跨包依赖图

```
ui/
├── main_window.py
│     ├── utils.config（仅 USER_CONFIG_DIRNAME / UI_STATE_FILENAME 常量）
│     ├── config_editor / debug_widget / growth_widget / inventory_widget
│     └── models.inventory / models.spirit_mark / models.pet_attribute
│
├── sprite_window.py
│     ├── utils.config, utils.dpi
│     ├── ui.pet_renderer, ui.render_pose, ui.show_overlay
│     ├── core.character, core.pathfinding
│     └── models.platform
│
├── show_overlay.py
│     ├── core.behavior_orchestrator.BehaviorPhaseName
│     ├── core.character
│     └── core.pet_mode.PetMode
│
├── target_selector.py
│     ├── core.character
│     ├── environment.environment_snapshot.EnvironmentSnapshot
│     ├── models.platform
│     └── utils.config
│
├── growth_widget.py
│     ├── models.inventory
│     ├── models.pet_attribute
│     ├── models.spirit_mark
│     └── ui.inventory_widget（复用 DraggableSmoothScrollArea / InventoryDetailsCard
│         / InventoryItemCard / _load_pixmap）
│
├── inventory_widget.py
│     └── models.inventory
│
├── config_editor.py       自包含（仅 qfluentwidgets + Qt）
├── debug_widget.py        自包含
├── tray_controller.py     自包含
├── pet_renderer.py        → ui.render_pose
└── render_pose.py         → models.state（Facing, Pet, PetState）
```
