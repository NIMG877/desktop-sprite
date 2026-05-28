from desktop_sprite.models.geometry import Vec2
from desktop_sprite.models.state import Pet, PetState
from desktop_sprite.core.animation_player import DEFAULT_ANIMATIONS
from desktop_sprite.ui.render_pose import PoseBuilder


def make_pet(state: PetState, velocity: Vec2 | None = None) -> Pet:
    return Pet(
        position=Vec2(0, 0),
        velocity=velocity or Vec2(),
        width=84,
        height=104,
        state=state,
    )


def test_fall_pose_gets_more_stretched_as_downward_velocity_increases():
    builder = PoseBuilder()
    slow = builder.build(make_pet(PetState.FALL, Vec2(0, 100)), phase=0.25, width=84, height=104)
    fast = builder.build(make_pet(PetState.FALL, Vec2(0, 1000)), phase=0.25, width=84, height=104)

    assert fast.body.front.height > slow.body.front.height
    assert fast.scarf.tail_tip.y < slow.scarf.tail_tip.y
    assert fast.shadow.opacity < slow.shadow.opacity


def test_climb_pose_alternates_hand_and_foot_targets():
    builder = PoseBuilder()
    pet = make_pet(PetState.CLIMB)
    first = builder.build(pet, phase=0.0, width=84, height=104)
    second = builder.build(pet, phase=0.25, width=84, height=104)

    assert first.edge_line is None
    assert len({round(limb.end.x, 4) for limb in first.limbs}) == 1
    assert len({round(limb.end.x, 4) for limb in second.limbs}) == 1
    assert first.limbs[0].end.y != second.limbs[0].end.y
    assert first.limbs[2].end.y != second.limbs[2].end.y


def test_walk_pose_has_opposed_feet():
    builder = PoseBuilder()
    pet = make_pet(PetState.WALK, Vec2(120, 0))
    pose = builder.build(pet, phase=0.25, width=84, height=104)

    left_foot = pose.limbs[2].end
    right_foot = pose.limbs[3].end
    assert left_foot.y > right_foot.y


def test_jump_pose_raises_hands_and_tucks_feet():
    builder = PoseBuilder()
    pet = make_pet(PetState.JUMP, Vec2(120, -520))
    pose = builder.build(pet, phase=0.25, width=84, height=104)

    assert pose.limbs[0].end.y < pose.body.front.y
    assert pose.limbs[1].end.y < pose.body.front.y
    assert pose.limbs[2].end.y < 104 * 0.86
    assert pose.scarf.tail_tip.y < 104 * 0.50


def test_show_pose_uses_requested_body_size():
    builder = PoseBuilder()
    pet = make_pet(PetState.HOVER)

    pose = builder.build(pet, phase=0.25, width=84, height=104)

    assert pose.body.front.width < 84
    assert pose.body.front.height < 104
    assert pose.wings is not None


def test_show_wing_lower_edges_stay_within_show_canvas_margin():
    builder = PoseBuilder()
    pet = make_pet(PetState.FLY)

    pose = builder.build(pet, phase=0.25, width=84, height=104)

    assert pose.wings is not None
    assert pose.wings.left_lower.y < 104 * 1.6
    assert pose.wings.right_lower.y < 104 * 1.6


def test_wing_downstroke_is_faster_than_upstroke():
    builder = PoseBuilder()
    pet = make_pet(PetState.HOVER)

    down_start = builder.build(pet, phase=0.04, width=84, height=104)
    down_end = builder.build(pet, phase=0.20, width=84, height=104)
    up_start = builder.build(pet, phase=0.48, width=84, height=104)
    up_end = builder.build(pet, phase=0.64, width=84, height=104)

    assert down_start.wings is not None
    assert down_end.wings is not None
    assert up_start.wings is not None
    assert up_end.wings is not None

    down_distance = down_end.wings.left_tip.y - down_start.wings.left_tip.y
    up_distance = up_start.wings.left_tip.y - up_end.wings.left_tip.y
    assert down_distance > up_distance


def test_fly_wing_downstroke_has_stronger_amplitude():
    builder = PoseBuilder()

    hover = builder.build(make_pet(PetState.HOVER), phase=0.32, width=84, height=104)
    fly = builder.build(make_pet(PetState.FLY), phase=0.32, width=84, height=104)
    hover_up = builder.build(make_pet(PetState.HOVER), phase=0.0, width=84, height=104)
    fly_up = builder.build(make_pet(PetState.FLY), phase=0.0, width=84, height=104)

    assert hover.wings is not None
    assert fly.wings is not None
    assert hover_up.wings is not None
    assert fly_up.wings is not None
    assert fly.wings.left_tip.y > hover.wings.left_tip.y
    assert fly.wings.right_tip.y > hover.wings.right_tip.y
    assert fly_up.wings.left_tip.y > hover_up.wings.left_tip.y
    assert fly_up.wings.right_tip.y > hover_up.wings.right_tip.y


def test_fly_and_land_flap_frequency_only_slightly_exceeds_hover():
    hover = DEFAULT_ANIMATIONS[PetState.HOVER]
    fly = DEFAULT_ANIMATIONS[PetState.FLY]
    land = DEFAULT_ANIMATIONS[PetState.WING_LAND]

    hover_frequency = hover.fps / hover.frame_count
    fly_frequency = fly.fps / fly.frame_count
    land_frequency = land.fps / land.frame_count

    assert hover_frequency < fly_frequency <= hover_frequency * 1.15
    assert hover_frequency < land_frequency <= hover_frequency * 1.15


def test_previous_open_wings_pose_uses_previous_elapsed_when_state_time_resets():
    builder = PoseBuilder()
    pet = make_pet(PetState.FLY)
    pet.state_time = 0.0

    previous_pose = builder.build(
        pet,
        phase=0.99,
        width=84,
        height=104,
        state=PetState.OPEN_WINGS,
        state_elapsed=0.7,
    )

    assert previous_pose.wings is not None
    assert previous_pose.wings.openness == 1.0
    assert previous_pose.wings.opacity == 225
