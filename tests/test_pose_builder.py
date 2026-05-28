from desktop_sprite.models.geometry import Vec2
from desktop_sprite.models.state import Pet, PetState
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


def test_show_wing_lower_edges_stay_near_pose_bounds():
    builder = PoseBuilder()
    pet = make_pet(PetState.FLY)

    pose = builder.build(pet, phase=0.25, width=84, height=104)

    assert pose.wings is not None
    assert pose.wings.left_lower.y < 104
    assert pose.wings.right_lower.y < 104
