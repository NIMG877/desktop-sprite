from desktop_sprite.core.physics_engine import PhysicsEngine
from desktop_sprite.environment.environment_snapshot import EnvironmentSnapshot
from desktop_sprite.models.geometry import Rect, Vec2
from desktop_sprite.models.state import Pet, PetState
from desktop_sprite.utils.config import PhysicsConfig


def test_pet_cannot_fall_below_work_area_floor_without_platforms():
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
        position=Vec2(50, 180),
        velocity=Vec2(0, 800),
        width=40,
        height=60,
        state=PetState.FALL,
    )
    snapshot = EnvironmentSnapshot(
        screen_rect=Rect.from_xywh(0, 0, 300, 260),
        work_area_rect=Rect.from_xywh(0, 0, 300, 220),
        taskbar_rect=None,
        windows=[],
        platforms=[],
        timestamp=0,
    )

    physics.update(pet, snapshot, 0.2)

    assert pet.position.y == 160
    assert pet.velocity.y == 0
    assert pet.support_platform_id == "ground:work_area"
    assert pet.state == PetState.IDLE


def test_already_below_floor_falling_pet_is_clamped_immediately():
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
        position=Vec2(50, 250),
        velocity=Vec2(0, 0),
        width=40,
        height=60,
        state=PetState.FALL,
    )
    snapshot = EnvironmentSnapshot(
        screen_rect=Rect.from_xywh(0, 0, 300, 320),
        work_area_rect=Rect.from_xywh(0, 0, 300, 220),
        taskbar_rect=None,
        windows=[],
        platforms=[],
        timestamp=0,
    )

    physics.update(pet, snapshot, 0.016)

    assert pet.bottom == 220
    assert pet.position.y == 160
    assert pet.state == PetState.IDLE


def test_dragged_pet_is_clamped_to_work_area_floor():
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
        position=Vec2(50, 190),
        velocity=Vec2(0, 0),
        width=40,
        height=60,
        state=PetState.DRAGGED,
    )
    snapshot = EnvironmentSnapshot(
        screen_rect=Rect.from_xywh(0, 0, 300, 260),
        work_area_rect=Rect.from_xywh(0, 0, 300, 220),
        taskbar_rect=None,
        windows=[],
        platforms=[],
        timestamp=0,
    )

    physics.update(pet, snapshot, 0.016)

    assert pet.bottom == 220
    assert pet.position.y == 160


def test_pet_cannot_move_above_work_area_top():
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
        position=Vec2(50, -30),
        velocity=Vec2(0, -500),
        width=40,
        height=60,
        state=PetState.FALL,
    )
    snapshot = EnvironmentSnapshot(
        screen_rect=Rect.from_xywh(0, 0, 300, 260),
        work_area_rect=Rect.from_xywh(0, 10, 300, 220),
        taskbar_rect=None,
        windows=[],
        platforms=[],
        timestamp=0,
    )

    physics.update(pet, snapshot, 0.016)

    assert pet.position.y == 10
    assert pet.velocity.y == 0
