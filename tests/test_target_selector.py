from desktop_sprite.environment.environment_snapshot import EnvironmentSnapshot
from desktop_sprite.models.geometry import Rect
from desktop_sprite.models.platform import Platform, PlatformType
from desktop_sprite.ui.target_selector import select_target_candidate


def make_snapshot(platforms: list[Platform]) -> EnvironmentSnapshot:
    return EnvironmentSnapshot(
        screen_rect=Rect.from_xywh(0, 0, 800, 600),
        work_area_rect=Rect.from_xywh(0, 0, 800, 560),
        taskbar_rect=None,
        windows=[],
        platforms=platforms,
        timestamp=1.0,
    )


def walkable_platform(id_: str, top: float, left: float = 0, right: float = 400) -> Platform:
    return Platform(
        id=id_,
        type=PlatformType.WINDOW_TOP,
        rect=Rect(left, top, right, top + 8),
        walkable=True,
        climbable=False,
    )


def test_select_target_candidate_prefers_nearest_vertical_platform():
    upper = walkable_platform("upper", top=80)
    lower = walkable_platform("lower", top=140)
    snapshot = make_snapshot([upper, lower])

    candidate = select_target_candidate(
        snapshot=snapshot,
        cursor_x=160,
        cursor_y=100,
        pet_width=80,
        search_down_distance=80,
        search_up_distance=40,
    )

    assert candidate is not None
    assert candidate.platform.id == "upper"
    assert candidate.anchor_t == 120
    assert candidate.flag_x == 160


def test_select_target_candidate_ignores_platforms_outside_search_ranges():
    snapshot = make_snapshot(
        [
            walkable_platform("too-high", top=40),
            walkable_platform("too-low", top=260),
        ]
    )

    candidate = select_target_candidate(
        snapshot=snapshot,
        cursor_x=160,
        cursor_y=120,
        pet_width=80,
        search_down_distance=100,
        search_up_distance=40,
    )

    assert candidate is None


def test_select_target_candidate_ignores_non_walkable_platforms():
    wall = Platform(
        id="wall",
        type=PlatformType.WINDOW_LEFT,
        rect=Rect.from_xywh(100, 80, 8, 200),
        walkable=False,
        climbable=True,
    )
    snapshot = make_snapshot([wall])

    candidate = select_target_candidate(
        snapshot=snapshot,
        cursor_x=104,
        cursor_y=100,
        pet_width=80,
        search_down_distance=100,
        search_up_distance=40,
    )

    assert candidate is None
