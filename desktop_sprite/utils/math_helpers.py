"""Tiny pure-math helpers shared by pet-attribute math and pose math.

The clamp / lerp / smoothstep trio used to be reimplemented (twice)
inside the pet-attribute module and again inside the pose renderer.
Keeping a single source of truth makes future tweaks (e.g. switching
the smoothstep to a true Hermite curve) a one-file change.

The helpers are intentionally dependency-free — no NumPy, no Qt — so
they can be imported by anything from `models` up to `ui`.
"""

from __future__ import annotations


def clamp(value: float, minimum: float, maximum: float) -> float:
    """Clamp `value` into the closed interval `[minimum, maximum]`."""

    return min(max(value, minimum), maximum)


def lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation between `a` and `b` at parameter `t`."""

    return a + (b - a) * t


def smoothstep(t: float) -> float:
    """Standard Hermite smoothstep on the unit interval.

    `t` is clamped to `[0, 1]` first, so callers can pass any
    real value and still get a number inside the unit interval.
    """

    clamped = clamp(t, 0.0, 1.0)
    return clamped * clamped * (3.0 - 2.0 * clamped)
