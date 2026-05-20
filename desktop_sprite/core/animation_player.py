from __future__ import annotations

from dataclasses import dataclass

from desktop_sprite.models.state import PetState


@dataclass(frozen=True, slots=True)
class AnimationSpec:
    fps: float
    frame_count: int
    loop: bool = True


DEFAULT_ANIMATIONS: dict[PetState, AnimationSpec] = {
    PetState.IDLE: AnimationSpec(fps=4, frame_count=8),
    PetState.WALK: AnimationSpec(fps=10, frame_count=6),
    PetState.MOVE_TO_TARGET: AnimationSpec(fps=10, frame_count=6),
    PetState.CLIMB: AnimationSpec(fps=8, frame_count=4),
    PetState.FALL: AnimationSpec(fps=6, frame_count=3),
    PetState.DRAGGED: AnimationSpec(fps=5, frame_count=2),
    PetState.SLEEP: AnimationSpec(fps=2, frame_count=4),
}


class AnimationPlayer:
    def __init__(self) -> None:
        self.state = PetState.IDLE
        self.elapsed = 0.0
        self.frame_index = 0

    def set_state(self, state: PetState) -> None:
        if state == self.state:
            return
        self.state = state
        self.elapsed = 0.0
        self.frame_index = 0

    def update(self, dt: float) -> int:
        spec = DEFAULT_ANIMATIONS[self.state]
        self.elapsed += dt
        self.frame_index = int(self.elapsed * spec.fps)
        if spec.loop:
            self.frame_index %= spec.frame_count
        else:
            self.frame_index = min(self.frame_index, spec.frame_count - 1)
        return self.frame_index

    @property
    def phase(self) -> float:
        spec = DEFAULT_ANIMATIONS[self.state]
        return self.frame_index / max(spec.frame_count - 1, 1)
