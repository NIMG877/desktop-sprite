"""Behaviour phase orchestrator.

The orchestrator historically had a single class with two intertwined
responsibilities:

1. Tracking the **current phase** (a name + elapsed time).
2. Driving the **Show sequence** (a fixed list of phases, advanced
   step-by-step by the director).

The two concerns shared one mutable `self.phase` dataclass, which
meant the phase was simultaneously "what phase are we in" and
"which step of the Show sequence is active". This made the dispatch
key in `PetShowDirector._start_phase_ability` and the progress
indicator in `CharacterDebugState.phase` conflate two things.

P1-C splits the responsibilities into two collaborators:

* `BehaviorPhaseTracker` owns the active phase + elapsed time.
* `BehaviorSequence` owns the Show sequence pointer.

`BehaviorOrchestrator` is a facade that coordinates the two. Most
methods are pure delegations to either the tracker or the sequence
and go through `__getattr__`; the four methods that must mutate
both halves (`begin`, `begin_show`, `advance_sequence`, `reset`)
live as explicit methods because they are *coordinators*, not
forwarders.
"""

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


class BehaviorPhaseTracker:
    """Owns the active phase dataclass.

    A simple getter/setter for `phase` plus a `tick(dt)` that bumps
    the elapsed counter. No knowledge of sequences.
    """

    def __init__(self, initial_phase: BehaviorPhaseName | str = BehaviorPhaseName.IDLE_WAIT) -> None:
        self.phase = BehaviorPhase(initial_phase)

    def begin(self, name: BehaviorPhaseName | str) -> None:
        self.phase = BehaviorPhase(name)

    def advance(self, name: BehaviorPhaseName | str) -> None:
        self.begin(name)

    def tick(self, dt: float) -> None:
        self.phase.elapsed += max(dt, 0.0)

    def reset(self) -> None:
        self.begin(BehaviorPhaseName.IDLE_WAIT)


class BehaviorSequence:
    """Owns the Show-sequence pointer.

    Knows nothing about the active phase. The orchestrator is
    responsible for keeping the tracker's phase in sync with
    `current_phase_name()`.
    """

    def __init__(self) -> None:
        self._phases: tuple[BehaviorPhaseName, ...] = ()
        self._index: int = 0
        self._complete: bool = False

    def begin_show(self) -> None:
        self._phases = SHOW_PHASE_SEQUENCE
        self._index = 0
        self._complete = False

    def reset(self) -> None:
        self._phases = ()
        self._index = 0
        self._complete = False

    def is_complete(self) -> bool:
        return self._complete

    def current_phase_name(self) -> BehaviorPhaseName | None:
        if not self._phases or self._index >= len(self._phases):
            return None
        return self._phases[self._index]

    def advance(self) -> None:
        if not self._phases or self._complete:
            return
        if self._index >= len(self._phases) - 1:
            self._complete = True
            return
        self._index += 1


# Method names that the orchestrator forwards to the tracker without
# any extra logic. Living on the tracker directly keeps the facade
# thin while still exposing a single, consistent API surface.
_TRACKER_FORWARDED: frozenset[str] = frozenset({"tick", "advance"})


class BehaviorOrchestrator:
    """Facade over `BehaviorPhaseTracker` + `BehaviorSequence`.

    Public API:

    * `phase` — `@property` returning the tracker's active phase.
    * `begin(name)` / `begin_show()` / `advance_sequence()` /
      `reset()` — coordinators that mutate both halves.
    * `tick(dt)` / `advance(name)` — pure tracker delegations
      handled via `__getattr__`.
    * `is_sequence_complete()` — pure sequence delegation handled
      via `__getattr__`.
    """

    def __init__(self, initial_phase: BehaviorPhaseName | str = BehaviorPhaseName.IDLE_WAIT) -> None:
        self.tracker = BehaviorPhaseTracker(initial_phase)
        self.sequence = BehaviorSequence()

    # ------------------------------------------------------------------
    # Phase — must be a property so callers can read `.name`/`.elapsed`
    # and the old `orchestrator.phase = ...` setter still works.
    # ------------------------------------------------------------------

    @property
    def phase(self) -> BehaviorPhase:
        return self.tracker.phase

    @phase.setter
    def phase(self, value: BehaviorPhase) -> None:
        self.tracker.phase = value

    # ------------------------------------------------------------------
    # Coordinators — these mutate both halves and therefore cannot be
    # expressed as a single `__getattr__` forward.
    # ------------------------------------------------------------------

    def begin(self, name: BehaviorPhaseName | str) -> None:
        self.tracker.begin(name)
        self.sequence.reset()

    def begin_show(self) -> None:
        self.sequence.begin_show()
        first = self.sequence.current_phase_name()
        if first is not None:
            self.tracker.begin(first)

    def advance_sequence(self) -> None:
        self.sequence.advance()
        next_phase = self.sequence.current_phase_name()
        if next_phase is not None and not self.sequence.is_complete():
            self.tracker.begin(next_phase)

    def reset(self) -> None:
        self.tracker.reset()
        self.sequence.reset()

    # ------------------------------------------------------------------
    # Forwarders — `__getattr__` only fires on attribute miss, so the
    # methods defined above and the `phase` property are never
    # re-routed through it.
    # ------------------------------------------------------------------

    def __getattr__(self, name: str):
        if name in _TRACKER_FORWARDED:
            return getattr(self.tracker, name)
        if name == "is_sequence_complete":
            # The sequence exposes its query as `is_complete`; the
            # orchestrator's public name is `is_sequence_complete`
            # because the test surface asks for it that way. Forward
            # by translation rather than by attribute lookup so the
            # rename stays explicit.
            return self.sequence.is_complete
        raise AttributeError(name)
