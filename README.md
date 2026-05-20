# Desktop Sprite MVP

Windows 桌面小精灵 MVP。当前版本实现了计划中的第一阶段闭环：

- 透明、无边框、置顶的小精灵窗口
- 默认代码绘制动画，无需额外图片资源即可运行
- `idle`、`walk`、`climb`、`fall`、`dragged` 状态
- 鼠标拖拽、松手后按拖拽速度投掷并受重力影响
- 获取主屏幕、工作区、任务栏和前台/可见窗口位置
- 将窗口顶部映射为可站立平台，窗口左右边映射为可攀爬墙
- 小精灵会靠近前台窗口、爬上窗口边缘，并在窗口顶部行走
- 所站窗口移动时跟随，窗口消失或最小化时掉落
- 配置文件控制帧率、速度、重力和调试绘制

## 运行

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python app.py
```

也可以直接：

```powershell
python app.py
```

前提是当前 Python 环境已安装 `PySide6`。

## 停止

在启动程序的 PowerShell/终端里按 `Ctrl+C`。如果是从 IDE 运行，使用 IDE 的停止按钮。

## 配置

默认配置在 `config/default.json`。常用项：

- `app.debug_draw`: 显示碰撞框、状态和速度
- `app.environment_refresh_hz`: 环境感知刷新频率
- `physics.gravity`: 重力
- `physics.walk_speed`: 行走速度
- `physics.climb_speed`: 攀爬速度

## 测试

```powershell
pytest
```

测试覆盖几何计算、窗口平台映射、状态机和基础物理落地逻辑。
