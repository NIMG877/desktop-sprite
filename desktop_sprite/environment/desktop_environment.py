from __future__ import annotations

import time

from desktop_sprite.environment.environment_snapshot import EnvironmentSnapshot
from desktop_sprite.environment.platform_mapper import PlatformMapper
from desktop_sprite.environment.screen_sensor import ScreenSensor
from desktop_sprite.environment.taskbar_sensor import TaskbarSensor
from desktop_sprite.environment.window_sensor import WindowSensor


class DesktopEnvironment:
    def __init__(self, pet_width: int, pet_height: int) -> None:
        self.screen_sensor = ScreenSensor()
        self.taskbar_sensor = TaskbarSensor()
        self.window_sensor = WindowSensor()
        self.platform_mapper = PlatformMapper(pet_width, pet_height)

    def set_own_window_handle(self, hwnd: int | None) -> None:
        self.window_sensor.set_own_window_handle(hwnd)

    def snapshot(self) -> EnvironmentSnapshot:
        screen_rect = self.screen_sensor.get_screen_rect()
        work_area_rect = self.screen_sensor.get_work_area_rect()
        taskbar_rect = self.taskbar_sensor.get_taskbar_rect()
        windows = self.window_sensor.get_windows()
        platforms = self.platform_mapper.map_platforms(
            screen_rect=screen_rect,
            work_area_rect=work_area_rect,
            taskbar_rect=taskbar_rect,
            windows=windows,
        )
        return EnvironmentSnapshot(
            screen_rect=screen_rect,
            work_area_rect=work_area_rect,
            taskbar_rect=taskbar_rect,
            windows=windows,
            platforms=platforms,
            timestamp=time.monotonic(),
        )
