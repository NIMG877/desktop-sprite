from __future__ import annotations

from desktop_sprite.core.character import DesktopCharacter
from desktop_sprite.core.pet_controller import PetController
from desktop_sprite.utils.config import AppConfig


def create_character(config: AppConfig, character_type: str | None = None) -> DesktopCharacter:
    return PetController(config)
