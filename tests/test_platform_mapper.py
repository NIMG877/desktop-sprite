from desktop_sprite.environment.platform_mapper import PlatformMapper
from desktop_sprite.models.geometry import Rect
from desktop_sprite.models.platform import PlatformType
from desktop_sprite.models.window_info import WindowInfo


def test_maps_window_to_top_and_side_platforms():
    mapper = PlatformMapper(pet_width=80, pet_height=100)
    window = WindowInfo(
        hwnd=123,
        title="Demo",
        rect=Rect.from_xywh(100, 100, 400, 300),
        visible=True,
        minimized=False,
        is_foreground=True,
    )

    platforms = mapper.map_platforms(
        screen_rect=Rect.from_xywh(0, 0, 1000, 800),
        work_area_rect=Rect.from_xywh(0, 0, 1000, 760),
        taskbar_rect=None,
        windows=[window],
    )

    types = {platform.type for platform in platforms}
    assert PlatformType.GROUND in types
    assert PlatformType.WINDOW_TOP in types
    assert PlatformType.WINDOW_LEFT in types
    assert PlatformType.WINDOW_RIGHT in types
    assert any(platform.id == "window:123:top" for platform in platforms)


def test_skips_taskbar_platform_when_it_duplicates_ground():
    mapper = PlatformMapper(pet_width=80, pet_height=100)

    platforms = mapper.map_platforms(
        screen_rect=Rect.from_xywh(0, 0, 1000, 800),
        work_area_rect=Rect.from_xywh(0, 0, 1000, 760),
        taskbar_rect=Rect.from_xywh(0, 760, 1000, 40),
        windows=[],
    )

    assert any(platform.id == "ground:work_area" for platform in platforms)
    assert not any(platform.id == "taskbar:main" for platform in platforms)
