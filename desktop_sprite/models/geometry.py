from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Vec2:
    x: float = 0.0
    y: float = 0.0

    def copy(self) -> "Vec2":
        return Vec2(self.x, self.y)


@dataclass(frozen=True, slots=True)
class Rect:
    left: float
    top: float
    right: float
    bottom: float

    @classmethod
    def from_xywh(cls, x: float, y: float, width: float, height: float) -> "Rect":
        return cls(x, y, x + width, y + height)

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top

    @property
    def center_x(self) -> float:
        return (self.left + self.right) / 2

    @property
    def center_y(self) -> float:
        return (self.top + self.bottom) / 2

    def moved_by(self, dx: float, dy: float) -> "Rect":
        return Rect(self.left + dx, self.top + dy, self.right + dx, self.bottom + dy)

    def overlaps_x(self, other: "Rect", padding: float = 0.0) -> bool:
        return self.right > other.left + padding and self.left < other.right - padding

    def overlaps_y(self, other: "Rect", padding: float = 0.0) -> bool:
        return self.bottom > other.top + padding and self.top < other.bottom - padding

    def intersects(self, other: "Rect") -> bool:
        return self.overlaps_x(other) and self.overlaps_y(other)

    def contains_point(self, x: float, y: float) -> bool:
        return self.left <= x <= self.right and self.top <= y <= self.bottom

    def clamp_point(self, x: float, y: float) -> tuple[float, float]:
        return min(max(x, self.left), self.right), min(max(y, self.top), self.bottom)

    def is_valid(self) -> bool:
        return self.width > 0 and self.height > 0
