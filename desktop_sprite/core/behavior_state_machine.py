from __future__ import annotations

from desktop_sprite.models.state import PetState


ALLOWED_TRANSITIONS: dict[PetState, set[PetState]] = {
    PetState.IDLE: {PetState.WALK, PetState.JUMP, PetState.FALL, PetState.DRAGGED, PetState.SLEEP, PetState.OPEN_WINGS},
    PetState.WALK: {PetState.IDLE, PetState.JUMP, PetState.CLIMB, PetState.FALL, PetState.DRAGGED, PetState.SLEEP, PetState.OPEN_WINGS},
    PetState.JUMP: {PetState.CLIMB, PetState.FALL, PetState.IDLE, PetState.WALK, PetState.DRAGGED, PetState.OPEN_WINGS},
    PetState.CLIMB: {PetState.IDLE, PetState.WALK, PetState.FALL, PetState.DRAGGED, PetState.OPEN_WINGS},
    PetState.FALL: {PetState.IDLE, PetState.WALK, PetState.CLIMB, PetState.DRAGGED, PetState.OPEN_WINGS},
    PetState.DRAGGED: {PetState.FALL, PetState.OPEN_WINGS},
    PetState.SLEEP: {PetState.IDLE, PetState.WALK, PetState.DRAGGED, PetState.FALL, PetState.OPEN_WINGS},
    PetState.OPEN_WINGS: {PetState.FLY, PetState.IDLE},
    PetState.FLY: {PetState.HOVER, PetState.IDLE},
    PetState.HOVER: {PetState.WING_LAND, PetState.IDLE},
    PetState.WING_LAND: {PetState.CLOSE_WINGS, PetState.IDLE},
    PetState.CLOSE_WINGS: {PetState.IDLE},
}


class BehaviorStateMachine:
    def __init__(self, initial_state: PetState = PetState.FALL) -> None:
        self.state = initial_state

    def can_transition(self, target: PetState) -> bool:
        return target == self.state or target in ALLOWED_TRANSITIONS[self.state]

    def transition(self, target: PetState) -> bool:
        if not self.can_transition(target):
            return False
        self.state = target
        return True
