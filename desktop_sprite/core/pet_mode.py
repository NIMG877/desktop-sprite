from __future__ import annotations

from enum import StrEnum


class PetMode(StrEnum):
    IDLE = "idle"
    GO_TO_TARGET = "go_to_target"
    SHOW = "show"


class ModeController:
    def __init__(self, initial_mode: PetMode = PetMode.IDLE) -> None:
        self.mode = initial_mode
        self.locked = False

    def set_mode(self, mode: PetMode, *, force: bool = False, lock: bool = False) -> bool:
        if self.locked and not force and mode != self.mode:
            return False
        if self.locked and not force and mode == self.mode:
            self.locked = self.locked or lock
            return True
        self.mode = mode
        self.locked = lock
        return True

    def unlock(self) -> None:
        self.locked = False

    def is_idle(self) -> bool:
        return self.mode == PetMode.IDLE

    def is_go_to_target(self) -> bool:
        return self.mode == PetMode.GO_TO_TARGET

    def is_show(self) -> bool:
        return self.mode == PetMode.SHOW
