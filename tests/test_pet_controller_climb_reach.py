from desktop_sprite.core.behavior_state_machine import BehaviorStateMachine
from desktop_sprite.core.pathfinding import PathAction, PathEdge, PathFinder, PathPlan
from desktop_sprite.core.pet_controller import PetController
from desktop_sprite.core.stamina_system import StaminaSystem
from desktop_sprite.environment.environment_snapshot import EnvironmentSnapshot
from desktop_sprite.models.geometry import Rect, Vec2
from desktop_sprite.models.platform import Platform, PlatformType
from desktop_sprite.models.state import Pet, PetState
from desktop_sprite.models.window_info import WindowInfo
from desktop_sprite.utils.config import load_config


def make_controller(window_top_y: float, pet_bottom: float = 200) -> tuple[PetController, Platform]:
    config = load_config()
    controller = PetController.__new__(PetController)
    controller.config = config
    controller.stamina = StaminaSystem(config.stamina, config.physics)
    controller.pathfinder = PathFinder()
    controller.path_plan = None
    controller.pet = Pet(
        position=Vec2(100, pet_bottom - config.pet.height),
        velocity=Vec2(0, 0),
        width=config.pet.width,
        height=config.pet.height,
        state=PetState.WALK,
        support_platform_id="ground:work_area",
        target_platform_id="window:123:left",
        stamina=config.stamina.initial_stamina,
    )
    controller.state_machine = BehaviorStateMachine(PetState.WALK)
    controller._state_goal_until = 0.0

    top = Platform(
        id="window:123:top",
        type=PlatformType.WINDOW_TOP,
        rect=Rect.from_xywh(80, window_top_y, 180, 4),
        walkable=True,
        climbable=False,
        dynamic=True,
        source_id=123,
    )
    side = Platform(
        id="window:123:left",
        type=PlatformType.WINDOW_LEFT,
        rect=Rect.from_xywh(100, window_top_y, 8, 180),
        walkable=False,
        climbable=True,
        dynamic=True,
        source_id=123,
    )
    ground = Platform(
        id="ground:work_area",
        type=PlatformType.GROUND,
        rect=Rect.from_xywh(0, pet_bottom, 500, 4),
        walkable=True,
        climbable=False,
    )
    controller.snapshot = EnvironmentSnapshot(
        screen_rect=Rect.from_xywh(0, 0, 500, 400),
        work_area_rect=Rect.from_xywh(0, 0, 500, 360),
        taskbar_rect=None,
        windows=[],
        platforms=[ground, top, side],
        timestamp=0,
    )
    return controller, side


def make_controller_with_side(window_top_y: float, window_bottom_y: float, pet_bottom: float = 200) -> tuple[PetController, Platform]:
    controller, side = make_controller(window_top_y=window_top_y, pet_bottom=pet_bottom)
    side = Platform(
        id=side.id,
        type=side.type,
        rect=Rect(side.rect.left, window_top_y, side.rect.right, window_bottom_y),
        walkable=side.walkable,
        climbable=side.climbable,
        dynamic=side.dynamic,
        source_id=side.source_id,
    )
    controller.snapshot = EnvironmentSnapshot(
        screen_rect=controller.snapshot.screen_rect,
        work_area_rect=controller.snapshot.work_area_rect,
        taskbar_rect=None,
        windows=[],
        platforms=[platform for platform in controller.snapshot.platforms if platform.id != side.id] + [side],
        timestamp=0,
    )
    return controller, side


def test_climb_reachability_allows_standing_reach():
    controller, side = make_controller(window_top_y=120)

    assert controller._climb_reachability(side) == "stand"


def test_climb_reachability_allows_jump_reach():
    controller, side = make_controller_with_side(window_top_y=25, window_bottom_y=140)

    assert controller._climb_reachability(side) == "jump"


def test_climb_reachability_blocks_unreachable_edge():
    controller, side = make_controller_with_side(window_top_y=-80, window_bottom_y=80)

    assert controller._climb_reachability(side) == "unreachable"


def test_unreachable_climb_target_is_cleared_instead_of_climbing():
    controller, side = make_controller_with_side(window_top_y=-80, window_bottom_y=80)

    controller._walk_toward_climb_side(side)

    assert controller.pet.target_platform_id is None
    assert controller.pet.state == PetState.IDLE


def test_reachable_tall_edge_starts_jump_before_climb():
    controller, side = make_controller_with_side(window_top_y=25, window_bottom_y=140)

    controller._walk_toward_climb_side(side)

    assert controller.pet.state == PetState.JUMP
    assert controller.pet.support_platform_id is None
    assert controller.pet.velocity.y < 0


def test_low_stamina_can_make_same_tall_edge_unreachable():
    controller, side = make_controller_with_side(window_top_y=25, window_bottom_y=140)
    controller.pet.stamina = 20

    assert controller._climb_reachability(side) == "unreachable"


def test_high_window_top_can_still_be_climbable_when_window_bottom_is_reachable():
    controller, side = make_controller_with_side(window_top_y=20, window_bottom_y=190)

    assert controller._climb_reachability(side) == "stand"


def test_window_bottom_above_pet_bottom_requires_jump_even_if_within_pet_height():
    controller, side = make_controller_with_side(window_top_y=25, window_bottom_y=140)

    assert 0 < controller.pet.bottom - side.rect.bottom < controller.pet.height
    assert controller._climb_reachability(side) == "jump"


def test_reachable_bottom_is_blocked_when_climb_distance_exceeds_stamina():
    controller, side = make_controller_with_side(window_top_y=-900, window_bottom_y=190)

    assert controller._climb_reachability(side) == "unreachable"


def test_exhausted_pet_clears_target_and_rests():
    controller, _side = make_controller(window_top_y=120)
    controller.pet.stamina = 5
    controller.pet.state = PetState.MOVE_TO_TARGET
    controller.pet.velocity.x = 40

    controller._update_behavior(0.016)

    assert controller.pet.target_platform_id is None
    assert controller.pet.velocity.x == 0
    assert controller.pet.state == PetState.IDLE


def test_walk_toward_x_does_not_snap_at_edge_distance():
    controller, _side = make_controller(window_top_y=120)
    controller.pet.position.x = 100
    controller.pet.velocity.x = 0

    reached = controller._walk_toward_x(105)

    assert not reached
    assert controller.pet.position.x == 100
    assert controller.pet.velocity.x > 0


def test_walking_does_not_end_just_because_previous_goal_time_expired():
    controller, _side = make_controller(window_top_y=120)
    support = controller.snapshot.platform_by_id("ground:work_area")
    controller.pet.state = PetState.WALK
    controller.pet.velocity.x = 20
    controller._state_goal_until = 0

    controller._keep_walking_on_platform(support, 0.016)

    assert controller.pet.state == PetState.WALK


def test_pathless_walk_is_normalized_to_idle():
    controller, _side = make_controller(window_top_y=120)
    controller.pet.state = PetState.WALK
    controller.pet.velocity.x = 40
    controller.path_plan = None

    controller._update_behavior(0.016)

    assert controller.pet.state == PetState.IDLE
    assert controller.pet.velocity.x == 0


def test_controller_executes_same_platform_walk_plan():
    controller, _side = make_controller(window_top_y=120)
    controller.pet.position.x = 100
    controller.path_plan = PathPlan(
        edges=[
            PathEdge(
                action=PathAction.WALK,
                from_platform_id="ground:work_area",
                to_platform_id="ground:work_area",
                target_x=140,
                cost=1,
            )
        ],
        current_index=0,
        target_window_id=None,
        snapshot_timestamp=1.0,
        target_platform_id="ground:work_area",
        target_x=140,
    )

    handled = controller._execute_path_plan()

    assert handled
    assert controller.path_plan is not None
    assert controller.pet.velocity.x > 0
    assert controller.pet.state == PetState.MOVE_TO_TARGET


def test_same_platform_walk_plan_is_not_advanced_before_moving():
    controller, _side = make_controller(window_top_y=120)
    controller.pet.position.x = 100
    controller.path_plan = PathPlan(
        edges=[
            PathEdge(
                action=PathAction.WALK,
                from_platform_id="ground:work_area",
                to_platform_id="ground:work_area",
                target_x=140,
                cost=1,
            )
        ],
        current_index=0,
        target_window_id=None,
        snapshot_timestamp=1.0,
        target_platform_id="ground:work_area",
        target_x=140,
    )

    controller._advance_path_if_reached()

    assert controller.path_plan is not None
    assert controller.path_plan.current_index == 0
    assert controller.pet.state == PetState.WALK


def test_random_wander_prefers_current_platform_via_path_plan(monkeypatch):
    controller, _side = make_controller(window_top_y=120)
    support = controller.snapshot.platform_by_id("ground:work_area")
    monkeypatch.setattr("desktop_sprite.core.pet_controller.random.random", lambda: 0.1)
    monkeypatch.setattr("desktop_sprite.core.pet_controller.random.uniform", lambda left, right: right)

    controller._start_random_wander(support)

    assert controller.path_plan is not None
    assert controller.path_plan.target_platform_id == support.id
    assert controller.path_plan.current_edge is not None
    assert controller.path_plan.current_edge.action == PathAction.WALK
    assert controller.path_plan.current_edge.from_platform_id == support.id
    assert controller.path_plan.current_edge.to_platform_id == support.id


def window_platforms(hwnd: int, left: float, top: float, right: float, bottom: float) -> list[Platform]:
    return [
        Platform(
            id=f"window:{hwnd}:top",
            type=PlatformType.WINDOW_TOP,
            rect=Rect(left, top, right, top + 8),
            walkable=True,
            climbable=False,
            dynamic=True,
            source_id=hwnd,
        ),
        Platform(
            id=f"window:{hwnd}:left",
            type=PlatformType.WINDOW_LEFT,
            rect=Rect(left - 8, top, left + 6, bottom),
            walkable=False,
            climbable=True,
            dynamic=True,
            source_id=hwnd,
        ),
        Platform(
            id=f"window:{hwnd}:right",
            type=PlatformType.WINDOW_RIGHT,
            rect=Rect(right - 6, top, right + 8, bottom),
            walkable=False,
            climbable=True,
            dynamic=True,
            source_id=hwnd,
        ),
    ]


def test_controller_plans_intermediate_path_to_high_foreground_window():
    controller, _side = make_controller(window_top_y=430)
    controller.snapshot = EnvironmentSnapshot(
        screen_rect=Rect.from_xywh(0, 0, 900, 700),
        work_area_rect=Rect.from_xywh(0, 0, 900, 650),
        taskbar_rect=None,
        windows=[
            WindowInfo(
                hwnd=2,
                title="target",
                rect=Rect(340, 300, 520, 500),
                visible=True,
                minimized=False,
                is_foreground=True,
            )
        ],
        platforms=[
            Platform(
                id="ground:work_area",
                type=PlatformType.GROUND,
                rect=Rect.from_xywh(0, 650, 900, 4),
                walkable=True,
                climbable=False,
            ),
            *window_platforms(1, 160, 430, 320, 620),
            *window_platforms(2, 340, 300, 520, 500),
        ],
        timestamp=2.0,
    )

    controller._maybe_target_foreground_window()

    assert controller.path_plan is not None
    assert controller.path_plan.target_window_id == 2
    assert len(controller.path_plan.edges) >= 2


def test_controller_clears_path_when_next_platform_disappears():
    controller, _side = make_controller(window_top_y=120)
    controller.path_plan = PathPlan(
        edges=[
            PathEdge(
                action=PathAction.JUMP,
                from_platform_id="ground:work_area",
                to_platform_id="missing:platform",
                target_x=100,
                cost=1,
            )
        ],
        current_index=0,
        target_window_id=99,
        snapshot_timestamp=1.0,
    )

    controller._validate_path_plan()

    assert controller.path_plan is None


def test_dragging_preserves_existing_path_plan_for_debug():
    controller, _side = make_controller(window_top_y=120)
    controller.path_plan = PathPlan(
        edges=[
            PathEdge(
                action=PathAction.CLIMB,
                from_platform_id="ground:work_area",
                to_platform_id="window:123:top",
                target_x=100,
                cost=1,
                side_platform_id="window:123:left",
            )
        ],
        current_index=0,
        target_window_id=123,
        snapshot_timestamp=1.0,
    )

    controller.start_drag(100, 100)

    assert controller.path_plan is not None


def test_validate_keeps_active_climb_path_even_when_current_position_no_longer_reaches_side():
    controller, side = make_controller_with_side(window_top_y=25, window_bottom_y=140)
    controller.pet.state = PetState.CLIMB
    controller.pet.target_platform_id = side.id
    controller.pet.position.y = -20
    controller.path_plan = PathPlan(
        edges=[
            PathEdge(
                action=PathAction.CLIMB,
                from_platform_id="ground:work_area",
                to_platform_id="window:123:top",
                target_x=side.rect.center_x - controller.pet.width / 2,
                cost=1,
                side_platform_id=side.id,
            )
        ],
        current_index=0,
        target_window_id=123,
        snapshot_timestamp=1.0,
    )

    controller._validate_path_plan()

    assert controller.path_plan is not None


def test_validate_keeps_planned_climb_path_without_rechecking_reachability():
    controller, side = make_controller_with_side(window_top_y=25, window_bottom_y=140)
    controller.pet.state = PetState.MOVE_TO_TARGET
    controller.pet.stamina = 0
    controller.path_plan = PathPlan(
        edges=[
            PathEdge(
                action=PathAction.CLIMB,
                from_platform_id="ground:work_area",
                to_platform_id="window:123:top",
                target_x=side.rect.center_x - controller.pet.width / 2,
                cost=1,
                side_platform_id=side.id,
            )
        ],
        current_index=0,
        target_window_id=123,
        snapshot_timestamp=1.0,
    )

    controller._validate_path_plan()

    assert controller.path_plan is not None


def test_completed_climb_continues_with_next_path_edge():
    controller, side = make_controller(window_top_y=120)
    controller.pet.state = PetState.CLIMB
    controller.state_machine = BehaviorStateMachine(PetState.CLIMB)
    controller.pet.support_platform_id = "window:123:top"
    controller.pet.target_platform_id = None
    controller.pet.position.x = side.rect.center_x - controller.pet.width / 2
    controller.path_plan = PathPlan(
        edges=[
            PathEdge(
                action=PathAction.CLIMB,
                from_platform_id="ground:work_area",
                to_platform_id="window:123:top",
                target_x=side.rect.center_x - controller.pet.width / 2,
                cost=1,
                side_platform_id=side.id,
            ),
            PathEdge(
                action=PathAction.WALK,
                from_platform_id="window:123:top",
                to_platform_id="window:123:top",
                target_x=controller.pet.position.x + 30,
                cost=1,
            ),
        ],
        current_index=0,
        target_window_id=123,
        snapshot_timestamp=1.0,
    )

    controller._update_behavior(0.016)

    assert controller.path_plan is not None
    assert controller.path_plan.current_index == 1
    assert controller.pet.state == PetState.MOVE_TO_TARGET
    assert controller.pet.velocity.x > 0


def test_completed_final_climb_finishes_path_on_top_platform():
    controller, side = make_controller(window_top_y=120)
    controller.pet.state = PetState.CLIMB
    controller.state_machine = BehaviorStateMachine(PetState.CLIMB)
    controller.pet.support_platform_id = "window:123:top"
    controller.pet.target_platform_id = None
    controller.path_plan = PathPlan(
        edges=[
            PathEdge(
                action=PathAction.CLIMB,
                from_platform_id="ground:work_area",
                to_platform_id="window:123:top",
                target_x=side.rect.center_x - controller.pet.width / 2,
                cost=1,
                side_platform_id=side.id,
            )
        ],
        current_index=0,
        target_window_id=123,
        snapshot_timestamp=1.0,
    )

    controller._update_behavior(0.016)

    assert controller.path_plan is None
    assert controller.pet.support_platform_id == "window:123:top"
    assert controller.pet.state == PetState.IDLE


def test_landing_tick_preserves_existing_path_plan():
    controller, _side = make_controller(window_top_y=120)
    controller.pet.state = PetState.IDLE
    controller.pet.support_platform_id = "window:123:top"
    controller._landed_on_platform_last_tick = True
    controller.path_plan = PathPlan(
        edges=[
            PathEdge(
                action=PathAction.JUMP,
                from_platform_id="ground:work_area",
                to_platform_id="window:123:top",
                target_x=100,
                cost=1,
            )
        ],
        current_index=0,
        target_window_id=123,
        snapshot_timestamp=1.0,
    )

    controller._update_behavior(0.016)

    assert controller.path_plan is not None
    assert controller.path_plan.current_index == 0


def test_landing_tick_does_not_start_new_path(monkeypatch):
    controller, _side = make_controller(window_top_y=120)
    controller.pet.state = PetState.IDLE
    controller.pet.support_platform_id = "window:123:top"
    controller.pet.target_platform_id = None
    controller.path_plan = None
    controller._landed_on_platform_last_tick = True
    called = False

    def fail_find_path(*args, **kwargs):
        nonlocal called
        called = True
        return None

    monkeypatch.setattr(controller.pathfinder, "find_path", fail_find_path)

    controller._update_behavior(0.016)

    assert controller.path_plan is None
    assert not called


def test_controller_does_not_plan_when_stamina_below_resume_threshold():
    controller, _side = make_controller(window_top_y=120)
    controller.pet.stamina = 20
    controller.snapshot = EnvironmentSnapshot(
        screen_rect=controller.snapshot.screen_rect,
        work_area_rect=controller.snapshot.work_area_rect,
        taskbar_rect=None,
        windows=[
            WindowInfo(
                hwnd=123,
                title="target",
                rect=Rect(80, 120, 260, 300),
                visible=True,
                minimized=False,
                is_foreground=True,
            )
        ],
        platforms=controller.snapshot.platforms,
        timestamp=3.0,
    )

    controller._maybe_target_foreground_window()

    assert controller.path_plan is None
