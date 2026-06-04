# Desktop Sprite（桌宠）

一个基于 **PySide6** 与 **PySide6-Fluent-Widgets** 的 Windows 桌面小精灵。桌宠能感知当前桌面环境（屏幕、任务栏、可见窗口），在窗口顶/侧边/任务栏之间寻路移动，可被拖拽、被选中作为目标点，并拥有一套"展翅—飞行—悬停—着陆"的展示动作；管理端使用 Fluent 风格窗口提供启动/重启、养成属性、灵痕装备、背包与配置编辑能力。

---

## 目录

- [项目特性](#项目特性)
- [运行与开发](#运行与开发)
- [整体架构](#整体架构)
- [包结构与对应 README](#包结构与对应-readme)
- [关键设计要点](#关键设计要点)
- [目录结构](#目录结构)
- [测试](#测试)
- [持久化文件一览](#持久化文件一览)
- [参考文档](#参考文档)

---

## 项目特性

- **桌面感知**：通过 Win32 枚举窗口 + Qt 主屏 API 实时构造可踩踏/可攀爬的 `Platform` 列表（地面、任务栏、窗口三边）。
- **寻路与物理**：基于表面图（Surface Graph）的 Dijkstra 寻路，内置抛物跳、爬墙侧抓、动态平台位移补偿、工作区/屏幕边界裁剪。
- **展示序列（Show）**：6 段相位（展翅→飞行→悬停→标题→着陆→收翅）由 `PetShowDirector` 统一驱动。
- **养成属性**：16 项属性按 *基础 / 视觉 / 特殊* 三类组织；灵痕装备以修饰器方式叠加，实时影响运动/体力/精力/饱腹。
- **灵痕系统**：5 个槽位（灵核/形骸/脉络/锋质/余响），含套装两件效果、词条生成、强化/分解/收藏；持久化在 `config/user/`。
- **Fluent 管理窗口**：主页（主题切换 + 启停）、实时触发、养成、背包、调试、设置（配置树编辑）。
- **托盘控制**：右键菜单可触发展示、设目标点、退出；单击/双击打开主窗。
- **可测试性**：`app.py` 内的 17 个模块级符号支持 `monkeypatch.setattr` 注入；状态写入集中在 `PetStateMediator`；`test_pet_controller_climb_reach.py` 通过 `__getattr__` 转发与同名保留方法访问内部状态。

---

## 运行与开发

### 依赖

- Python ≥ 3.10
- PySide6 ≥ 6.7
- PySide6-Fluent-Widgets ≥ 1.11.2
- pytest ≥ 8.0（仅测试）

安装：

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

### 启动

```bash
python -m app
```

主程序入口：[app.py](app.py) 仅一行 `main()`，真实实现位于 [`desktop_sprite/app/`](desktop_sprite/app/)。可选 CLI 参数 `--character <id>` 选择角色档（默认 `pet`）。

### 测试

```bash
pytest -q
```

---

## 整体架构

项目以**分层 + 单向依赖**的方式组织，业务核心（桌宠控制）与界面、配置、平台感知解耦。

```
                          ┌────────────────────────────────┐
                          │  app.py  /  desktop_sprite.app  │  ← 入口
                          └──────────────┬─────────────────┘
                                         │
                          ┌──────────────▼─────────────────┐
                          │          AppRuntime             │  ← 运行时门面
                          └──┬─────┬──────┬──────┬──────┬───┘
                             │     │      │      │      │
              ┌──────────────┘     │      │      │      └──────────────┐
              ▼                    ▼      ▼      ▼                     ▼
   ┌──────────────────┐  ┌──────────────┐  ...  ┌────────────┐  ┌─────────────────┐
   │   core (控制)    │  │  models      │       │ environment │  │  ui (PySide6)   │
   │ PetController    │◄─┤ Pet/State    │       │ Sensors /   │  │ MainWindow/     │
   │ Show/State/Path  │  │ Inventory    │       │ Platform    │  │ SpriteWindow/   │
   │ Physics/Animate  │  │ SpiritMark   │       │ Mapper      │  │ Overlay/...     │
   └─────────┬────────┘  └─────┬────────┘       └─────┬───────┘  └─────────┬───────┘
             │                 │                       │                    │
             └──────────┬──────┴───────────────────────┴────────────────────┘
                        ▼
                  ┌──────────────┐
                  │ utils/config │  ← 配置加载/合并
                  └──────────────┘
```

读法：UI 通过回调向 `AppRuntime` 触发动作；`AppRuntime` 调用 `core` 的 `PetController`；`PetController` 从 `environment` 拉快照、向 `models` 读写灵痕/背包；`utils/config` 提供配置加载；UI 还直接消费 `models` 的快照（养成/背包/灵痕）以渲染。

---

## 包结构与对应 README

| 包 | README | 角色 |
| --- | --- | --- |
| `desktop_sprite.app` | [desktop_sprite/app/README.md](desktop_sprite/app/README.md) | 应用运行时门面（`AppRuntime` + `main()` + 模块级 re-export 符号 + `RuntimePaths`） |
| `desktop_sprite.core` | [desktop_sprite/core/README.md](desktop_sprite/core/README.md) | 桌宠控制核心（`PetController` / `PetStateMediator` / `PetShowDirector` / 物理 / 寻路 / 动画） |
| `desktop_sprite.environment` | [desktop_sprite/environment/README.md](desktop_sprite/environment/README.md) | 桌面环境感知（`EnvironmentSnapshot` / `PlatformMapper` / 三类 Sensor） |
| `desktop_sprite.models` | [desktop_sprite/models/README.md](desktop_sprite/models/README.md) | 不可变数据模型（`Pet` / 16 属性 / 物品 / 灵痕 / 持久化入口） |
| `desktop_sprite.ui` | [desktop_sprite/ui/README.md](desktop_sprite/ui/README.md) | PySide6 + Fluent 界面（`MainWindow` / `SpriteWindow` / 浮层 / 养成 / 背包 / 托盘） |
| `desktop_sprite.utils` | [desktop_sprite/utils/README.md](desktop_sprite/utils/README.md) | 工具与配置（`load_config` / `AppConfig` 树 / DPI / 日志 / Win32 探测） |

每个子包 README 详细列出：文件清单、公开 API（签名+说明）、内部 API、依赖图、字段表、业务规则、可访问入口。**本文档仅做总览与设计要点串联；具体实现请跳转对应 README。**

---

## 关键设计要点

- **`PetStateMediator` 是 `pet.state` 的合法写源**：`PetStateMediator.transition` 同时维护 `Pet.state` ↔ `BehaviorStateMachine.state` ↔ `BehaviorOrchestrator.phase` ↔ `ModeController.mode/locked` 的同步。`PhysicsEngine` 等旁路改 `pet.state` 后须调用 `mediator.snapshot_state()` 让状态机镜像重新对齐。详见 [core/README.md](desktop_sprite/core/README.md)。
- **`PetShowDirector` 集中管理 Show 序列**：6 段相位 + 3 种 `PetAbility`（Wing/Flight/Hover）的生命周期都走 `PetShowDirector.start / update / finish`；`PetController` 暴露同名 `_start_* / _update_*` 方法把这些调用转发到 director。详见 [core/README.md](desktop_sprite/core/README.md)。
- **`AppRuntime` 是运行时门面**：所有长生命周期对象（`QApplication` / 桌宠 / 三个窗口 / 托盘 / 管理窗口 / 灵痕档案）都聚合为 `AppRuntime` 字段；运行时 → UI 通过构造时注入的 `lambda` 回调；`_app_symbols()` 延迟查表让 `tests/test_app.py` 的 17 个 `monkeypatch.setattr` 生效。详见 [app/README.md](desktop_sprite/app/README.md)。
- **qfluentwidgets 主题安全**：自定义颜色/粗体走 `setTextColor(light, dark)` 与 `QFont.setWeight(DemiBold)`，**不**走 `setStyleSheet("color: ...; font-weight: ...;")`。原因：qfluentwidgets 的 `addStyleSheet(register=True)` 路径在每次 `themeChanged` 时**完全覆盖** `widget.styleSheet()`，而 `QFont` / `setTextColor` 存储在 widget property 上不受影响。详见 [ui/README.md](desktop_sprite/ui/README.md) 的"主题安全 API 用法"。
- **frozen + replace 的不可变风格**：所有领域 dataclass 用 `frozen=True, slots=True`；状态变更通过 `dataclasses.replace` 返回新对象，便于回退/撤销/差异测试。详见 [models/README.md](desktop_sprite/models/README.md)。
- **`AppConfig` 加载流程**：默认配置 → 可选用户 `character` 段合并 → `character.profile_files` 指向的角色档合并 → 可选用户顶层合并 → 4 个 motion key（`walk_speed / climb_speed / jump_speed_x / jump_speed_y`）从 `pet` 段并入 `physics` 段 → 构造 `AppConfig`。详见 [utils/README.md](desktop_sprite/utils/README.md)。

---

## 目录结构

```text
DesktopSprite/
├── app.py                              # 入口薄壳
├── README.md                           # ← 本文件
├── requirements.txt
├── pytest.ini
│
├── config/                             # 默认 / 角色 / 用户态配置
│   ├── default.json
│   ├── items.json
│   ├── characters/pet.json
│   └── user/{inventory,spirit_marks,ui_state}.json
│
├── assets/
│   ├── spirit_mark/                    # 灵痕部位图标
│   └── test/                           # 测试物品图标
│
├── desktop_sprite/
│   ├── app/README.md                   # 运行时门面
│   ├── core/README.md                  # 桌宠控制核心
│   ├── environment/README.md           # 桌面环境感知
│   ├── models/README.md                # 不可变数据模型
│   ├── ui/README.md                    # PySide6 + Fluent 界面
│   └── utils/README.md                 # 工具与配置
│
└── tests/                              # 21 个测试文件
```

---

## 测试

测试根目录 `tests/`，21 个文件覆盖装配、配置、UI、几何、物理、寻路、灵痕、状态机等关键模块。`pytest.ini` 设置 `pythonpath = .` 与 `testpaths = tests`，运行：

```bash
pytest -q
```

主要测试文件清单与各包对应关系：

| 测试 | 覆盖范围 |
| --- | --- |
| `test_app.py` | 通过 `monkeypatch.setattr(desktop_sprite.app, "<NAME>", ...)` 注入 17 个模块级符号（[app/README.md](desktop_sprite/app/README.md)） |
| `test_pet_controller_climb_reach.py` | 730 行，通过 `PetController.__new__` 跳过 `__init__`、直接读写 15+ 私有成员（[core/README.md](desktop_sprite/core/README.md) 的"`__getattr__` 转发 / Show 兼容方法"） |
| `test_mode_and_orchestrator.py` | `BehaviorOrchestrator` facade 的相位/序列 API |
| `test_state_machine.py` | 纯状态机转移表 |
| `test_physics.py` / `test_pathfinding.py` / `test_platform_mapper.py` / `test_screen_boundary.py` | 环境/物理/寻路（[environment/README.md](desktop_sprite/environment/README.md)） |
| `test_growth_widget.py` | 养成 + 灵痕装备 UI |
| `test_main_window.py` | 主窗构造、主题切换、状态持久化 |
| `test_config_editor.py` | JSON 树编辑与未保存高亮 |
| `test_inventory.py` / `test_inventory_widget.py` | 背包模型与视图 |
| `test_spirit_mark.py` / `test_spirit_mark_service.py` | 灵痕模型 + 授予服务 |
| `test_pet_attribute.py` | 属性表与修饰器 |
| `test_pet_renderer.py` / `test_pose_builder.py` | 渲染 |
| `test_geometry.py` | 几何原语 |
| `test_target_selector.py` / `test_debug_widget.py` | 浮层与调试 |

`test_pet_controller_climb_reach.py` 依赖 `PetController` 内的多个 `_*` 私有方法（`_update_behavior / _execute_path_plan / _walk_toward_x / _start_open_wings / _start_hover / _update_show / _update_pet_ability / _maybe_grab_climb_side_while_jumping / _keep_walking_on_platform / _validate_path_plan / _advance_path_if_reached / _start_random_wander / _active_pet_ability / _show_context / _state_goal_until / _landed_on_platform_last_tick / _auto_sleeping / _resource_resting`）以及从 `desktop_sprite.core.pet_controller` 导入的 `HoverAbility / WingAbility / SHOW_HOVER_SECONDS`。`PetController` 通过 `__getattr__` 转发与同名保留方法支持这些访问。详见 [core/README.md](desktop_sprite/core/README.md) 末尾"`__getattr__` 转发 / Show 兼容方法"。

---

## 持久化文件一览

| 路径 | 用途 | 写入者 | 详见 |
| --- | --- | --- | --- |
| `config/user/ui_state.json` | 主题（display label）+ 主窗 geometry（base64）+ ConfigEditor 折叠节点 | `MainWindow` | [ui/README.md](desktop_sprite/ui/README.md) |
| `config/user/inventory.json` | 背包条目（`entry_id ↔ item_id` 索引） | `inventory.append_inventory_entry`、`spirit_mark_service.grant_spirit_mark` | [models/README.md](desktop_sprite/models/README.md) |
| `config/user/spirit_marks.json` | 灵痕实例（套装/部位/主词条/副词条/等级/收藏/来源） | `spirit_mark.save_spirit_mark_inventory`、`spirit_mark_service.grant_spirit_mark` | [models/README.md](desktop_sprite/models/README.md) |
| `config/default.json` | 默认配置（只读） | — | [utils/README.md](desktop_sprite/utils/README.md) |
| `config/items.json` | 物品目录（只读） | — | [models/README.md](desktop_sprite/models/README.md) |
| `config/characters/pet.json` | 角色档（只读，启动时合并） | — | [utils/README.md](desktop_sprite/utils/README.md) |

