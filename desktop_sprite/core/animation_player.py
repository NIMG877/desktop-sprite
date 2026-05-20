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
    PetState.JUMP: AnimationSpec(fps=8, frame_count=5),
    PetState.CLIMB: AnimationSpec(fps=8, frame_count=4),
    PetState.FALL: AnimationSpec(fps=6, frame_count=3),
    PetState.DRAGGED: AnimationSpec(fps=5, frame_count=2),
    PetState.SLEEP: AnimationSpec(fps=2, frame_count=4),
}


class AnimationPlayer:
    def __init__(self) -> None:
        self.state = PetState.IDLE
        self.previous_state: PetState | None = None
        self.elapsed = 0.0
        self.previous_elapsed = 0.0
        self.transition_elapsed = 1.0
        self.transition_duration = 0.14
        self.frame_index = 0

    def set_state(self, state: PetState) -> None:
        if state == self.state:
            return
        self.previous_state = self.state
        self.previous_elapsed = self.elapsed
        self.transition_elapsed = 0.0
        self.state = state
        self.elapsed = 0.0
        self.frame_index = 0

    def update(self, dt: float) -> int:
        spec = DEFAULT_ANIMATIONS[self.state]
        self.elapsed += dt
        self.previous_elapsed += dt
        self.transition_elapsed += dt
        self.frame_index = int(self.elapsed * spec.fps)
        if spec.loop:
            self.frame_index %= spec.frame_count
        else:
            self.frame_index = min(self.frame_index, spec.frame_count - 1)
        return self.frame_index

    @property
    def phase(self) -> float:
        return self._phase_for(self.state, self.elapsed)

    @property
    def previous_phase(self) -> float:
        if self.previous_state is None:
            return self.phase
        return self._phase_for(self.previous_state, self.previous_elapsed)

    @property
    def blend_alpha(self) -> float:
        if self.previous_state is None:
            return 1.0
        raw = min(max(self.transition_elapsed / self.transition_duration, 0.0), 1.0)
        return raw * raw * (3.0 - 2.0 * raw)

    def _phase_for(self, state: PetState, elapsed: float) -> float:
        spec = DEFAULT_ANIMATIONS[state]
        cycle_position = elapsed * spec.fps / max(spec.frame_count, 1)
        if spec.loop:
            return cycle_position % 1.0
        return min(cycle_position, 1.0)
