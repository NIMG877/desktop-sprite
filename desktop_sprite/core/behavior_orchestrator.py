from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class BehaviorPhaseName(StrEnum):
    IDLE_WAIT = "idle_wait"
    PATH_PLANNING = "path_planning"
    PATH_EXECUTING = "path_executing"
    PATH_FINISHED = "path_finished"
    SHOW_OPEN_WINGS = "show_open_wings"
    SHOW_FLY = "show_fly"
    SHOW_HOVER = "show_hover"
    SHOW_TITLE = "show_title"
    SHOW_LAND = "show_land"
    SHOW_CLOSE_WINGS = "show_close_wings"


SHOW_PHASE_SEQUENCE: tuple[BehaviorPhaseName, ...] = (
    BehaviorPhaseName.SHOW_OPEN_WINGS,
    BehaviorPhaseName.SHOW_FLY,
    BehaviorPhaseName.SHOW_HOVER,
    BehaviorPhaseName.SHOW_TITLE,
    BehaviorPhaseName.SHOW_LAND,
    BehaviorPhaseName.SHOW_CLOSE_WINGS,
)


@dataclass(slots=True)
class BehaviorPhase:
    name: BehaviorPhaseName | str
    elapsed: float = 0.0


class BehaviorOrchestrator:
    def __init__(self, initial_phase: BehaviorPhaseName | str = BehaviorPhaseName.IDLE_WAIT) -> None:
        self.phase = BehaviorPhase(initial_phase)
        self._sequence: tuple[BehaviorPhaseName, ...] = ()
        self._sequence_index = 0
        self._sequence_complete = False

    def begin(self, name: BehaviorPhaseName | str) -> None:
        self.phase = BehaviorPhase(name)
        self._sequence = ()
        self._sequence_index = 0
        self._sequence_complete = False

    def advance(self, name: BehaviorPhaseName | str) -> None:
        self.begin(name)

    def tick(self, dt: float) -> None:
        self.phase.elapsed += max(dt, 0.0)
        self._advance_sequence_if_needed()

    def reset(self) -> None:
        self.begin(BehaviorPhaseName.IDLE_WAIT)

    def begin_show(self) -> None:
        self._sequence = SHOW_PHASE_SEQUENCE
        self._sequence_index = 0
        self._sequence_complete = False
        self.phase = BehaviorPhase(self._sequence[self._sequence_index])

    def is_sequence_complete(self) -> bool:
        return self._sequence_complete

    def phase_duration(self) -> float | None:
        return None

    def phase_progress(self) -> float:
        duration = self.phase_duration()
        if duration is None or duration <= 0:
            return 0.0
        return min(max(self.phase.elapsed / duration, 0.0), 1.0)

    def advance_sequence(self) -> None:
        if not self._sequence or self._sequence_complete:
            return
        if self._sequence_index >= len(self._sequence) - 1:
            self._sequence_complete = True
            return
        self._sequence_index += 1
        self.phase = BehaviorPhase(self._sequence[self._sequence_index])

    def _advance_sequence_if_needed(self) -> None:
        if not self._sequence or self._sequence_complete:
            return
        while True:
            duration = self.phase_duration()
            if duration is None or self.phase.elapsed < duration:
                return
            overflow = self.phase.elapsed - duration
            if self._sequence_index >= len(self._sequence) - 1:
                self.phase.elapsed = duration
                self._sequence_complete = True
                return
            self._sequence_index += 1
            self.phase = BehaviorPhase(self._sequence[self._sequence_index], overflow)
