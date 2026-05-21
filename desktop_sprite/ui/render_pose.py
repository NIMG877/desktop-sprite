from __future__ import annotations

import math
from dataclasses import dataclass

from desktop_sprite.models.state import Facing, Pet, PetState


def clamp(value: float, minimum: float, maximum: float) -> float:
    return min(max(value, minimum), maximum)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


@dataclass(frozen=True, slots=True)
class PosePoint:
    x: float
    y: float

    def blend(self, other: "PosePoint", t: float) -> "PosePoint":
        return PosePoint(lerp(self.x, other.x, t), lerp(self.y, other.y, t))


@dataclass(frozen=True, slots=True)
class PoseRect:
    x: float
    y: float
    width: float
    height: float

    def blend(self, other: "PoseRect", t: float) -> "PoseRect":
        return PoseRect(
            lerp(self.x, other.x, t),
            lerp(self.y, other.y, t),
            lerp(self.width, other.width, t),
            lerp(self.height, other.height, t),
        )


@dataclass(frozen=True, slots=True)
class LimbPose:
    root: PosePoint
    joint: PosePoint
    end: PosePoint
    radius: float
    terminal_radius: float

    def blend(self, other: "LimbPose", t: float) -> "LimbPose":
        return LimbPose(
            self.root.blend(other.root, t),
            self.joint.blend(other.joint, t),
            self.end.blend(other.end, t),
            lerp(self.radius, other.radius, t),
            lerp(self.terminal_radius, other.terminal_radius, t),
        )


@dataclass(frozen=True, slots=True)
class BodyPose:
    back: PoseRect
    front: PoseRect
    highlight: PoseRect

    def blend(self, other: "BodyPose", t: float) -> "BodyPose":
        return BodyPose(
            self.back.blend(other.back, t),
            self.front.blend(other.front, t),
            self.highlight.blend(other.highlight, t),
        )


@dataclass(frozen=True, slots=True)
class EyePose:
    left: PoseRect
    right: PoseRect
    left_highlight: PoseRect
    right_highlight: PoseRect
    sleeping: bool = False

    def blend(self, other: "EyePose", t: float) -> "EyePose":
        return EyePose(
            self.left.blend(other.left, t),
            self.right.blend(other.right, t),
            self.left_highlight.blend(other.left_highlight, t),
            self.right_highlight.blend(other.right_highlight, t),
            sleeping=other.sleeping if t >= 0.5 else self.sleeping,
        )


@dataclass(frozen=True, slots=True)
class ScarfPose:
    band: PoseRect
    tail_a: PosePoint
    tail_tip: PosePoint
    tail_b: PosePoint

    def blend(self, other: "ScarfPose", t: float) -> "ScarfPose":
        return ScarfPose(
            self.band.blend(other.band, t),
            self.tail_a.blend(other.tail_a, t),
            self.tail_tip.blend(other.tail_tip, t),
            self.tail_b.blend(other.tail_b, t),
        )


@dataclass(frozen=True, slots=True)
class ShadowPose:
    ellipse: PoseRect
    opacity: int

    def blend(self, other: "ShadowPose", t: float) -> "ShadowPose":
        return ShadowPose(self.ellipse.blend(other.ellipse, t), round(lerp(self.opacity, other.opacity, t)))


@dataclass(frozen=True, slots=True)
class RenderPose:
    facing: Facing
    offset: PosePoint
    rotation: float
    body: BodyPose
    eyes: EyePose
    scarf: ScarfPose
    shadow: ShadowPose
    limbs: tuple[LimbPose, LimbPose, LimbPose, LimbPose]
    edge_line: tuple[PosePoint, PosePoint] | None = None

    def blend(self, other: "RenderPose", t: float) -> "RenderPose":
        return RenderPose(
            facing=other.facing,
            offset=self.offset.blend(other.offset, t),
            rotation=lerp(self.rotation, other.rotation, t),
            body=self.body.blend(other.body, t),
            eyes=self.eyes.blend(other.eyes, t),
            scarf=self.scarf.blend(other.scarf, t),
            shadow=self.shadow.blend(other.shadow, t),
            limbs=tuple(a.blend(b, t) for a, b in zip(self.limbs, other.limbs)),  # type: ignore[arg-type]
            edge_line=other.edge_line if t >= 0.5 else self.edge_line,
        )


class PoseBuilder:
    def build(self, pet: Pet, phase: float, width: int, height: int, state: PetState | None = None) -> RenderPose:
        resolved_state = state or pet.state
        cycle = phase * math.tau
        speed = clamp(abs(pet.velocity.x) / 160.0, 0.0, 1.6)
        fall_strength = clamp(max(pet.velocity.y, 0.0) / 1000.0, 0.0, 1.25)

        body = self._body(resolved_state, width, height, fall_strength)
        offset = self._offset(resolved_state, cycle, speed, fall_strength)
        rotation = self._rotation(resolved_state, pet, fall_strength)
        limbs = self._limbs(resolved_state, cycle, speed, fall_strength, width, height)
        scarf = self._scarf(resolved_state, cycle, width, height, fall_strength)
        eyes = self._eyes(resolved_state, cycle, width, height, fall_strength)
        shadow = self._shadow(resolved_state, width, height, fall_strength)

        return RenderPose(
            facing=pet.facing,
            offset=offset,
            rotation=rotation,
            body=body,
            eyes=eyes,
            scarf=scarf,
            shadow=shadow,
            limbs=limbs,
            edge_line=None,
        )

    def _offset(self, state: PetState, cycle: float, speed: float, fall_strength: float) -> PosePoint:
        if state == PetState.WALK:
            return PosePoint(math.sin(cycle) * 1.5 * speed, math.sin(cycle * 2.0) * 2.4 * speed)
        if state == PetState.JUMP:
            return PosePoint(math.sin(cycle) * 1.0, -3.0 + math.sin(cycle * 1.5) * 1.2)
        if state == PetState.IDLE:
            return PosePoint(math.sin(cycle * 0.7) * 0.9, math.sin(cycle) * 1.8)
        if state == PetState.CLIMB:
            return PosePoint(2.5, math.sin(cycle) * 3.2)
        if state == PetState.FALL:
            return PosePoint(0.0, 5.0 + fall_strength * 2.0)
        if state == PetState.DRAGGED:
            return PosePoint(math.sin(cycle) * 1.2, math.cos(cycle) * 1.0)
        return PosePoint(0.0, 0.0)

    def _rotation(self, state: PetState, pet: Pet, fall_strength: float) -> float:
        if state == PetState.FALL:
            drift = clamp(pet.velocity.x / 500.0, -1.0, 1.0)
            return -12.0 - fall_strength * 14.0 + drift * 8.0
        if state == PetState.CLIMB:
            return -7.0
        if state == PetState.JUMP:
            drift = clamp(pet.velocity.x / 500.0, -1.0, 1.0)
            lift = clamp(max(-pet.velocity.y, 0.0) / 520.0, 0.0, 1.0)
            return 7.0 * lift + drift * 8.0
        if state == PetState.DRAGGED:
            return clamp(pet.velocity.x / 70.0, -10.0, 10.0)
        return 0.0

    def _body(self, state: PetState, w: int, h: int, fall_strength: float) -> BodyPose:
        if state == PetState.CLIMB:
            return BodyPose(
                PoseRect(w * 0.25, h * 0.14, w * 0.48, h * 0.72),
                PoseRect(w * 0.22, h * 0.12, w * 0.48, h * 0.70),
                PoseRect(w * 0.32, h * 0.22, w * 0.16, h * 0.17),
            )
        if state == PetState.FALL:
            stretch = fall_strength * h * 0.05
            narrow = fall_strength * w * 0.03
            return BodyPose(
                PoseRect(w * 0.20 + narrow, h * 0.21 - stretch * 0.2, w * 0.62 - narrow, h * 0.62 + stretch),
                PoseRect(w * 0.17 + narrow, h * 0.18 - stretch * 0.2, w * 0.62 - narrow, h * 0.60 + stretch),
                PoseRect(w * 0.31, h * 0.27, w * 0.19, h * 0.15),
            )
        if state == PetState.DRAGGED:
            return BodyPose(
                PoseRect(w * 0.22, h * 0.17, w * 0.60, h * 0.68),
                PoseRect(w * 0.19, h * 0.13, w * 0.60, h * 0.66),
                PoseRect(w * 0.31, h * 0.22, w * 0.20, h * 0.17),
            )
        if state == PetState.JUMP:
            return BodyPose(
                PoseRect(w * 0.23, h * 0.16, w * 0.56, h * 0.68),
                PoseRect(w * 0.20, h * 0.12, w * 0.56, h * 0.66),
                PoseRect(w * 0.32, h * 0.22, w * 0.18, h * 0.17),
            )
        return BodyPose(
            PoseRect(w * 0.22, h * 0.18, w * 0.58, h * 0.70),
            PoseRect(w * 0.19, h * 0.14, w * 0.58, h * 0.68),
            PoseRect(w * 0.31, h * 0.23, w * 0.20, h * 0.18),
        )

    def _limbs(
        self,
        state: PetState,
        cycle: float,
        speed: float,
        fall_strength: float,
        w: int,
        h: int,
    ) -> tuple[LimbPose, LimbPose, LimbPose, LimbPose]:
        radius = max(4, w * 0.06)
        terminal = max(4, w * 0.07)

        if state == PetState.CLIMB:
            hand_shift = math.sin(cycle) * h * 0.05
            foot_shift = math.sin(cycle + math.pi) * h * 0.055
            grip_x = w * 0.79
            return (
                LimbPose(PosePoint(w * 0.42, h * 0.34), PosePoint(w * 0.58, h * 0.29), PosePoint(grip_x, h * 0.24 + hand_shift), radius, terminal),
                LimbPose(PosePoint(w * 0.44, h * 0.50), PosePoint(w * 0.59, h * 0.47), PosePoint(grip_x, h * 0.43 - hand_shift), radius, terminal),
                LimbPose(PosePoint(w * 0.42, h * 0.70), PosePoint(w * 0.60, h * 0.68), PosePoint(grip_x, h * 0.70 + foot_shift), radius, terminal),
                LimbPose(PosePoint(w * 0.36, h * 0.75), PosePoint(w * 0.57, h * 0.80), PosePoint(grip_x, h * 0.82 - foot_shift), radius, terminal),
            )

        if state == PetState.FALL:
            spread = fall_strength
            arm_wave = math.sin(cycle) * h * 0.035
            return (
                LimbPose(PosePoint(w * 0.34, h * 0.44), PosePoint(w * (0.21 - 0.04 * spread), h * 0.36), PosePoint(w * (0.08 - 0.03 * spread), h * (0.31 - 0.05 * spread) + arm_wave), radius, terminal),
                LimbPose(PosePoint(w * 0.64, h * 0.45), PosePoint(w * (0.78 + 0.04 * spread), h * 0.36), PosePoint(w * (0.91 + 0.03 * spread), h * (0.31 - 0.05 * spread) - arm_wave), radius, terminal),
                LimbPose(PosePoint(w * 0.40, h * 0.74), PosePoint(w * 0.31, h * (0.82 + 0.02 * spread)), PosePoint(w * (0.20 - 0.03 * spread), h * 0.88), radius, terminal),
                LimbPose(PosePoint(w * 0.58, h * 0.74), PosePoint(w * 0.68, h * (0.82 + 0.02 * spread)), PosePoint(w * (0.78 + 0.03 * spread), h * 0.88), radius, terminal),
            )

        if state == PetState.JUMP:
            tuck = math.sin(cycle) * h * 0.025
            return (
                LimbPose(PosePoint(w * 0.34, h * 0.43), PosePoint(w * 0.25, h * 0.25), PosePoint(w * 0.20, h * 0.09 + tuck), radius, terminal),
                LimbPose(PosePoint(w * 0.62, h * 0.43), PosePoint(w * 0.72, h * 0.25), PosePoint(w * 0.78, h * 0.09 - tuck), radius, terminal),
                LimbPose(PosePoint(w * 0.39, h * 0.72), PosePoint(w * 0.33, h * 0.78), PosePoint(w * 0.28, h * 0.78 + tuck), radius, terminal),
                LimbPose(PosePoint(w * 0.58, h * 0.72), PosePoint(w * 0.66, h * 0.78), PosePoint(w * 0.72, h * 0.78 - tuck), radius, terminal),
            )

        stride = math.sin(cycle) * h * 0.05 * max(speed, 0.35)
        arm_swing = math.sin(cycle + math.pi) * h * 0.035 * max(speed, 0.25)
        if state == PetState.IDLE:
            stride *= 0.2
            arm_swing *= 0.2
        return (
            LimbPose(PosePoint(w * 0.29, h * 0.48), PosePoint(w * 0.22, h * 0.55 + arm_swing), PosePoint(w * 0.18, h * 0.64 + arm_swing), radius, terminal * 0.8),
            LimbPose(PosePoint(w * 0.67, h * 0.48), PosePoint(w * 0.75, h * 0.55 - arm_swing), PosePoint(w * 0.80, h * 0.64 - arm_swing), radius, terminal * 0.8),
            LimbPose(PosePoint(w * 0.36, h * 0.74), PosePoint(w * 0.30, h * 0.80 + stride * 0.4), PosePoint(w * 0.27, h * 0.86 + stride), radius, terminal),
            LimbPose(PosePoint(w * 0.60, h * 0.74), PosePoint(w * 0.66, h * 0.80 - stride * 0.4), PosePoint(w * 0.70, h * 0.86 - stride), radius, terminal),
        )

    def _scarf(self, state: PetState, cycle: float, w: int, h: int, fall_strength: float) -> ScarfPose:
        scarf_y = h * 0.57
        tail_tip_y = h * (0.58 + math.sin(cycle) * 0.03)
        if state == PetState.CLIMB:
            scarf_y = h * 0.54
            tail_tip_y = h * (0.52 + math.sin(cycle) * 0.025)
        elif state == PetState.JUMP:
            scarf_y = h * 0.54
            tail_tip_y = h * (0.42 + math.sin(cycle) * 0.035)
        elif state == PetState.FALL:
            scarf_y = h * 0.51
            tail_tip_y = h * (0.30 - fall_strength * 0.12 + math.sin(cycle) * 0.025)
        elif state == PetState.DRAGGED:
            tail_tip_y = h * (0.48 + math.sin(cycle) * 0.04)

        return ScarfPose(
            band=PoseRect(w * 0.18, scarf_y, w * 0.58, h * 0.12),
            tail_a=PosePoint(w * 0.66, scarf_y + h * 0.05),
            tail_tip=PosePoint(w * 0.93, tail_tip_y),
            tail_b=PosePoint(w * 0.68, scarf_y + h * 0.16),
        )

    def _eyes(self, state: PetState, cycle: float, w: int, h: int, fall_strength: float) -> EyePose:
        eye_y = h * 0.40
        if state == PetState.SLEEP:
            eye_y = h * 0.43
        elif state == PetState.JUMP:
            eye_y = h * 0.38
        elif state == PetState.FALL:
            eye_y = h * 0.38
        elif state == PetState.CLIMB:
            eye_y = h * 0.36

        look = math.sin(cycle * 0.55) * w * 0.008
        eye_w = w * (0.095 + fall_strength * 0.015 if state == PetState.FALL else 0.08)
        eye_h = h * (0.10 + fall_strength * 0.01 if state == PetState.FALL else 0.08)
        left = PoseRect(w * 0.41 + look, eye_y, eye_w, eye_h)
        right = PoseRect(w * 0.58 + look, eye_y, eye_w, eye_h)
        return EyePose(
            left=left,
            right=right,
            left_highlight=PoseRect(left.x + w * 0.03, eye_y + h * 0.015, w * 0.022, h * 0.022),
            right_highlight=PoseRect(right.x + w * 0.03, eye_y + h * 0.015, w * 0.022, h * 0.022),
            sleeping=state == PetState.SLEEP,
        )

    def _shadow(self, state: PetState, w: int, h: int, fall_strength: float) -> ShadowPose:
        if state == PetState.FALL:
            return ShadowPose(PoseRect(w * 0.34, h * 0.91, w * (0.40 - fall_strength * 0.12), h * 0.055), round(36 - fall_strength * 14))
        if state == PetState.JUMP:
            return ShadowPose(PoseRect(w * 0.30, h * 0.90, w * 0.42, h * 0.06), 42)
        return ShadowPose(PoseRect(w * 0.22, h * 0.84, w * 0.56, h * 0.10), 70)
