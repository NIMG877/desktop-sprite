from desktop_sprite.core.behavior_state_machine import BehaviorStateMachine
from desktop_sprite.core.pet_controller import PetController
from desktop_sprite.environment.environment_snapshot import EnvironmentSnapshot
from desktop_sprite.models.geometry import Rect, Vec2
from desktop_sprite.models.platform import Platform, PlatformType
from desktop_sprite.models.state import Pet, PetState
from desktop_sprite.utils.config import load_config


def make_controller(window_top_y: float, pet_bottom: float = 200) -> tuple[PetController, Platform]:
    config = load_config()
    controller = PetController.__new__(PetController)
    controller.config = config
    controller.pet = Pet(
        position=Vec2(100, pet_bottom - config.pet.height),
        velocity=Vec2(0, 0),
        width=config.pet.width,
        height=config.pet.height,
        state=PetState.WALK,
        support_platform_id="ground:work_area",
        target_platform_id="window:123:left",
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


def test_climb_reachability_allows_standing_reach():
    controller, side = make_controller(window_top_y=120)

    assert controller._climb_reachability(side) == "stand"


def test_climb_reachability_allows_jump_reach():
    controller, side = make_controller(window_top_y=25)

    assert controller._climb_reachability(side) == "jump"


def test_climb_reachability_blocks_unreachable_edge():
    controller, side = make_controller(window_top_y=-80)

    assert controller._climb_reachability(side) == "unreachable"


def test_unreachable_climb_target_is_cleared_instead_of_climbing():
    controller, side = make_controller(window_top_y=-80)

    controller._walk_toward_climb_side(side)

    assert controller.pet.target_platform_id is None
    assert controller.pet.state == PetState.IDLE


def test_reachable_tall_edge_starts_jump_before_climb():
    controller, side = make_controller(window_top_y=25)

    controller._walk_toward_climb_side(side)

    assert controller.pet.state == PetState.JUMP
    assert controller.pet.support_platform_id is None
    assert controller.pet.velocity.y == controller.config.physics.jump_speed_y
