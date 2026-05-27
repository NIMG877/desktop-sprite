# 托盘退出功能

当前版本在系统托盘中加入了桌宠控制入口。启动桌宠后，Windows 托盘区域会出现一个 Desktop Sprite 图标，右键图标可以打开菜单，并通过 `退出` 关闭程序。

## 功能范围

v1 只提供退出能力：

- 显示系统托盘图标
- 右键打开托盘菜单
- 点击 `退出` 后关闭桌宠窗口并退出应用

暂不包含显示/隐藏、暂停动作、置顶切换、调试绘制开关或设置窗口。

## 实现结构

托盘逻辑集中在 `desktop_sprite/ui/tray_controller.py` 中，入口文件 `desktop_sprite/app.py` 只负责创建和持有 `TrayController`。

`TrayController` 使用 PySide6 原生组件实现：

- `QSystemTrayIcon`：显示系统托盘图标
- `QMenu`：提供右键菜单
- `QAction`：提供 `退出` 菜单项
- `QPixmap` 和 `QIcon`：运行时生成托盘图标，避免额外图片资源依赖

退出时会先隐藏托盘图标，再关闭桌宠窗口，最后调用 `QApplication.quit()`。桌宠窗口原有的 `closeEvent()` 会继续负责关闭调试覆盖层。

## 后续扩展

托盘控制器可以继续扩展常用操作，例如：

- 显示/隐藏桌宠
- 暂停/恢复动作
- 置顶开关
- 调试绘制开关
- 打开设置窗口

这些功能建议继续放在 `TrayController` 或独立设置控制器中，由托盘菜单调用桌宠窗口或配置服务暴露的方法，避免把托盘菜单逻辑写进 `SpriteWindow`。
