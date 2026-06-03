from desktop_sprite.models.pet_attribute import PetAttributeModifier, PetAttributeSheet
from desktop_sprite.utils.config import (
    AppConfig,
    BehaviorConfig,
    CharacterConfig,
    InteractionConfig,
    PetConfig,
    PhysicsConfig,
    RuntimeConfig,
)


def _config() -> AppConfig:
    return AppConfig(
        app=RuntimeConfig(60, True, False, "INFO"),
        pet=PetConfig(84, 104, 300, 300),
        physics=PhysicsConfig(1800, 120, 92, 180, -520, 1100, 0.65, 10),
        behavior=BehaviorConfig(1.0, 2.5, 120, True, 3.5),
        interaction=InteractionConfig(True, True, True, True, 220, 80),
        character=CharacterConfig("pet", {"pet": "characters/pet.json"}),
    )


def test_pet_attribute_sheet_reads_base_values_from_config_and_applies_modifiers():
    sheet = PetAttributeSheet.from_config(_config()).with_modifiers(
        (
            PetAttributeModifier("mobility", 12),
            PetAttributeModifier("mobility", 10, "percent"),
            PetAttributeModifier("spark", 3, "percent"),
        )
    )

    assert sheet.value_for("mobility").base_value == 120
    assert sheet.value_for("mobility").total == 144
    assert sheet.value_for("mobility").percent_bonus_value == 12
    assert sheet.value_for("mobility").formatted_formula() == "120 +12 +10%(+12)"
    assert sheet.value_for("leap").base_value == 350
    assert sheet.value_for("spark").formatted_total() == "8%"


def test_pet_attribute_sheet_can_add_and_remove_buff_modifiers_by_source():
    sheet = PetAttributeSheet.from_config(_config())

    buffed = sheet.add_modifier(PetAttributeModifier("vigor", 20, source_id="meal-buff"))

    assert buffed.value_for("vigor").total == 230
    assert buffed.remove_modifiers_from_source("meal-buff").value_for("vigor").total == 210
