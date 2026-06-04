"""Show-mode director.

The Show sequence (open wings → fly → hover → title → land → close
wings) used to live as `_start_*` and `_update_show` methods on
`PetController`, mixed in with the controller's main loop. This module
extracts that subsystem into its own class.

The director is intentionally thin on state: it does not own the
pet, the mode controller, or the orchestrator. Instead, the controller
hands the director a `ShowContext` and a reference to itself, and the
director mutates the controller's `pet`, `_active_pet_ability`, and
mode/orchestrator state directly. This preserves the original mutation
surface so existing code — including the very fragile
`test_pet_controller_climb_reach.py` — can still read those fields.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from desktop_sprite.core.behavior_orchestrator import BehaviorPhaseName
from desktop_sprite.core.pet_mode import PetMode
from desktop_sprite.core.show_phase_durations import (
    SHOW_HOVER_SECONDS,
    SHOW_RENDER_SCALE_X,
    SHOW_RENDER_SCALE_Y,
    SHOW_TITLE_SECONDS,
)
from desktop_sprite.models.geometry import Vec2
from desktop_sprite.models.state import Facing, PetState


# Re-exported here so the public surface stays at the import site the
# fragile climb-reach test uses (`from desktop_sprite.core
# .pet_controller import HoverAbility, WingAbility, SHOW_HOVER_SECONDS`).
__all__ = [
    "FlightAbility",
    "HoverAbility",
    "PetAbility",
    "ShowContext",
    "WingAbility",
    "SHOW_HOVER_SECONDS",
]


@dataclass(slots=True)
class ShowContext:
    start_x: float
    start_y: float
    hover_x: float
    hover_y: float
    land_x: float
    land_y: float
    render_width: int
    render_height: int


@dataclass(slots=True)
class WingAbility:
    state: PetState
    duration: float
    elapsed: float = 0.0


@dataclass(slots=True)
class FlightAbility:
    start_x: float
    start_y: float
    target_x: float
    target_y: float
    speed: float
    state: PetState


@dataclass(slots=True)
class HoverAbility:
    base_x: float
    base_y: float
    duration: float | None = None
    elapsed: float = 0.0


PetAbility = WingAbility | FlightAbility | HoverAbility


class PetShowDirector:
    """Drive the Show sequence for a `PetController`.

    The director is instantiated once per controller; it holds no
    per-show state of its own. The controller passes itself in along
    with a `ShowContext` to begin a Show, then calls `update(dt)` each
    frame until the sequence completes.
    """

    def start(self, controller, context: ShowContext) -> None:
        """Reset per-show fields on the controller and kick off wings-open."""

        controller.path_plan = None
        controller.pet.target_window_id = None
        controller.pet.support_surface_id = None
        controller.pet.target_surface_id = None
        controller.pet.velocity = Vec2()
        controller._active_pet_ability = None
        self._start_phase_ability(controller, BehaviorPhaseName.SHOW_OPEN_WINGS, context)

    def update(self, controller, dt: float) -> bool:
        """Advance the Show sequence by one frame.

        Returns `True` when the sequence has finished so the controller
        can fall out of Show mode.
        """

        context: ShowContext | None = getattr(controller, "_show_context", None)
        if context is None:
            return True  # Nothing to do; controller will call finish().

        phase = controller.orchestrator.phase.name
        if controller.orchestrator.is_sequence_complete():
            return True

        if controller._active_pet_ability is None:
            self._start_phase_ability(controller, phase, context)

        ability_done = self._update_ability(controller, dt)

        # Special-case: the hover phase needs a fixed minimum hold so
        # the title overlay gets a chance to appear above the sprite.
        if phase == BehaviorPhaseName.SHOW_HOVER and isinstance(
            controller._active_pet_ability, HoverAbility
        ):
            if controller._active_pet_ability.elapsed >= SHOW_HOVER_SECONDS:
                controller.orchestrator.advance_sequence()

        if ability_done:
            controller._active_pet_ability = None
            controller.orchestrator.advance_sequence()

        return controller.orchestrator.is_sequence_complete()

    def finish(self, controller) -> None:
        """Place the pet at the landing point and unlock Show mode."""

        context: ShowContext | None = getattr(controller, "_show_context", None)
        if context is not None:
            controller.pet.position = Vec2(context.land_x, context.land_y)
        controller._show_context = None
        controller._active_pet_ability = None
        controller.pet.velocity = Vec2()
        controller.pet.support_surface_id = None
        controller.pet.target_surface_id = None
        controller.mode_controller.unlock()
        controller.mode_controller.set_mode(PetMode.IDLE, force=True)
        controller.orchestrator.begin(BehaviorPhaseName.IDLE_WAIT)
        controller._transition(PetState.IDLE)
        controller._pick_new_idle_goal()

    # ------------------------------------------------------------------
    # Phase → ability dispatch
    # ------------------------------------------------------------------

    def _start_phase_ability(
        self, controller, phase: BehaviorPhaseName | str, context: ShowContext
    ) -> None:
        if phase == BehaviorPhaseName.SHOW_OPEN_WINGS:
            self._start_open_wings(controller)
            controller.pet.position = Vec2(context.start_x, context.start_y)
            return
        if phase == BehaviorPhaseName.SHOW_FLY:
            self._start_flight_to(
                controller,
                context.hover_x,
                context.hover_y,
                state=PetState.FLY,
                speed=controller.effective_stats().flight_speed
                * controller._resource_influence().special_factor,
            )
            return
        if phase == BehaviorPhaseName.SHOW_HOVER:
            self._start_hover(
                controller, context.hover_x, context.hover_y, SHOW_HOVER_SECONDS + SHOW_TITLE_SECONDS
            )
            return
        if phase == BehaviorPhaseName.SHOW_TITLE:
            if not isinstance(controller._active_pet_ability, HoverAbility):
                self._start_hover(controller, context.hover_x, context.hover_y, SHOW_TITLE_SECONDS)
            return
        if phase == BehaviorPhaseName.SHOW_LAND:
            self._start_flight_to(
                controller,
                context.land_x,
                context.land_y,
                state=PetState.WING_LAND,
                speed=controller.effective_stats().landing_speed
                * controller._resource_influence().special_factor,
            )
            return
        if phase == BehaviorPhaseName.SHOW_CLOSE_WINGS:
            controller.pet.position = Vec2(context.land_x, context.land_y)
            self._start_close_wings(controller)

    # ------------------------------------------------------------------
    # Ability primitives
    # ------------------------------------------------------------------

    def _start_open_wings(self, controller) -> None:
        controller._transition(PetState.OPEN_WINGS)
        controller.pet.velocity = Vec2()
        duration = controller.effective_stats().wing_open_seconds / max(
            controller._resource_influence().special_factor, 0.25
        )
        controller._active_pet_ability = WingAbility(PetState.OPEN_WINGS, duration)

    def _start_close_wings(self, controller) -> None:
        controller._transition(PetState.CLOSE_WINGS)
        controller.pet.velocity = Vec2()
        duration = controller.effective_stats().wing_close_seconds / max(
            controller._resource_influence().special_factor, 0.25
        )
        controller._active_pet_ability = WingAbility(PetState.CLOSE_WINGS, duration)

    def _start_flight_to(
        self,
        controller,
        target_x: float,
        target_y: float,
        *,
        state: PetState,
        speed: float,
    ) -> None:
        controller._transition(state)
        controller.pet.support_surface_id = None
        controller.pet.target_surface_id = None
        controller._active_pet_ability = FlightAbility(
            start_x=controller.pet.position.x,
            start_y=controller.pet.position.y,
            target_x=target_x,
            target_y=target_y,
            speed=max(speed, 1.0),
            state=state,
        )

    def _start_hover(
        self, controller, base_x: float, base_y: float, duration: float | None = None
    ) -> None:
        controller._transition(PetState.HOVER)
        controller.pet.velocity = Vec2()
        controller._active_pet_ability = HoverAbility(
            base_x,
            base_y,
            None if duration is None else max(duration, 0.0),
        )

    def _update_ability(self, controller, dt: float) -> bool:
        ability = controller._active_pet_ability
        if ability is None:
            return True
        if isinstance(ability, WingAbility):
            ability.elapsed += max(dt, 0.0)
            return ability.elapsed >= ability.duration
        if isinstance(ability, FlightAbility):
            return self._update_flight(controller, ability, dt)
        if isinstance(ability, HoverAbility):
            return self._update_hover(controller, ability, dt)
        return True

    def _update_flight(self, controller, ability: FlightAbility, dt: float) -> bool:
        dx = ability.target_x - controller.pet.position.x
        dy = ability.target_y - controller.pet.position.y
        distance = math.hypot(dx, dy)
        if distance <= 0.001:
            controller.pet.position = Vec2(ability.target_x, ability.target_y)
            controller.pet.velocity = Vec2()
            return True

        step = ability.speed * max(dt, 0.0)
        if step >= distance:
            controller.pet.position = Vec2(ability.target_x, ability.target_y)
            controller.pet.velocity = Vec2()
            return True

        direction_x = dx / distance
        direction_y = dy / distance
        controller.pet.position.x += direction_x * step
        controller.pet.position.y += direction_y * step
        controller.pet.velocity = Vec2(direction_x * ability.speed, direction_y * ability.speed)
        controller.pet.facing = Facing.RIGHT if direction_x >= 0 else Facing.LEFT
        return False

    def _update_hover(self, controller, ability: HoverAbility, dt: float) -> bool:
        ability.elapsed += max(dt, 0.0)
        influence = controller._resource_influence()
        controller.pet.position = Vec2(
            ability.base_x,
            ability.base_y
            + math.sin(
                ability.elapsed
                * controller.effective_stats().hover_frequency
                * max(influence.special_factor, 0.25)
            )
            * controller.effective_stats().hover_amplitude
            * influence.special_factor,
        )
        if ability.duration is None:
            return False
        return ability.elapsed >= ability.duration
