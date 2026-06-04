from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from desktop_sprite.models.state import PetState
from desktop_sprite.utils.config import AppConfig, PhysicsConfig


BonusType = Literal["flat", "percent"]
AttributeValueFormat = Literal["number", "percent"]
AttributeCategory = Literal["basic", "visual", "special"]


@dataclass(frozen=True, slots=True)
class PetAttributeDefinition:
    id: str
    name: str
    english_name: str
    role: str
    mapped_content: str
    initial_source: str
    allowed_bonus_types: tuple[BonusType, ...]
    value_format: AttributeValueFormat = "number"
    category: AttributeCategory = "basic"


@dataclass(frozen=True, slots=True)
class PetAttributeModifier:
    attribute_id: str
    value: float
    bonus_type: BonusType = "flat"
    source_id: str = ""
    source_type: str = "manual"


@dataclass(frozen=True, slots=True)
class PetAttributeValue:
    definition: PetAttributeDefinition
    base_value: float
    flat_bonus: float = 0.0
    percent_bonus: float = 0.0

    @property
    def percent_bonus_value(self) -> float:
        if self.definition.value_format == "percent":
            return self.percent_bonus
        return self.base_value * self.percent_bonus / 100.0

    @property
    def total_bonus(self) -> float:
        return self.flat_bonus + self.percent_bonus_value

    @property
    def total(self) -> float:
        return self.base_value + self.total_bonus

    def formatted_total(self) -> str:
        return _format_attribute_number(self.total, self.definition.value_format)

    def formatted_base(self) -> str:
        return _format_attribute_number(self.base_value, self.definition.value_format)

    def formatted_bonus(self) -> str:
        parts: list[str] = []
        if self.flat_bonus:
            parts.append(_format_signed(self.flat_bonus, self.definition.value_format))
        if self.percent_bonus:
            parts.append(f"{_format_signed_number(self.percent_bonus)}%")
        return " / ".join(parts) if parts else "+0"

    def formatted_flat_bonus(self) -> str:
        return _format_signed(self.flat_bonus, self.definition.value_format)

    def formatted_percent_bonus_value(self) -> str:
        return _format_signed(self.percent_bonus_value, self.definition.value_format)

    def formatted_total_bonus(self) -> str:
        return _format_signed(self.total_bonus, self.definition.value_format)

    def formatted_formula(self) -> str:
        percent = f"{_format_signed_number(self.percent_bonus)}%"
        return (
            f"{self.formatted_base()} "
            f"{self.formatted_flat_bonus()} "
            f"{percent}({self.formatted_percent_bonus_value()})"
        )


@dataclass(frozen=True, slots=True)
class PetAttributeSheet:
    values: tuple[PetAttributeValue, ...]
    modifiers: tuple[PetAttributeModifier, ...] = ()

    @classmethod
    def from_config(cls, config: AppConfig) -> PetAttributeSheet:
        base_values = {
            "mobility": float(config.physics.walk_speed),
            "cling": float(config.physics.climb_speed),
            "leap": _derive_leap_value(config),
            "wander": float(config.attributes.wander),
            "vigor": float(config.attributes.vigor),
            "recovery": float(config.attributes.recovery),
            "awareness": float(config.attributes.awareness),
            "focus": float(config.attributes.focus),
            "satiety": float(config.attributes.satiety),
            "spark": float(config.attributes.spark),
            "radiance": float(config.attributes.radiance),
            "trail": float(config.attributes.trail),
            "resonance": float(config.attributes.resonance),
            "aura": float(config.attributes.aura),
            "arcana": float(config.attributes.arcana),
            "attunement": float(config.attributes.attunement),
        }
        return cls(
            tuple(
                PetAttributeValue(definition, base_values[definition.id])
                for definition in PET_ATTRIBUTE_DEFINITIONS
            )
        )

    def value_for(self, attribute_id: str) -> PetAttributeValue:
        for value in self.values:
            if value.definition.id == attribute_id:
                return value
        raise KeyError(f"Unknown pet attribute: {attribute_id}")

    def with_modifiers(self, modifiers: tuple[PetAttributeModifier, ...]) -> PetAttributeSheet:
        grouped: dict[str, tuple[float, float]] = {}
        for modifier in modifiers:
            definition = PET_ATTRIBUTE_DEFINITIONS_BY_ID.get(modifier.attribute_id)
            if definition is None or modifier.bonus_type not in definition.allowed_bonus_types:
                continue
            flat_bonus, percent_bonus = grouped.get(modifier.attribute_id, (0.0, 0.0))
            if modifier.bonus_type == "percent":
                percent_bonus += modifier.value
            else:
                flat_bonus += modifier.value
            grouped[modifier.attribute_id] = (flat_bonus, percent_bonus)

        new_values: list[PetAttributeValue] = []
        for value in self.values:
            flat, percent = grouped.get(value.definition.id, (0.0, 0.0))
            new_values.append(
                replace(
                    value,
                    flat_bonus=flat,
                    percent_bonus=percent,
                )
            )
        return replace(
            self,
            values=tuple(new_values),
            modifiers=modifiers,
        )

    def add_modifier(self, modifier: PetAttributeModifier) -> PetAttributeSheet:
        return self.with_modifiers((*self.modifiers, modifier))

    def remove_modifiers_from_source(self, source_id: str) -> PetAttributeSheet:
        return self.with_modifiers(
            tuple(modifier for modifier in self.modifiers if modifier.source_id != source_id)
        )


@dataclass(frozen=True, slots=True)
class PetEffectiveStats:
    physics: PhysicsConfig
    idle_min_seconds: float
    idle_max_seconds: float
    reachable_wander_probability: float
    min_wander_distance_factor: float
    flight_speed: float
    landing_speed: float
    wing_open_seconds: float
    wing_close_seconds: float
    hover_amplitude: float
    hover_frequency: float
    max_stamina: float
    base_stamina: float
    stamina_recovery: float
    max_energy: float
    base_energy: float
    energy_recovery: float
    satiety: float
    base_satiety: float

    @classmethod
    def from_sheet(cls, config: AppConfig, sheet: PetAttributeSheet) -> "PetEffectiveStats":
        mobility = _attribute_ratio(sheet, "mobility", config.physics.walk_speed)
        cling = _attribute_ratio(sheet, "cling", config.physics.climb_speed)
        leap = _attribute_ratio(sheet, "leap", _derive_leap_value(config))
        wander = _attribute_ratio(sheet, "wander", config.attributes.wander)
        arcana = _attribute_ratio(sheet, "arcana", config.attributes.arcana)
        attunement = _attribute_ratio(sheet, "attunement", config.attributes.attunement)

        wander_interval_scale = 1.0 / wander
        return cls(
            physics=replace(
                config.physics,
                walk_speed=max(config.physics.walk_speed * mobility, 1.0),
                climb_speed=max(config.physics.climb_speed * cling, 1.0),
                jump_speed_x=config.physics.jump_speed_x * leap,
                jump_speed_y=config.physics.jump_speed_y * leap,
            ),
            idle_min_seconds=max(config.behavior.idle_min_seconds * wander_interval_scale, 0.1),
            idle_max_seconds=max(config.behavior.idle_max_seconds * wander_interval_scale, 0.1),
            reachable_wander_probability=_clamp(0.5 * wander, 0.05, 0.95),
            min_wander_distance_factor=_clamp(0.8 * wander, 0.25, 2.0),
            flight_speed=max(config.pet.flight.speed * arcana, 1.0),
            landing_speed=max(config.pet.flight.landing_speed * arcana, 1.0),
            wing_open_seconds=max(config.pet.wings.open_seconds / attunement, 0.05),
            wing_close_seconds=max(config.pet.wings.close_seconds / attunement, 0.05),
            hover_amplitude=max(config.pet.hover.amplitude * arcana, 0.0),
            hover_frequency=max(config.pet.hover.frequency * attunement, 0.05),
            max_stamina=max(_attribute_total(sheet, "vigor", config.attributes.vigor), 1.0),
            base_stamina=max(_attribute_base(sheet, "vigor", config.attributes.vigor), 1.0),
            stamina_recovery=max(_attribute_total(sheet, "recovery", config.attributes.recovery), 0.0),
            max_energy=max(_attribute_total(sheet, "awareness", config.attributes.awareness), 1.0),
            base_energy=max(_attribute_base(sheet, "awareness", config.attributes.awareness), 1.0),
            energy_recovery=max(_attribute_total(sheet, "focus", config.attributes.focus), 0.0),
            satiety=max(_attribute_total(sheet, "satiety", config.attributes.satiety), 1.0),
            base_satiety=max(_attribute_base(sheet, "satiety", config.attributes.satiety), 1.0),
        )


@dataclass(frozen=True, slots=True)
class PetResourceInfluence:
    movement_factor: float
    climb_factor: float
    jump_factor: float
    wander_factor: float
    special_factor: float
    recovery_factor: float
    sleep_pressure: float
    feeding_pressure: float
    should_sleep: bool
    should_wake: bool
    should_rest: bool
    should_stop_rest: bool
    should_seek_food: bool
    should_stop_seek_food: bool

    @classmethod
    def from_resources(
        cls,
        resources: "PetRuntimeResources",
        stats: PetEffectiveStats,
    ) -> "PetResourceInfluence":
        stamina_ratio = resources.stamina_ratio(stats)
        energy_ratio = resources.energy_ratio(stats)
        satiety_ratio = resources.satiety_ratio(stats)

        stamina_ready = _smooth_ratio(stamina_ratio, 0.15, 0.60)
        stamina_burst = _smooth_ratio(stamina_ratio, 0.20, 0.75)
        energy_ready = _smooth_ratio(energy_ratio, 0.15, 0.70)
        special_ready = _smooth_ratio(energy_ratio, 0.20, 0.80)
        satiety_ready = _smooth_ratio(satiety_ratio, 0.10, 0.55)

        return cls(
            movement_factor=_clamp((0.70 + 0.30 * stamina_ready) * (0.85 + 0.15 * satiety_ready), 0.25, 1.0),
            climb_factor=_clamp((0.35 + 0.65 * stamina_burst) * (0.85 + 0.15 * satiety_ready), 0.25, 1.0),
            jump_factor=_clamp((0.40 + 0.60 * stamina_burst) * (0.90 + 0.10 * satiety_ready), 0.25, 1.0),
            wander_factor=_clamp(
                (0.15 + 0.85 * energy_ready)
                * (0.25 + 0.75 * stamina_ready)
                * (0.35 + 0.65 * satiety_ready),
                0.0,
                1.0,
            ),
            special_factor=_clamp((0.10 + 0.90 * special_ready) * (0.50 + 0.50 * satiety_ready), 0.0, 1.0),
            recovery_factor=_clamp(0.25 + 0.75 * satiety_ready, 0.25, 1.0),
            sleep_pressure=_clamp(1.0 - _smooth_ratio(energy_ratio, 0.10, 0.45), 0.0, 1.0),
            feeding_pressure=_clamp(1.0 - _smooth_ratio(satiety_ratio, 0.10, 0.40), 0.0, 1.0),
            should_sleep=energy_ratio <= 0.10,
            should_wake=energy_ratio >= 0.45,
            should_rest=stamina_ratio <= 0.15,
            should_stop_rest=stamina_ratio >= 0.40,
            should_seek_food=satiety_ratio <= 0.10,
            should_stop_seek_food=satiety_ratio >= 0.35,
        )


@dataclass(slots=True)
class PetRuntimeResources:
    stamina: float
    energy: float
    satiety: float

    @classmethod
    def from_stats(cls, stats: PetEffectiveStats) -> "PetRuntimeResources":
        return cls(stats.max_stamina, stats.max_energy, stats.satiety)

    def clamp_to_stats(self, stats: PetEffectiveStats) -> None:
        self.stamina = _clamp(self.stamina, 0.0, stats.max_stamina)
        self.energy = _clamp(self.energy, 0.0, stats.max_energy)
        self.satiety = _clamp(self.satiety, 0.0, stats.satiety)

    def tick(self, state: PetState, dt: float, stats: PetEffectiveStats) -> None:
        elapsed = max(dt, 0.0)
        influence = PetResourceInfluence.from_resources(self, stats)
        if state == PetState.SLEEP:
            self.energy += stats.energy_recovery * influence.recovery_factor * elapsed
            self.stamina += stats.stamina_recovery * influence.recovery_factor * elapsed
        elif state in {PetState.IDLE, PetState.DRAGGED}:
            self.stamina += stats.stamina_recovery * influence.recovery_factor * 0.5 * elapsed
            self.energy -= 0.1 * (1.0 + influence.feeding_pressure * 0.35) * elapsed
        else:
            self.stamina -= _stamina_cost_for_state(state) * elapsed
            self.energy -= 0.25 * (1.0 + influence.feeding_pressure * 0.35) * elapsed
        self.satiety -= _satiety_cost_for_state(state) * (100.0 / max(stats.base_satiety, 1.0)) * elapsed
        self.clamp_to_stats(stats)

    def influence(self, stats: PetEffectiveStats) -> PetResourceInfluence:
        return PetResourceInfluence.from_resources(self, stats)

    def stamina_ratio(self, stats: PetEffectiveStats) -> float:
        return self.stamina / max(stats.base_stamina, 1.0)

    def energy_ratio(self, stats: PetEffectiveStats) -> float:
        return self.energy / max(stats.base_energy, 1.0)

    def satiety_ratio(self, stats: PetEffectiveStats) -> float:
        return self.satiety / max(stats.base_satiety, 1.0)


PET_ATTRIBUTE_DEFINITIONS: tuple[PetAttributeDefinition, ...] = (
    PetAttributeDefinition("mobility", "机动", "Mobility", "基础水平移动速度", "walk_speed", "config.physics.walk_speed", ("flat", "percent")),
    PetAttributeDefinition("cling", "攀附", "Cling", "垂直/边缘移动速度", "climb_speed", "config.physics.climb_speed", ("flat", "percent")),
    PetAttributeDefinition("leap", "腾跃", "Leap", "综合跳跃能力", "jump_speed_x / jump_speed_y", "config.physics.jump_speed_x + jump_speed_y", ("flat", "percent")),
    PetAttributeDefinition("wander", "巡游", "Wander", "自主移动倾向", "idle_min_seconds / idle_max_seconds", "fixed", ("flat",)),
    PetAttributeDefinition("vigor", "元气", "Vigor", "体力容量", "可持续活动时间", "fixed", ("flat",)),
    PetAttributeDefinition("recovery", "生息", "Recovery", "体力恢复速度", "休息/低活动体力恢复", "fixed", ("flat",)),
    PetAttributeDefinition("awareness", "灵识", "Awareness", "精力容量", "清醒活动时长", "fixed", ("flat",)),
    PetAttributeDefinition("focus", "凝神", "Focus", "精力恢复速度", "睡眠恢复效率", "fixed", ("flat",)),
    PetAttributeDefinition("satiety", "饱腹", "Satiety", "饥饿综合属性", "饥饿增长/惩罚/寻食倾向", "fixed", ("flat",)),
    PetAttributeDefinition("spark", "迸发", "Spark", "视觉触发强度", "展示/特殊动作/稀有表现触发概率", "fixed", ("percent",), "percent", "visual"),
    PetAttributeDefinition("radiance", "辉映", "Radiance", "视觉存在感", "光感/亮度/轮廓强调", "fixed", ("flat",), "number", "visual"),
    PetAttributeDefinition("trail", "留痕", "Trail", "动作残留感", "轨迹/残影/拖尾", "fixed", ("flat",), "number", "visual"),
    PetAttributeDefinition("resonance", "共鸣", "Resonance", "反馈表现强度", "回响/波纹/粒子/动作反馈", "fixed", ("flat",), "number", "visual"),
    PetAttributeDefinition("aura", "灵韵", "Aura", "整体氛围感", "气场/节奏/视觉风格", "fixed", ("flat",), "number", "visual"),
    PetAttributeDefinition("arcana", "异能", "Arcana", "特殊能力强度", "角色特殊能力强度", "fixed", ("flat",), "number", "special"),
    PetAttributeDefinition("attunement", "调律", "Attunement", "特殊能力流畅度", "启动/结束/衔接/冷却", "fixed", ("flat",), "number", "special"),
)
PET_ATTRIBUTE_DEFINITIONS_BY_ID = {definition.id: definition for definition in PET_ATTRIBUTE_DEFINITIONS}
PET_ATTRIBUTE_ID_BY_NAME = {definition.name: definition.id for definition in PET_ATTRIBUTE_DEFINITIONS}
PET_ATTRIBUTE_ID_BY_ENGLISH_NAME = {definition.english_name: definition.id for definition in PET_ATTRIBUTE_DEFINITIONS}


def attribute_id_for_name(name: str) -> str | None:
    return PET_ATTRIBUTE_ID_BY_NAME.get(name) or PET_ATTRIBUTE_ID_BY_ENGLISH_NAME.get(name)


def _derive_leap_value(config: AppConfig) -> float:
    return (abs(float(config.physics.jump_speed_x)) + abs(float(config.physics.jump_speed_y))) / 2.0


def _attribute_total(sheet: PetAttributeSheet, attribute_id: str, fallback: float) -> float:
    try:
        return sheet.value_for(attribute_id).total
    except KeyError:
        return fallback


def _attribute_base(sheet: PetAttributeSheet, attribute_id: str, fallback: float) -> float:
    try:
        return sheet.value_for(attribute_id).base_value
    except KeyError:
        return fallback


def _attribute_ratio(sheet: PetAttributeSheet, attribute_id: str, fallback: float) -> float:
    value = _attribute_total(sheet, attribute_id, fallback)
    return _clamp(value / max(abs(fallback), 1.0), 0.25, 3.0)


def _stamina_cost_for_state(state: PetState) -> float:
    if state == PetState.CLIMB:
        return 2.5
    if state == PetState.JUMP:
        return 2.0
    if state in {PetState.FLY, PetState.HOVER, PetState.WING_LAND}:
        return 1.8
    if state == PetState.WALK:
        return 1.0
    return 0.5


def _satiety_cost_for_state(state: PetState) -> float:
    if state == PetState.SLEEP:
        return 0.008
    if state in {PetState.IDLE, PetState.DRAGGED}:
        return 0.012
    if state in {PetState.CLIMB, PetState.JUMP, PetState.FLY, PetState.HOVER, PetState.WING_LAND}:
        return 0.035
    if state == PetState.WALK:
        return 0.02
    return 0.016


def _smooth_ratio(value: float, start: float, end: float) -> float:
    if end <= start:
        return 1.0 if value >= end else 0.0
    normalized = _clamp((value - start) / (end - start), 0.0, 1.0)
    return normalized * normalized * (3.0 - 2.0 * normalized)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(max(value, minimum), maximum)


def _format_attribute_number(value: float, value_format: AttributeValueFormat) -> str:
    text = _format_number(value)
    return f"{text}%" if value_format == "percent" else text


def _format_signed(value: float, value_format: AttributeValueFormat) -> str:
    text = _format_signed_number(value)
    return f"{text}%" if value_format == "percent" else text


def _format_signed_number(value: float) -> str:
    sign = "+" if value >= 0 else "-"
    return f"{sign}{_format_number(abs(value))}"


def _format_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")
