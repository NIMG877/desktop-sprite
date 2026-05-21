from desktop_sprite.core.behavior_state_machine import BehaviorStateMachine
from desktop_sprite.models.state import PetState


def test_allowed_dragged_to_fall_transition():
    machine = BehaviorStateMachine(PetState.DRAGGED)

    assert machine.transition(PetState.FALL)
    assert machine.state == PetState.FALL


def test_blocks_unexpected_sleep_to_climb_transition():
    machine = BehaviorStateMachine(PetState.SLEEP)

    assert not machine.transition(PetState.CLIMB)
    assert machine.state == PetState.SLEEP


def test_walk_can_jump_before_climbing():
    machine = BehaviorStateMachine(PetState.WALK)

    assert machine.transition(PetState.JUMP)
    assert machine.state == PetState.JUMP
