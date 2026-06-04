"""Pet state mediator.

The pet runtime historically kept three pieces of state in lockstep:

* `Pet.state` — the canonical state on the entity.
* `BehaviorStateMachine.state` — the legal-transition table that
  guards every change.
* `BehaviorOrchestrator.phase.name` — the high-level "what are we
  doing" pointer (idle / path executing / show phase).
* `ModeController.mode` / `locked` — the coarse-grain mode lock
  (idle / go-to-target / show).

These four fields were manually re-synced at every transition in
`PetController._transition` and `start_show` / `_finish_show`. The
mediator centralises that bookkeeping: callers ask the mediator to
transition and the mediator is responsible for keeping the four
fields consistent.

The mediator is intentionally narrow. It does not own the physics,
the path finder, or the path executor — those subsystems are still
addressed directly via `controller.pet`, `controller.pathfinder`, etc.
"""

from __future__ import annotations

from desktop_sprite.core.behavior_orchestrator import BehaviorOrchestrator
from desktop_sprite.core.behavior_state_machine import BehaviorStateMachine
from desktop_sprite.core.pet_mode import ModeController, PetMode
from desktop_sprite.models.state import Pet, PetState


class PetStateMediator:
    """Single source of truth for the pet's state machine and mode.

    The mediator is a plain data holder. `PetController` (and the
    `PetShowDirector` it composes) read its fields and call its
    methods; nothing else mutates `pet.state` or `state_machine.state`.
    """

    def __init__(
        self,
        pet: Pet,
        state_machine: BehaviorStateMachine,
        orchestrator: BehaviorOrchestrator,
        mode_controller: ModeController,
    ) -> None:
        self.pet = pet
        self.state_machine = state_machine
        self.orchestrator = orchestrator
        self.mode_controller = mode_controller

    # ------------------------------------------------------------------
    # State machine — single transition path
    # ------------------------------------------------------------------

    def transition(self, target: PetState) -> bool:
        """Try to transition `pet.state` to `target`.

        Mirrors the original `PetController._transition` semantics:
        1. Sync the state machine's internal state from the pet.
        2. Ask the state machine to validate + advance.
        3. If the transition succeeded, write it back to the pet and
           reset `pet.state_time`.
        """

        self.state_machine.state = self.pet.state
        if self.state_machine.transition(target):
            self.pet.state = target
            self.pet.state_time = 0.0
            return True
        return False

    def snapshot_state(self) -> None:
        """Re-sync the state machine to the pet's current state.

        Use this when the pet's state has been mutated by a system
        that does not go through the mediator (e.g. the physics
        engine after P0-D).
        """

        self.state_machine.state = self.pet.state

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    @property
    def is_show(self) -> bool:
        return self.mode_controller.is_show()

    @property
    def is_dragged(self) -> bool:
        return self.pet.state == PetState.DRAGGED

    @property
    def mode(self) -> PetMode:
        return self.mode_controller.mode

    @property
    def mode_locked(self) -> bool:
        return self.mode_controller.locked

    @property
    def phase_name(self) -> str:
        return self.orchestrator.phase.name

    @property
    def phase_elapsed(self) -> float:
        return self.orchestrator.phase.elapsed

    # ------------------------------------------------------------------
    # Orchestrator & mode passthroughs
    # ------------------------------------------------------------------

    def begin_phase(self, name) -> None:
        self.orchestrator.begin(name)

    def advance_phase(self, name) -> None:
        self.orchestrator.advance(name)

    def begin_show(self) -> None:
        self.orchestrator.begin_show()

    def advance_sequence(self) -> None:
        self.orchestrator.advance_sequence()

    def is_sequence_complete(self) -> bool:
        return self.orchestrator.is_sequence_complete()

    def set_mode(self, mode: PetMode, *, force: bool = False, lock: bool = False) -> bool:
        return self.mode_controller.set_mode(mode, force=force, lock=lock)

    def unlock(self) -> None:
        self.mode_controller.unlock()

    def unlock_and_idle(self) -> None:
        """Show-mode teardown helper: drop the lock and return to idle."""

        self.mode_controller.unlock()
        self.mode_controller.set_mode(PetMode.IDLE, force=True)
