from __future__ import annotations

import json
import random
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from desktop_sprite.models.pet_attribute import (
    PET_ATTRIBUTE_DEFINITIONS,
    PET_ATTRIBUTE_DEFINITIONS_BY_ID,
    PET_ATTRIBUTE_ID_BY_NAME,
    BonusType,
    PetAttributeModifier,
    attribute_id_for_name,
)


SPIRIT_MARK_CATEGORY_ID = "spirit_mark"


@dataclass(frozen=True, slots=True)
class SpiritMarkSlot:
    id: str
    name: str
    description: str


@dataclass(frozen=True, slots=True)
class SpiritMarkSet:
    id: str
    name: str
    style: str
    two_piece_stat: str
    two_piece_value: int
    two_piece_bonus_type: BonusType
    four_piece_description: str


@dataclass(frozen=True, slots=True)
class SpiritMarkStat:
    name: str
    value: int
    bonus_type: BonusType = "flat"


@dataclass(frozen=True, slots=True)
class SpiritMarkGrantRequest:
    entry_id: str = ""
    source_type: str = "manual"
    source_id: str = ""
    source_description: str = "这道灵痕来自一次手动纪念。"
    quality_hint: str = ""
    style_hint: str = ""
    set_hint: str = ""
    rarity_hint: str | int = ""
    record_tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SpiritMark:
    entry_id: str
    name: str
    slot_id: str
    set_id: str
    rarity: int
    main_stat: SpiritMarkStat
    sub_stats: tuple[SpiritMarkStat, ...] = ()
    level: int = 0
    source_type: str = "manual"
    source_id: str = ""
    source_description: str = ""
    created_at: str = ""
    favorite: bool = False
    equipped: bool = False
    fractured: bool = False
    record_tags: tuple[str, ...] = ()

    @property
    def max_level(self) -> int:
        return max_level_for_rarity(self.rarity)


@dataclass(frozen=True, slots=True)
class SpiritMarkMaterials:
    spirit_dust: int = 0
    essence: int = 0
    stardust_core: int = 0
    remnant: int = 0
    set_dust: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SpiritMarkInventory:
    marks: tuple[SpiritMark, ...] = ()
    materials: SpiritMarkMaterials = field(default_factory=SpiritMarkMaterials)

    def mark_by_entry_id(self, entry_id: str) -> SpiritMark | None:
        return next((mark for mark in self.marks if mark.entry_id == entry_id), None)

    def equipped_marks(self) -> tuple[SpiritMark, ...]:
        return tuple(mark for mark in self.marks if mark.equipped)

    def equip(self, entry_id: str) -> SpiritMarkInventory:
        mark = self._require_mark(entry_id)
        marks = tuple(
            replace(other, equipped=(other.entry_id == entry_id or (other.equipped and other.slot_id != mark.slot_id)))
            for other in self.marks
        )
        return replace(self, marks=marks)

    def unequip(self, entry_id: str) -> SpiritMarkInventory:
        self._require_mark(entry_id)
        return replace(
            self,
            marks=tuple(replace(mark, equipped=False) if mark.entry_id == entry_id else mark for mark in self.marks),
        )

    def set_favorite(self, entry_id: str, favorite: bool = True) -> SpiritMarkInventory:
        self._require_mark(entry_id)
        return replace(
            self,
            marks=tuple(replace(mark, favorite=favorite) if mark.entry_id == entry_id else mark for mark in self.marks),
        )

    def enhance(self, entry_id: str, *, rng: random.Random | None = None) -> SpiritMarkInventory:
        mark = self._require_mark(entry_id)
        if mark.level >= mark.max_level:
            raise SpiritMarkError(f"Spirit mark {entry_id} is already at max level")
        rng = rng or random.Random()
        growth = 1 + (1 if rng.random() < 0.25 + mark.rarity * 0.03 else 0)
        main_stat = replace(mark.main_stat, value=mark.main_stat.value + growth)
        sub_stats = tuple(
            replace(stat, value=stat.value + (1 if index == mark.level % max(1, len(mark.sub_stats)) else 0))
            for index, stat in enumerate(mark.sub_stats)
        )
        updated = replace(mark, level=mark.level + 1, main_stat=main_stat, sub_stats=sub_stats)
        return replace(self, marks=tuple(updated if item.entry_id == entry_id else item for item in self.marks))

    def decompose(self, entry_id: str) -> tuple[SpiritMarkInventory, SpiritMarkMaterials]:
        mark = self._require_mark(entry_id)
        if mark.favorite:
            raise SpiritMarkError("Favorite spirit marks cannot be decomposed")
        returned = SpiritMarkMaterials(
            spirit_dust=mark.rarity * 6 + mark.level * 3,
            essence=max(0, mark.rarity - 2) + mark.level // 4,
            stardust_core=1 if mark.rarity >= 5 else 0,
            remnant=2 if mark.fractured else 0,
            set_dust={mark.set_id: max(1, mark.level // 3)} if mark.level else {},
        )
        inventory = replace(self, marks=tuple(mark_item for mark_item in self.marks if mark_item.entry_id != entry_id))
        return inventory, returned

    def stat_totals(self) -> dict[str, int]:
        totals: dict[str, int] = {}
        for mark in self.equipped_marks():
            main_key = _stat_total_key(mark.main_stat)
            totals[main_key] = totals.get(main_key, 0) + mark.main_stat.value
            for stat in mark.sub_stats:
                key = _stat_total_key(stat)
                totals[key] = totals.get(key, 0) + stat.value
        for set_id, count in self.set_counts().items():
            set_definition = SPIRIT_MARK_SETS.get(set_id)
            if set_definition is not None and count >= 2:
                stat = SpiritMarkStat(
                    set_definition.two_piece_stat,
                    set_definition.two_piece_value,
                    set_definition.two_piece_bonus_type,
                )
                key = _stat_total_key(stat)
                totals[key] = totals.get(key, 0) + stat.value
        return totals

    def formatted_stat_totals(self) -> tuple[str, ...]:
        lines: list[str] = []
        for key, value in sorted(self.stat_totals().items()):
            name, bonus_type = _split_stat_total_key(key)
            lines.append(format_spirit_mark_stat(SpiritMarkStat(name, value, bonus_type)))
        return tuple(lines)

    def attribute_modifiers(self) -> tuple[PetAttributeModifier, ...]:
        modifiers: list[PetAttributeModifier] = []
        for mark in self.equipped_marks():
            modifiers.append(_stat_modifier(mark.main_stat, source_id=mark.entry_id))
            modifiers.extend(_stat_modifier(stat, source_id=mark.entry_id) for stat in mark.sub_stats)
        for set_id, count in self.set_counts().items():
            set_definition = SPIRIT_MARK_SETS.get(set_id)
            if set_definition is None or count < 2:
                continue
            modifiers.append(
                _stat_modifier(
                    SpiritMarkStat(
                        set_definition.two_piece_stat,
                        set_definition.two_piece_value,
                        set_definition.two_piece_bonus_type,
                    ),
                    source_id=f"set:{set_id}:2",
                    source_type="spirit_mark_set",
                )
            )
        return tuple(modifier for modifier in modifiers if modifier.attribute_id)

    def set_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for mark in self.equipped_marks():
            counts[mark.set_id] = counts.get(mark.set_id, 0) + 1
        return counts

    def _require_mark(self, entry_id: str) -> SpiritMark:
        mark = self.mark_by_entry_id(entry_id)
        if mark is None:
            raise SpiritMarkError(f"Unknown spirit mark entry: {entry_id}")
        return mark


class SpiritMarkError(ValueError):
    pass


SPIRIT_MARK_SLOTS: dict[str, SpiritMarkSlot] = {
    "core": SpiritMarkSlot("core", "灵核", "桌宠能力的核心痕迹，偏向能量、觉醒、稳定与整体气质。"),
    "form": SpiritMarkSlot("form", "形骸", "桌宠外部形态与身体结构，偏向体态、轮廓和动作幅度。"),
    "meridian": SpiritMarkSlot("meridian", "脉络", "桌宠内部流动与动作衔接，偏向柔韧、回弹、节奏与连贯性。"),
    "edge": SpiritMarkSlot("edge", "锋质", "桌宠外放能力与动作张力，偏向爆发、冲击、速度与压迫感。"),
    "echo": SpiritMarkSlot("echo", "余响", "桌宠行为留下的痕迹，偏向光效、残影、轨迹和氛围。"),
}

SPIRIT_MARK_SETS: dict[str, SpiritMarkSet] = {
    "silent_guardian": SpiritMarkSet("silent_guardian", "静默守护", "安静、陪伴、守护", "灵识", 2, "flat", "待机、陪伴或守护状态下，桌宠精力基础更稳定。"),
    "stardust_echo": SpiritMarkSet("stardust_echo", "星尘余响", "光效、轨迹、残影", "留痕", 2, "flat", "桌宠动作结束后会留下更明显的轨迹、残影或粒子表现。"),
    "windfarer": SpiritMarkSet("windfarer", "破风远行", "移动、巡游、探索", "机动", 2, "percent", "桌宠巡游、移动或空间活动范围更大，行动路径更丰富。"),
    "falling_echo": SpiritMarkSet("falling_echo", "坠落回响", "落地、回弹、重量感", "腾跃", 2, "flat", "桌宠落地、停驻或动作收尾时表现更平稳。"),
    "flowing_mirage": SpiritMarkSet("flowing_mirage", "幻形流转", "变形、流动、动作衔接", "调律", 2, "flat", "桌宠动作衔接更自然，特殊能力启动与收束更流畅。"),
}

PRIMARY_STAT_POOLS: dict[str, tuple[str, ...]] = {
    "core": ("元气", "灵识", "异能", "调律"),
    "form": ("机动", "腾跃", "元气", "饱腹"),
    "meridian": ("攀附", "调律", "生息", "凝神"),
    "edge": ("机动", "腾跃", "巡游", "迸发"),
    "echo": ("辉映", "留痕", "共鸣", "灵韵"),
}

ALL_STATS = tuple(definition.name for definition in PET_ATTRIBUTE_DEFINITIONS)
STYLE_SET_HINTS = {
    "ambient": "silent_guardian",
    "quiet": "silent_guardian",
    "trail": "stardust_echo",
    "light": "stardust_echo",
    "move": "windfarer",
    "exploration": "windfarer",
    "landing": "falling_echo",
    "flow": "flowing_mirage",
}


def generate_spirit_mark(
    request: SpiritMarkGrantRequest,
    *,
    rng: random.Random | None = None,
    now: datetime | None = None,
) -> SpiritMark:
    rng = rng or random.Random()
    now = now or datetime.now(timezone.utc)
    slot_id = rng.choice(tuple(SPIRIT_MARK_SLOTS))
    set_id = _select_set_id(request, rng)
    rarity = _select_rarity(request.rarity_hint, request.quality_hint, rng)
    fractured = request.quality_hint in {"interrupted", "failed", "fractured"}
    main_name = rng.choice(PRIMARY_STAT_POOLS[slot_id])
    main_bonus_type = _select_bonus_type(main_name, rng)
    sub_pool = [stat for stat in ALL_STATS if stat != main_name]
    sub_count = max(1, min(4, rarity - 1))
    sub_stats = _roll_sub_stats(tuple(rng.sample(sub_pool, k=sub_count)), rarity, rng)
    slot = SPIRIT_MARK_SLOTS[slot_id]
    spirit_set = SPIRIT_MARK_SETS[set_id]
    entry_id = request.entry_id or _build_entry_id(now, rng)
    return SpiritMark(
        entry_id=entry_id,
        name=f"{spirit_set.name}·{slot.name}",
        slot_id=slot_id,
        set_id=set_id,
        rarity=rarity,
        main_stat=SpiritMarkStat(main_name, _roll_main_stat_value(rarity, main_bonus_type, rng), main_bonus_type),
        sub_stats=sub_stats,
        source_type=request.source_type,
        source_id=request.source_id,
        source_description=request.source_description,
        created_at=now.isoformat(),
        fractured=fractured,
        record_tags=request.record_tags,
    )


def max_level_for_rarity(rarity: int) -> int:
    return 4 + max(1, min(5, rarity)) * 2


def format_spirit_mark_stat(stat: SpiritMarkStat) -> str:
    suffix = "%" if stat.bonus_type == "percent" else ""
    return f"{stat.name} +{stat.value}{suffix}"


def load_spirit_mark_inventory(
    path: str | Path,
) -> SpiritMarkInventory:
    selected_path = Path(path)
    _ensure_spirit_mark_file(selected_path)
    with selected_path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    return spirit_mark_inventory_from_dict(data)


def save_spirit_mark_inventory(path: str | Path, inventory: SpiritMarkInventory) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as file:
        json.dump(spirit_mark_inventory_to_dict(inventory), file, ensure_ascii=False, indent=2)
        file.write("\n")


def spirit_mark_inventory_from_dict(data: dict[str, Any]) -> SpiritMarkInventory:
    marks = tuple(spirit_mark_from_dict(raw_mark) for raw_mark in data.get("marks", ()))
    materials_data = data.get("materials", {})
    materials = SpiritMarkMaterials(
        spirit_dust=int(materials_data.get("spirit_dust", 0)),
        essence=int(materials_data.get("essence", 0)),
        stardust_core=int(materials_data.get("stardust_core", 0)),
        remnant=int(materials_data.get("remnant", 0)),
        set_dust={str(key): int(value) for key, value in materials_data.get("set_dust", {}).items()},
    )
    return SpiritMarkInventory(marks, materials)


def spirit_mark_inventory_to_dict(inventory: SpiritMarkInventory) -> dict[str, Any]:
    return {
        "marks": [spirit_mark_to_dict(mark) for mark in inventory.marks],
        "materials": {
            "spirit_dust": inventory.materials.spirit_dust,
            "essence": inventory.materials.essence,
            "stardust_core": inventory.materials.stardust_core,
            "remnant": inventory.materials.remnant,
            "set_dust": inventory.materials.set_dust,
        },
    }


def _ensure_spirit_mark_file(path: Path) -> None:
    if path.is_file():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(spirit_mark_inventory_to_dict(SpiritMarkInventory()), file, ensure_ascii=False, indent=2)
        file.write("\n")


def spirit_mark_from_dict(data: dict[str, Any]) -> SpiritMark:
    return SpiritMark(
        entry_id=str(data["entry_id"]),
        name=str(data["name"]),
        slot_id=str(data["slot_id"]),
        set_id=str(data["set_id"]),
        rarity=int(data["rarity"]),
        main_stat=_stat_from_dict(data["main_stat"]),
        sub_stats=tuple(_stat_from_dict(item) for item in data.get("sub_stats", ())),
        level=int(data.get("level", 0)),
        source_type=str(data.get("source_type", "manual")),
        source_id=str(data.get("source_id", "")),
        source_description=str(data.get("source_description", "")),
        created_at=str(data.get("created_at", "")),
        favorite=bool(data.get("favorite", False)),
        equipped=bool(data.get("equipped", False)),
        fractured=bool(data.get("fractured", False)),
        record_tags=tuple(str(tag) for tag in data.get("record_tags", ())),
    )


def spirit_mark_to_dict(mark: SpiritMark) -> dict[str, Any]:
    return {
        "entry_id": mark.entry_id,
        "name": mark.name,
        "slot_id": mark.slot_id,
        "set_id": mark.set_id,
        "rarity": mark.rarity,
        "main_stat": _stat_to_dict(mark.main_stat),
        "sub_stats": [_stat_to_dict(stat) for stat in mark.sub_stats],
        "level": mark.level,
        "source_type": mark.source_type,
        "source_id": mark.source_id,
        "source_description": mark.source_description,
        "created_at": mark.created_at,
        "favorite": mark.favorite,
        "equipped": mark.equipped,
        "fractured": mark.fractured,
        "record_tags": list(mark.record_tags),
    }


def _stat_from_dict(data: dict[str, Any]) -> SpiritMarkStat:
    return SpiritMarkStat(
        str(data["name"]),
        int(data["value"]),
        _normalize_bonus_type(data.get("bonus_type", "flat")),
    )


def _stat_to_dict(stat: SpiritMarkStat) -> dict[str, Any]:
    data: dict[str, Any] = {"name": stat.name, "value": stat.value}
    if stat.bonus_type != "flat":
        data["bonus_type"] = stat.bonus_type
    return data


def _stat_total_key(stat: SpiritMarkStat) -> str:
    return f"{stat.name}:{stat.bonus_type}"


def _split_stat_total_key(key: str) -> tuple[str, BonusType]:
    name, _separator, raw_bonus_type = key.rpartition(":")
    return name, _normalize_bonus_type(raw_bonus_type)


def _stat_modifier(
    stat: SpiritMarkStat,
    *,
    source_id: str,
    source_type: str = "spirit_mark",
) -> PetAttributeModifier:
    attribute_id = attribute_id_for_name(stat.name) or ""
    return PetAttributeModifier(
        attribute_id=attribute_id,
        value=stat.value,
        bonus_type=stat.bonus_type,
        source_id=source_id,
        source_type=source_type,
    )


def _roll_sub_stats(names: tuple[str, ...], rarity: int, rng: random.Random) -> tuple[SpiritMarkStat, ...]:
    stats: list[SpiritMarkStat] = []
    for name in names:
        bonus_type = _select_bonus_type(name, rng)
        stats.append(SpiritMarkStat(name, _roll_stat_value(rarity, bonus_type, rng), bonus_type))
    return tuple(stats)


def _select_bonus_type(name: str, rng: random.Random) -> BonusType:
    attribute_id = PET_ATTRIBUTE_ID_BY_NAME.get(name)
    definition = PET_ATTRIBUTE_DEFINITIONS_BY_ID.get(attribute_id or "")
    if definition is None:
        return "flat"
    if definition.allowed_bonus_types == ("percent",):
        return "percent"
    if definition.allowed_bonus_types == ("flat",):
        return "flat"
    return "percent" if rng.random() < 0.28 else "flat"


def _roll_main_stat_value(rarity: int, bonus_type: BonusType, rng: random.Random) -> int:
    if bonus_type == "percent":
        return rarity * 2 + rng.randint(0, 1)
    return rarity * 3 + rng.randint(0, 2)


def _roll_stat_value(rarity: int, bonus_type: BonusType, rng: random.Random) -> int:
    if bonus_type == "percent":
        return rng.randint(1, max(2, rarity))
    return rng.randint(1, rarity + 2)


def _normalize_bonus_type(value: Any) -> BonusType:
    return "percent" if value == "percent" else "flat"


def _select_set_id(request: SpiritMarkGrantRequest, rng: random.Random) -> str:
    if request.set_hint in SPIRIT_MARK_SETS:
        return request.set_hint
    if request.style_hint in STYLE_SET_HINTS:
        return STYLE_SET_HINTS[request.style_hint]
    return rng.choice(tuple(SPIRIT_MARK_SETS))


def _select_rarity(rarity_hint: str | int, quality_hint: str, rng: random.Random) -> int:
    if isinstance(rarity_hint, int):
        return max(1, min(5, rarity_hint))
    if isinstance(rarity_hint, str) and rarity_hint.isdigit():
        return max(1, min(5, int(rarity_hint)))
    quality_floor = 3 if quality_hint in {"completed", "excellent"} else 1
    weights = [30, 28, 22, 14, 6]
    rarity = rng.choices([1, 2, 3, 4, 5], weights=weights, k=1)[0]
    return max(quality_floor, rarity)


def _build_entry_id(now: datetime, rng: random.Random) -> str:
    stamp = now.strftime("%Y%m%d%H%M%S")
    return f"sm-{stamp}-{rng.randrange(1000, 10000)}"
