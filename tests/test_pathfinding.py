from desktop_sprite.core.pathfinding import PathAction, PathFinder
from desktop_sprite.core.stamina_system import StaminaSystem
from desktop_sprite.environment.environment_snapshot import EnvironmentSnapshot
from desktop_sprite.models.geometry import Rect, Vec2
from desktop_sprite.models.platform import Platform, PlatformType
from desktop_sprite.models.state import Pet
from desktop_sprite.utils.config import load_config


def platform(id_: str, type_: PlatformType, rect: Rect, *, source_id: int | None = None) -> Platform:
    return Platform(
        id=id_,
        type=type_,
        rect=rect,
        walkable=type_ in {PlatformType.GROUND, PlatformType.TASKBAR, PlatformType.WINDOW_TOP},
        climbable=type_ in {PlatformType.WINDOW_LEFT, PlatformType.WINDOW_RIGHT},
        dynamic=source_id is not None,
        source_id=source_id,
    )


def window_platforms(hwnd: int, left: float, top: float, right: float, bottom: float) -> list[Platform]:
    return [
        platform(f"window:{hwnd}:top", PlatformType.WINDOW_TOP, Rect(left, top, right, top + 8), source_id=hwnd),
        platform(f"window:{hwnd}:left", PlatformType.WINDOW_LEFT, Rect(left - 8, top, left + 6, bottom), source_id=hwnd),
        platform(f"window:{hwnd}:right", PlatformType.WINDOW_RIGHT, Rect(right - 6, top, right + 8, bottom), source_id=hwnd),
    ]


def make_snapshot(platforms: list[Platform]) -> EnvironmentSnapshot:
    return EnvironmentSnapshot(
        screen_rect=Rect.from_xywh(0, 0, 900, 700),
        work_area_rect=Rect.from_xywh(0, 0, 900, 650),
        taskbar_rect=None,
        windows=[],
        platforms=platforms,
        timestamp=1.0,
    )


def make_pet(stamina_value: float = 100) -> Pet:
    return Pet(
        position=Vec2(100, 546),
        velocity=Vec2(),
        width=84,
        height=104,
        support_platform_id="ground:work_area",
        stamina=stamina_value,
    )


def make_stamina() -> StaminaSystem:
    config = load_config()
    return StaminaSystem(config.stamina, config.physics)


def ground() -> Platform:
    return platform("ground:work_area", PlatformType.GROUND, Rect.from_xywh(0, 650, 900, 4))


def test_low_window_path_climbs_from_ground_to_window_top():
    pet = make_pet()
    snapshot = make_snapshot([ground(), *window_platforms(1, 160, 430, 320, 620)])

    plan = PathFinder().find_path(pet, snapshot, target_window_id=1, stamina=make_stamina())

    assert plan is not None
    assert [edge.action for edge in plan.edges] == [PathAction.CLIMB]
    assert plan.edges[-1].to_platform_id == "window:1:top"


def test_high_window_can_be_reached_through_lower_window():
    pet = make_pet()
    snapshot = make_snapshot(
        [
            ground(),
            *window_platforms(1, 160, 430, 320, 620),
            *window_platforms(2, 340, 300, 520, 500),
        ]
    )

    plan = PathFinder().find_path(pet, snapshot, target_window_id=2, stamina=make_stamina())

    assert plan is not None
    assert len(plan.edges) >= 2
    assert plan.edges[0].to_platform_id == "window:1:top"
    assert plan.edges[-1].to_platform_id == "window:2:top"


def test_gap_between_platforms_generates_jump_edge_when_in_range():
    pet = make_pet()
    target_top = platform("window:2:top", PlatformType.WINDOW_TOP, Rect(360, 430, 520, 438), source_id=2)
    snapshot = make_snapshot([ground(), *window_platforms(1, 160, 430, 320, 620), target_top])

    plan = PathFinder().find_path(pet, snapshot, target_window_id=2, stamina=make_stamina())

    assert plan is not None
    assert any(edge.action == PathAction.JUMP for edge in plan.edges)


def test_gap_beyond_jump_distance_has_no_path():
    pet = make_pet()
    target_top = platform("window:2:top", PlatformType.WINDOW_TOP, Rect(760, 430, 880, 438), source_id=2)
    snapshot = make_snapshot([ground(), *window_platforms(1, 160, 430, 320, 620), target_top])

    plan = PathFinder().find_path(pet, snapshot, target_window_id=2, stamina=make_stamina())

    assert plan is None


def test_high_window_without_intermediate_path_is_unreachable():
    pet = make_pet()
    snapshot = make_snapshot([ground(), *window_platforms(1, 160, 100, 320, 280)])

    plan = PathFinder().find_path(pet, snapshot, target_window_id=1, stamina=make_stamina())

    assert plan is None


def test_low_stamina_blocks_climb_edge():
    pet = make_pet(stamina_value=20)
    snapshot = make_snapshot([ground(), *window_platforms(1, 160, 430, 320, 620)])

    plan = PathFinder().find_path(pet, snapshot, target_window_id=1, stamina=make_stamina())

    assert plan is None
