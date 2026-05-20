from desktop_sprite.core.physics_engine import PhysicsEngine
from desktop_sprite.environment.environment_snapshot import EnvironmentSnapshot
from desktop_sprite.models.geometry import Rect, Vec2
from desktop_sprite.models.platform import Platform, PlatformType
from desktop_sprite.models.state import Pet, PetState
from desktop_sprite.utils.config import PhysicsConfig


def make_physics():
    return PhysicsEngine(
        PhysicsConfig(
            gravity=1000,
            walk_speed=100,
            climb_speed=80,
            jump_speed_x=180,
            jump_speed_y=-520,
            max_fall_speed=1100,
            drag_throw_factor=0.65,
            edge_snap_distance=10,
        )
    )


def make_snapshot(platforms):
    return EnvironmentSnapshot(
        screen_rect=Rect.from_xywh(0, 0, 300, 200),
        work_area_rect=Rect.from_xywh(0, 0, 300, 200),
        taskbar_rect=None,
        windows=[],
        platforms=platforms,
        timestamp=0,
    )


def test_falling_pet_lands_on_platform():
    physics = make_physics()
    pet = Pet(
        position=Vec2(50, 40),
        velocity=Vec2(0, 200),
        width=40,
        height=60,
        state=PetState.FALL,
    )
    platform = Platform(
        id="ground:test",
        type=PlatformType.GROUND,
        rect=Rect.from_xywh(0, 120, 200, 4),
        walkable=True,
        climbable=False,
    )
    snapshot = make_snapshot([platform])

    physics.update(pet, snapshot, 0.1)

    assert pet.support_platform_id == "ground:test"
    assert pet.position.y == 60
    assert pet.velocity.y == 0


def test_supported_pet_falls_when_platform_moves_out_from_under_it():
    physics = make_physics()
    pet = Pet(
        position=Vec2(50, 60),
        velocity=Vec2(0, 0),
        width=40,
        height=60,
        state=PetState.IDLE,
        support_platform_id="window:123:top",
    )
    moved_platform = Platform(
        id="window:123:top",
        type=PlatformType.WINDOW_TOP,
        rect=Rect.from_xywh(180, 120, 100, 4),
        walkable=True,
        climbable=False,
        dynamic=True,
        source_id=123,
    )
    snapshot = make_snapshot([moved_platform])

    physics.update(pet, snapshot, 0.1)

    assert pet.support_platform_id is None
    assert pet.state == PetState.FALL
    assert pet.velocity.y > 0


def test_supported_pet_is_lifted_when_dynamic_platform_moves_up():
    physics = make_physics()
    pet = Pet(
        position=Vec2(50, 60),
        velocity=Vec2(0, 0),
        width=40,
        height=60,
        state=PetState.IDLE,
        support_platform_id="window:123:top",
    )
    previous = make_snapshot(
        [
            Platform(
                id="window:123:top",
                type=PlatformType.WINDOW_TOP,
                rect=Rect.from_xywh(0, 120, 200, 4),
                walkable=True,
                climbable=False,
                dynamic=True,
                source_id=123,
            )
        ]
    )
    current = make_snapshot(
        [
            Platform(
                id="window:123:top",
                type=PlatformType.WINDOW_TOP,
                rect=Rect.from_xywh(0, 90, 200, 4),
                walkable=True,
                climbable=False,
                dynamic=True,
                source_id=123,
            )
        ]
    )

    physics.reconcile_platform_motion(pet, previous, current)
    physics.update(pet, current, 0.1)

    assert pet.support_platform_id == "window:123:top"
    assert pet.position.y == 30
    assert pet.velocity.y == 0


def test_supported_pet_is_not_carried_down_when_dynamic_platform_moves_down():
    physics = make_physics()
    pet = Pet(
        position=Vec2(50, 60),
        velocity=Vec2(0, 0),
        width=40,
        height=60,
        state=PetState.IDLE,
        support_platform_id="window:123:top",
    )
    previous = make_snapshot(
        [
            Platform(
                id="window:123:top",
                type=PlatformType.WINDOW_TOP,
                rect=Rect.from_xywh(0, 120, 200, 4),
                walkable=True,
                climbable=False,
                dynamic=True,
                source_id=123,
            )
        ]
    )
    current = make_snapshot(
        [
            Platform(
                id="window:123:top",
                type=PlatformType.WINDOW_TOP,
                rect=Rect.from_xywh(0, 150, 200, 4),
                walkable=True,
                climbable=False,
                dynamic=True,
                source_id=123,
            )
        ]
    )

    physics.reconcile_platform_motion(pet, previous, current)

    assert pet.position.y == 60


def test_jumping_pet_lands_like_falling_pet():
    physics = make_physics()
    pet = Pet(
        position=Vec2(50, 40),
        velocity=Vec2(0, 200),
        width=40,
        height=60,
        state=PetState.JUMP,
    )
    platform = Platform(
        id="ground:test",
        type=PlatformType.GROUND,
        rect=Rect.from_xywh(0, 120, 200, 4),
        walkable=True,
        climbable=False,
    )
    snapshot = make_snapshot([platform])

    physics.update(pet, snapshot, 0.1)

    assert pet.support_platform_id == "ground:test"
    assert pet.position.y == 60
    assert pet.state == PetState.IDLE
