import pytest

from desktop_sprite.models.pet_attribute import (
    PetAttributeModifier,
    PetResourceInfluence,
    PetAttributeSheet,
    PetEffectiveStats,
    PetRuntimeResources,
)
from desktop_sprite.models.state import PetState
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


def test_effective_stats_map_attributes_to_runtime_parameters():
    config = _config()
    sheet = PetAttributeSheet.from_config(config).with_modifiers(
        (
            PetAttributeModifier("mobility", 20, "percent"),
            PetAttributeModifier("cling", 10),
            PetAttributeModifier("leap", 50),
            PetAttributeModifier("wander", 50),
            PetAttributeModifier("arcana", 25),
            PetAttributeModifier("attunement", 25),
        )
    )

    stats = PetEffectiveStats.from_sheet(config, sheet)

    assert stats.physics.walk_speed == 144
    assert stats.physics.climb_speed == 102
    assert stats.physics.jump_speed_x > config.physics.jump_speed_x
    assert stats.physics.jump_speed_y < config.physics.jump_speed_y
    assert stats.idle_min_seconds < config.behavior.idle_min_seconds
    assert stats.flight_speed == 650
    assert stats.wing_open_seconds == pytest.approx(0.56)


def test_runtime_resources_recover_and_apply_distinct_influence_factors():
    stats = PetEffectiveStats.from_sheet(_config(), PetAttributeSheet.from_config(_config()))
    resources = PetRuntimeResources.from_stats(stats)

    resources.tick(PetState.CLIMB, 10.0, stats)

    assert resources.stamina < stats.max_stamina

    resources.stamina = 0
    influence = resources.influence(stats)
    assert influence.climb_factor < influence.movement_factor
    assert influence.should_rest

    resources.tick(PetState.SLEEP, 10.0, stats)
    assert resources.stamina > 0


def test_resource_thresholds_use_base_values_and_have_hysteresis():
    config = _config()
    sheet = PetAttributeSheet.from_config(config).with_modifiers((PetAttributeModifier("vigor", 90),))
    stats = PetEffectiveStats.from_sheet(config, sheet)
    resources = PetRuntimeResources.from_stats(stats)

    assert stats.max_stamina == 300
    assert stats.base_stamina == 210

    resources.stamina = 42
    influence = PetResourceInfluence.from_resources(resources, stats)
    assert resources.stamina_ratio(stats) == pytest.approx(0.2)
    assert not influence.should_rest

    resources.stamina = 20
    assert PetResourceInfluence.from_resources(resources, stats).should_rest

    resources.stamina = 80
    assert not PetResourceInfluence.from_resources(resources, stats).should_stop_rest

    resources.stamina = 90
    assert PetResourceInfluence.from_resources(resources, stats).should_stop_rest
