from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from desktop_sprite.utils.config import AppConfig


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
            "wander": 100.0,
            "vigor": 210.0,
            "recovery": 5.0,
            "awareness": 100.0,
            "focus": 2.0,
            "satiety": 100.0,
            "spark": 5.0,
            "radiance": 50.0,
            "trail": 0.0,
            "resonance": 0.0,
            "aura": 50.0,
            "arcana": 100.0,
            "attunement": 100.0,
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
        return replace(
            self,
            values=tuple(
                replace(
                    value,
                    flat_bonus=grouped.get(value.definition.id, (0.0, 0.0))[0],
                    percent_bonus=grouped.get(value.definition.id, (0.0, 0.0))[1],
                )
                for value in self.values
            ),
            modifiers=modifiers,
        )

    def add_modifier(self, modifier: PetAttributeModifier) -> PetAttributeSheet:
        return self.with_modifiers((*self.modifiers, modifier))

    def remove_modifiers_from_source(self, source_id: str) -> PetAttributeSheet:
        return self.with_modifiers(
            tuple(modifier for modifier in self.modifiers if modifier.source_id != source_id)
        )


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
