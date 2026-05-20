from desktop_sprite.core.physics_engine import PhysicsEngine
from desktop_sprite.environment.environment_snapshot import EnvironmentSnapshot
from desktop_sprite.models.geometry import Rect, Vec2
from desktop_sprite.models.platform import Platform, PlatformType
from desktop_sprite.models.state import Pet, PetState
from desktop_sprite.utils.config import PhysicsConfig


def test_falling_pet_lands_on_platform():
    physics = PhysicsEngine(
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
    snapshot = EnvironmentSnapshot(
        screen_rect=Rect.from_xywh(0, 0, 300, 200),
        work_area_rect=Rect.from_xywh(0, 0, 300, 200),
        taskbar_rect=None,
        windows=[],
        platforms=[platform],
        timestamp=0,
    )

    physics.update(pet, snapshot, 0.1)

    assert pet.support_platform_id == "ground:test"
    assert pet.position.y == 60
    assert pet.velocity.y == 0
