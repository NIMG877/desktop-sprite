from desktop_sprite.core.behavior_state_machine import BehaviorStateMachine
from desktop_sprite.core.behavior_orchestrator import BehaviorOrchestrator, BehaviorPhaseName
from desktop_sprite.core.pathfinding import PathFinder, PathPlan, PathStep, TraversalAction
from desktop_sprite.core.pet_controller import HoverAbility, PetController, SHOW_HOVER_SECONDS, WingAbility
from desktop_sprite.core.pet_mode import ModeController, PetMode
from desktop_sprite.environment.environment_snapshot import EnvironmentSnapshot
from desktop_sprite.models.geometry import Rect, Vec2
from desktop_sprite.models.pet_attribute import PetAttributeModifier, PetAttributeSheet
from desktop_sprite.models.platform import Platform, PlatformType
from desktop_sprite.models.state import Pet, PetState
from desktop_sprite.models.window_info import WindowInfo
from desktop_sprite.utils.config import load_config


def make_controller(window_top_y: float, pet_bottom: float = 200) -> tuple[PetController, Platform]:
    config = load_config()
    controller = PetController.__new__(PetController)
    controller.config = config
    controller.pathfinder = PathFinder()
    controller.path_plan = None
    controller.mode_controller = ModeController()
    controller.orchestrator = BehaviorOrchestrator()
    controller.pet = Pet(
        position=Vec2(100, pet_bottom - config.pet.height),
        velocity=Vec2(0, 0),
        width=config.pet.width,
        height=config.pet.height,
        state=PetState.WALK,
        support_surface_id="ground:work_area",
        target_surface_id="window:123:left",
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


def test_walk_toward_x_does_not_snap_at_edge_distance():
    controller, _side = make_controller(window_top_y=120)
    controller.pet.position.x = 100
    controller.pet.velocity.x = 0

    reached = controller._walk_toward_x(105)

    assert not reached
    assert controller.pet.position.x == 100
    assert controller.pet.velocity.x > 0


def test_controller_uses_attribute_sheet_for_movement_and_special_timing():
    controller, _side = make_controller(window_top_y=120)
    sheet = PetAttributeSheet.from_config(controller.config).with_modifiers(
        (
            PetAttributeModifier("mobility", 50, "percent"),
            PetAttributeModifier("attunement", 100),
        )
    )

    controller.set_attribute_sheet(sheet)
    controller.pet.position.x = 100
    controller.pet.velocity.x = 0

    controller._walk_toward_x(140)

    assert controller.pet.velocity.x == 180

    controller._start_open_wings()
    assert isinstance(controller._active_pet_ability, WingAbility)
    # The ability mirrors `effective_stats().wing_open_seconds` divided
    # by the resource-driven `special_factor` floor (see
    # `PetShowDirector._start_open_wings`). Computing the expected value
    # from those same inputs keeps the test decoupled from whatever
    # base value the shipped config picks for `attunement` /
    # `wings.open_seconds` — a snapshot of the old
    # `attunement=100` config would lock this to `0.5` and break as
    # soon as the config is tuned.
    expected_duration = controller.effective_stats().wing_open_seconds / max(
        controller._resource_influence().special_factor, 0.25
    )
    assert controller._active_pet_ability.duration == expected_duration


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
        steps=[
            PathStep(TraversalAction.MOVE, "ground:work_area", "ground:work_area", 140, 1)
        ],
        current_index=0,
        target_window_id=None,
        snapshot_timestamp=1.0,
        target_surface_id="ground:work_area",
        target_anchor_t=140,
    )

    handled = controller._execute_path_plan()

    assert handled
    assert controller.path_plan is not None
    assert controller.pet.velocity.x > 0
    assert controller.pet.state == PetState.WALK


def test_controller_executes_vertical_move_plan():
    controller, side = make_controller(window_top_y=120)
    controller.pet.state = PetState.CLIMB
    controller.state_machine = BehaviorStateMachine(PetState.CLIMB)
    controller.pet.position.x = side.rect.center_x - controller.pet.width / 2
    controller.pet.position.y = side.rect.bottom - controller.pet.height
    controller.pet.support_surface_id = side.id
    controller.pet.target_surface_id = side.id
    controller.path_plan = PathPlan(
        steps=[
            PathStep(TraversalAction.MOVE, side.id, side.id, side.rect.top, 1)
        ],
        current_index=0,
        target_window_id=side.source_id,
        snapshot_timestamp=1.0,
    )

    handled = controller._execute_path_plan()

    assert handled
    assert controller.path_plan is not None
    assert controller.pet.velocity.y < 0
    assert controller.pet.velocity.x == 0
    assert controller.pet.state == PetState.CLIMB


def test_same_platform_walk_plan_is_not_advanced_before_moving():
    controller, _side = make_controller(window_top_y=120)
    controller.pet.position.x = 100
    controller.path_plan = PathPlan(
        steps=[
            PathStep(TraversalAction.MOVE, "ground:work_area", "ground:work_area", 140, 1)
        ],
        current_index=0,
        target_window_id=None,
        snapshot_timestamp=1.0,
        target_surface_id="ground:work_area",
        target_anchor_t=140,
    )

    controller._advance_path_if_reached()

    assert controller.path_plan is not None
    assert controller.path_plan.current_index == 0
    assert controller.pet.state == PetState.WALK


def test_controller_executes_fall_step_from_surface_edge():
    controller, _side = make_controller(window_top_y=120)
    controller.pet.position.x = 100
    controller.path_plan = PathPlan(
        steps=[
            PathStep(TraversalAction.FALL, "ground:work_area", "window:123:top", 100, 1)
        ],
        current_index=0,
        target_window_id=123,
        snapshot_timestamp=1.0,
    )

    handled = controller._execute_path_plan()

    assert handled
    assert controller.pet.state == PetState.FALL
    assert controller.pet.support_surface_id is None
    assert controller.pet.target_surface_id == "window:123:top"


def test_random_wander_prefers_current_platform_via_path_plan(monkeypatch):
    controller, _side = make_controller(window_top_y=120)
    support = controller.snapshot.platform_by_id("ground:work_area")
    monkeypatch.setattr("desktop_sprite.core.pet_controller.random.random", lambda: 0.9)
    monkeypatch.setattr("desktop_sprite.core.pet_controller.random.uniform", lambda left, right: right)

    controller._start_random_wander(support)

    assert controller.path_plan is not None
    assert controller.path_plan.target_surface_id == support.id
    assert controller.path_plan.current_step is not None
    assert controller.path_plan.current_step.action == TraversalAction.MOVE
    assert controller.path_plan.current_step.from_surface_id == support.id
    assert controller.path_plan.current_step.to_surface_id == support.id
    assert controller.mode_controller.mode == PetMode.GO_TO_TARGET
    assert controller.orchestrator.phase.name == BehaviorPhaseName.PATH_EXECUTING


def test_set_target_surface_point_uses_pathfinder_plan():
    controller, _side = make_controller(window_top_y=120)

    success = controller.set_target_surface_point("ground:work_area", 180)

    assert success
    assert controller.path_plan is not None
    assert controller.path_plan.target_surface_id == "ground:work_area"
    assert controller.path_plan.target_anchor_t == 180
    assert controller.mode_controller.mode == PetMode.GO_TO_TARGET
    assert controller.orchestrator.phase.name == BehaviorPhaseName.PATH_EXECUTING


def test_set_target_surface_point_keeps_existing_plan_when_unreachable(monkeypatch):
    controller, _side = make_controller(window_top_y=120)
    existing = PathPlan(
        steps=[
            PathStep(TraversalAction.MOVE, "ground:work_area", "ground:work_area", 140, 1)
        ],
        current_index=0,
        target_window_id=None,
        snapshot_timestamp=1.0,
        target_surface_id="ground:work_area",
        target_anchor_t=140,
    )
    controller.path_plan = existing
    monkeypatch.setattr(controller.pathfinder, "find_path_to_surface_point", lambda **_kwargs: None)

    success = controller.set_target_surface_point("window:123:top", 100)

    assert not success
    assert controller.path_plan is existing
    assert controller.mode_controller.mode == PetMode.IDLE
    assert controller.orchestrator.phase.name == BehaviorPhaseName.IDLE_WAIT


def test_start_show_locks_mode_and_clears_path_plan():
    controller, _side = make_controller(window_top_y=120)
    controller.path_plan = PathPlan(
        steps=[
            PathStep(TraversalAction.MOVE, "ground:work_area", "ground:work_area", 140, 1)
        ],
        current_index=0,
        target_window_id=None,
        snapshot_timestamp=1.0,
        target_surface_id="ground:work_area",
        target_anchor_t=140,
    )

    assert controller.start_show()

    assert controller.path_plan is None
    assert controller.mode_controller.mode == PetMode.SHOW
    assert controller.mode_controller.locked
    assert controller.orchestrator.phase.name == BehaviorPhaseName.SHOW_OPEN_WINGS
    assert controller.pet.state == PetState.OPEN_WINGS


def test_sleep_stops_walking_and_clears_path_plan():
    controller, _side = make_controller(window_top_y=120)
    controller.path_plan = PathPlan(
        steps=[
            PathStep(TraversalAction.MOVE, "ground:work_area", "ground:work_area", 140, 1)
        ],
        current_index=0,
        target_window_id=123,
        snapshot_timestamp=1.0,
        target_surface_id="ground:work_area",
        target_anchor_t=140,
    )
    controller.pet.target_window_id = 123
    controller.pet.velocity.x = 40

    assert controller.sleep()

    assert controller.pet.state == PetState.SLEEP
    assert controller.pet.velocity.x == 0
    assert controller.path_plan is None
    assert controller.pet.target_window_id is None
    assert controller.pet.target_surface_id is None
    assert controller.mode_controller.mode == PetMode.IDLE
    assert controller.orchestrator.phase.name == BehaviorPhaseName.IDLE_WAIT


def test_sleep_does_not_interrupt_show_mode():
    controller, _side = make_controller(window_top_y=120)
    controller.start_show()

    assert not controller.sleep()
    assert controller.pet.state == PetState.OPEN_WINGS
    assert controller.mode_controller.mode == PetMode.SHOW


def test_low_energy_auto_sleep_wakes_only_after_higher_threshold():
    controller, _side = make_controller(window_top_y=120)
    sheet = PetAttributeSheet.from_config(controller.config)
    controller.set_attribute_sheet(sheet)
    stats = controller.effective_stats()
    controller.resources.energy = stats.base_energy * 0.09
    controller.pet.state = PetState.IDLE
    controller.pet.support_surface_id = "ground:work_area"

    controller._update_behavior(0.016)

    assert controller.pet.state == PetState.SLEEP
    assert controller._auto_sleeping

    controller.resources.energy = stats.base_energy * 0.44
    controller._update_behavior(0.016)

    assert controller.pet.state == PetState.SLEEP

    controller.resources.energy = stats.base_energy * 0.46
    controller._update_behavior(0.016)

    assert controller.pet.state == PetState.IDLE
    assert not controller._auto_sleeping


def test_low_stamina_rest_uses_higher_exit_threshold():
    controller, _side = make_controller(window_top_y=120)
    controller.set_attribute_sheet(PetAttributeSheet.from_config(controller.config))
    stats = controller.effective_stats()
    controller.resources.stamina = stats.base_stamina * 0.10
    controller.pet.state = PetState.IDLE
    controller.pet.support_surface_id = "ground:work_area"

    controller._update_behavior(0.016)

    assert controller.pet.state == PetState.IDLE
    assert controller._resource_resting

    controller.resources.stamina = stats.base_stamina * 0.39
    controller._update_behavior(0.016)

    assert controller._resource_resting

    controller.resources.stamina = stats.base_stamina * 0.41
    controller._update_behavior(0.016)

    assert not controller._resource_resting


def test_show_render_state_separates_canvas_from_pet_body():
    controller, _side = make_controller(window_top_y=120)
    original_x = controller.pet.position.x
    original_y = controller.pet.position.y

    controller.start_show()
    render = controller.render_state()

    assert controller.pet.position.x == original_x
    assert controller.pet.position.y == original_y
    assert render.width > controller.pet.width
    assert render.height > controller.pet.height
    assert render.pose_width == controller.pet.width
    assert render.pose_height == controller.pet.height
    assert render.body_offset_x > 0
    assert render.body_offset_y > 0
    assert render.x == controller.pet.position.x - render.body_offset_x
    assert render.y == controller.pet.position.y - render.body_offset_y


def test_show_mode_blocks_target_drag_poke_and_random_wander():
    controller, _side = make_controller(window_top_y=120)
    original_state = controller.pet.state

    controller.start_show()

    assert not controller.set_target_surface_point("ground:work_area", 180)
    controller.start_drag(120, 120)
    controller.poke()
    controller._start_random_wander(controller.snapshot.platform_by_id("ground:work_area"))

    assert controller.mode_controller.mode == PetMode.SHOW
    assert controller.pet.state != PetState.DRAGGED
    assert controller.pet.state != original_state or controller.pet.state == PetState.OPEN_WINGS
    assert controller.path_plan is None


def test_show_phases_finish_back_to_idle():
    controller, _side = make_controller(window_top_y=120)
    controller.start_show()

    # The full Show sequence is six phases, two of which (HOVER +
    # TITLE) hold the pet on screen for SHOW_HOVER_SECONDS +
    # SHOW_TITLE_SECONDS = 3.7s regardless of config, and the four
    # movement phases scale with `attunement` / `arcana`. With the
    # shipped config the worst case is ~19s end-to-end, so 250 ticks
    # of 0.1s gives a comfortable 6s buffer without making the test
    # slow to fail on a real regression.
    for _ in range(250):
        controller._update_show(0.1)
        if controller.mode_controller.mode == PetMode.IDLE:
            break

    assert controller.mode_controller.mode == PetMode.IDLE
    assert not controller.mode_controller.locked
    assert controller.orchestrator.phase.name == BehaviorPhaseName.IDLE_WAIT
    assert controller.pet.state == PetState.IDLE


def test_show_flight_uses_pet_flight_speed_instead_of_phase_duration():
    controller, _side = make_controller(window_top_y=120)
    controller.start_show()

    # Tick by the *effective* wing-open duration (not the raw config
    # value): the runtime divides `wings.open_seconds` by an
    # `attunement`-derived ratio, so 1.0s of game time is only enough
    # to clear OPEN_WINGS when `attunement` happens to be 1.0.
    controller._update_show(controller.effective_stats().wing_open_seconds)
    assert controller.orchestrator.phase.name == BehaviorPhaseName.SHOW_FLY

    start_x = controller.pet.position.x
    start_y = controller.pet.position.y
    controller._update_show(0.1)
    distance = ((controller.pet.position.x - start_x) ** 2 + (controller.pet.position.y - start_y) ** 2) ** 0.5

    # Likewise the in-flight velocity is the *effective* flight
    # speed (raw `flight.speed` × `arcana` ratio), not the raw config
    # number — computing the expected from the same source keeps the
    # assertion meaningful when the shipped config tunes `arcana`.
    expected_speed = controller.effective_stats().flight_speed * 0.1
    assert round(distance, 5) == round(expected_speed, 5)


def test_hover_ability_loops_until_caller_supplies_duration():
    controller, _side = make_controller(window_top_y=120)
    controller.pet.state = PetState.FLY
    controller.state_machine = BehaviorStateMachine(PetState.FLY)

    controller._start_hover(100, 80)

    assert not controller._update_pet_ability(10.0)
    assert controller.pet.state == PetState.HOVER


def test_show_title_reuses_existing_hover_ability_without_resetting_elapsed():
    controller, _side = make_controller(window_top_y=120)
    controller.start_show()
    controller.orchestrator.advance_sequence()
    controller.orchestrator.advance_sequence()
    controller._active_pet_ability = None

    controller._update_show(SHOW_HOVER_SECONDS + 0.1)

    ability = controller._active_pet_ability
    assert isinstance(ability, HoverAbility)
    assert controller.orchestrator.phase.name == BehaviorPhaseName.SHOW_TITLE
    assert ability.elapsed > SHOW_HOVER_SECONDS

    same_ability = ability
    controller._update_show(0.1)

    assert controller._active_pet_ability is same_ability
    assert same_ability.elapsed > SHOW_HOVER_SECONDS + 0.1


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


def test_controller_clears_path_when_next_platform_disappears():
    controller, _side = make_controller(window_top_y=120)
    controller.path_plan = PathPlan(
        steps=[
            PathStep(TraversalAction.JUMP, "ground:work_area", "missing:platform", 100, 1)
        ],
        current_index=0,
        target_window_id=99,
        snapshot_timestamp=1.0,
    )

    controller._validate_path_plan()

    assert controller.path_plan is None
    assert controller.mode_controller.mode == PetMode.IDLE
    assert controller.orchestrator.phase.name == BehaviorPhaseName.IDLE_WAIT


def test_dragging_preserves_existing_path_plan_for_debug():
    controller, _side = make_controller(window_top_y=120)
    controller.path_plan = PathPlan(
        steps=[
            PathStep(TraversalAction.TRANSFORM, "ground:work_area", "window:123:top", 100, 1, "window:123:left")
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
    controller.pet.target_surface_id = side.id
    controller.pet.position.y = -20
    controller.path_plan = PathPlan(
        steps=[
            PathStep(TraversalAction.TRANSFORM, "ground:work_area", "window:123:top", side.rect.center_x - controller.pet.width / 2, 1, side.id)
        ],
        current_index=0,
        target_window_id=123,
        snapshot_timestamp=1.0,
    )

    controller._validate_path_plan()

    assert controller.path_plan is not None


def test_validate_keeps_planned_climb_path_without_rechecking_reachability():
    controller, side = make_controller_with_side(window_top_y=25, window_bottom_y=140)
    controller.pet.state = PetState.WALK
    controller.path_plan = PathPlan(
        steps=[
            PathStep(TraversalAction.TRANSFORM, "ground:work_area", "window:123:top", side.rect.center_x - controller.pet.width / 2, 1, side.id)
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
    controller.pet.support_surface_id = "window:123:top"
    controller.pet.target_surface_id = None
    controller.pet.position.x = side.rect.center_x - controller.pet.width / 2
    controller.path_plan = PathPlan(
        steps=[
            PathStep(TraversalAction.TRANSFORM, "ground:work_area", "window:123:top", side.rect.center_x - controller.pet.width / 2, 1, side.id),
            PathStep(TraversalAction.MOVE, "window:123:top", "window:123:top", controller.pet.position.x + 30, 1),
        ],
        current_index=0,
        target_window_id=123,
        snapshot_timestamp=1.0,
    )

    controller._update_behavior(0.016)

    assert controller.path_plan is not None
    assert controller.path_plan.current_index == 1
    assert controller.pet.state == PetState.WALK
    assert controller.pet.velocity.x > 0


def test_completed_final_climb_finishes_path_on_top_platform():
    controller, side = make_controller(window_top_y=120)
    controller.pet.state = PetState.CLIMB
    controller.state_machine = BehaviorStateMachine(PetState.CLIMB)
    controller.pet.support_surface_id = "window:123:top"
    controller.pet.target_surface_id = None
    controller.path_plan = PathPlan(
        steps=[
            PathStep(TraversalAction.TRANSFORM, "ground:work_area", "window:123:top", side.rect.center_x - controller.pet.width / 2, 1, side.id)
        ],
        current_index=0,
        target_window_id=123,
        snapshot_timestamp=1.0,
    )

    controller._update_behavior(0.016)

    assert controller.path_plan is None
    assert controller.pet.support_surface_id == "window:123:top"
    assert controller.pet.state == PetState.IDLE
    assert controller.mode_controller.mode == PetMode.IDLE
    assert controller.orchestrator.phase.name == BehaviorPhaseName.IDLE_WAIT


def test_landing_tick_preserves_existing_path_plan():
    controller, _side = make_controller(window_top_y=120)
    controller.pet.state = PetState.IDLE
    controller.pet.support_surface_id = "window:123:top"
    controller._landed_on_platform_last_tick = True
    controller.path_plan = PathPlan(
        steps=[
            PathStep(TraversalAction.JUMP, "ground:work_area", "window:123:top", 100, 1)
        ],
        current_index=0,
        target_window_id=123,
        snapshot_timestamp=1.0,
    )

    controller._update_behavior(0.016)

    assert controller.path_plan is not None
    assert controller.path_plan.current_index == 0


def test_jump_grab_uses_planned_wall_contact_point():
    controller, side = make_controller(window_top_y=120)
    controller.pet.state = PetState.JUMP
    controller.pet.support_surface_id = None
    controller.pet.target_surface_id = side.id
    controller.pet.position.x = side.rect.center_x - controller.pet.width / 2
    controller.pet.position.y = side.rect.top - controller.pet.height
    controller.path_plan = PathPlan(
        steps=[
            PathStep(
                TraversalAction.JUMP,
                "ground:work_area",
                side.id,
                controller.pet.position.x,
                1,
                land_t=side.rect.top,
                land_point=(controller.pet.position.x, side.rect.top - controller.pet.height),
            ),
            PathStep(
                TraversalAction.TRANSFORM,
                side.id,
                "window:123:top",
                controller.pet.position.x,
                1,
                side.id,
            ),
        ],
        current_index=0,
        target_window_id=side.source_id,
        snapshot_timestamp=1.0,
    )

    controller._maybe_grab_climb_side_while_jumping()

    assert controller.pet.state == PetState.CLIMB
    assert controller.pet.target_surface_id == side.id
    assert controller.path_plan is not None
    assert controller.path_plan.current_index == 1


def test_landing_tick_does_not_start_new_path(monkeypatch):
    controller, _side = make_controller(window_top_y=120)
    controller.pet.state = PetState.IDLE
    controller.pet.support_surface_id = "window:123:top"
    controller.pet.target_surface_id = None
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
