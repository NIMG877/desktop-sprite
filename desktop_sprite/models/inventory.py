from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from desktop_sprite.models.spirit_mark import (
    SPIRIT_MARK_CATEGORY_ID,
    SPIRIT_MARK_SETS,
    SPIRIT_MARK_SLOTS,
    SpiritMark,
    load_spirit_mark_inventory,
)


logger = logging.getLogger(__name__)
Details = tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class ItemCategory:
    id: str
    name: str
    order: int


@dataclass(frozen=True, slots=True)
class ItemDefinition:
    id: str
    category_id: str
    name: str
    description: str
    image: Path
    stackable: bool
    details: Details = ()


@dataclass(frozen=True, slots=True)
class InventoryEntry:
    entry_id: str
    item_id: str
    quantity: int = 1
    details: Details = ()


@dataclass(frozen=True, slots=True)
class InventorySnapshot:
    categories: tuple[ItemCategory, ...] = ()
    item_definitions: dict[str, ItemDefinition] = field(default_factory=dict)
    entries: tuple[InventoryEntry, ...] = ()

    @classmethod
    def empty(cls) -> InventorySnapshot:
        return cls()

    def entries_for_category(self, category_id: str) -> tuple[InventoryEntry, ...]:
        return tuple(
            entry
            for entry in self.entries
            if self.item_definitions[entry.item_id].category_id == category_id
        )

    def definition_for(self, entry: InventoryEntry) -> ItemDefinition:
        return self.item_definitions[entry.item_id]

    def details_for(self, entry: InventoryEntry) -> Details:
        definition = self.definition_for(entry)
        merged = dict(definition.details)
        merged.update(entry.details)
        return tuple(merged.items())


class InventoryValidationError(ValueError):
    pass


def load_inventory(
    items_path: str | Path,
    default_inventory_path: str | Path,
    inventory_path: str | Path | None = None,
    default_spirit_mark_path: str | Path | None = None,
    spirit_mark_path: str | Path | None = None,
) -> InventorySnapshot:
    catalog_path = Path(items_path)
    try:
        categories, definitions = _load_catalog(catalog_path)
    except (OSError, json.JSONDecodeError, InventoryValidationError) as exc:
        logger.error("Failed to load item catalog %s: %s", catalog_path, exc)
        return InventorySnapshot.empty()

    snapshot = InventorySnapshot(categories, definitions)
    user_path = Path(inventory_path) if inventory_path is not None else None
    selected_path = user_path if user_path is not None and user_path.is_file() else Path(default_inventory_path)
    try:
        entries = _load_entries(selected_path, definitions)
    except (OSError, json.JSONDecodeError, InventoryValidationError) as exc:
        logger.error("Failed to load inventory %s: %s", selected_path, exc)
        return snapshot
    definitions, entries = _apply_spirit_mark_details(
        catalog_path,
        definitions,
        entries,
        default_spirit_mark_path,
        spirit_mark_path,
    )
    return InventorySnapshot(categories, definitions, entries)


def _load_catalog(path: Path) -> tuple[tuple[ItemCategory, ...], dict[str, ItemDefinition]]:
    data = _read_object(path)
    raw_categories = _require_list(data, "categories")
    categories: list[ItemCategory] = []
    category_ids: set[str] = set()
    for raw_category in raw_categories:
        category = _require_object(raw_category, "category")
        category_id = _require_string(category, "id")
        if category_id in category_ids:
            raise InventoryValidationError(f"Duplicate category id: {category_id}")
        category_ids.add(category_id)
        categories.append(
            ItemCategory(
                id=category_id,
                name=_require_string(category, "name"),
                order=_require_int(category, "order"),
            )
        )

    definitions: dict[str, ItemDefinition] = {}
    for raw_item in _require_list(data, "items"):
        item = _require_object(raw_item, "item")
        item_id = _require_string(item, "id")
        if item_id in definitions:
            raise InventoryValidationError(f"Duplicate item id: {item_id}")
        category_id = _require_string(item, "category_id")
        if category_id not in category_ids:
            raise InventoryValidationError(f"Unknown category id for {item_id}: {category_id}")
        image = path.parent / _require_string(item, "image")
        definitions[item_id] = ItemDefinition(
            id=item_id,
            category_id=category_id,
            name=_require_string(item, "name"),
            description=_require_string(item, "description"),
            image=image.resolve(),
            stackable=_require_bool(item, "stackable"),
            details=_parse_details(item.get("details", {}), f"item {item_id} details"),
        )
    return tuple(sorted(categories, key=lambda category: category.order)), definitions


def _load_entries(
    path: Path,
    definitions: dict[str, ItemDefinition],
) -> tuple[InventoryEntry, ...]:
    data = _read_object(path)
    entries: list[InventoryEntry] = []
    entry_ids: set[str] = set()
    stacked_item_ids: set[str] = set()
    for raw_entry in _require_list(data, "entries"):
        entry = _require_object(raw_entry, "inventory entry")
        entry_id = _require_string(entry, "entry_id")
        if entry_id in entry_ids:
            raise InventoryValidationError(f"Duplicate inventory entry id: {entry_id}")
        entry_ids.add(entry_id)
        item_id = _require_string(entry, "item_id")
        if item_id not in definitions:
            raise InventoryValidationError(f"Unknown inventory item id: {item_id}")
        quantity = _require_int(entry, "quantity", default=1)
        if quantity < 1:
            raise InventoryValidationError(f"Quantity must be at least 1 for {entry_id}")
        definition = definitions[item_id]
        if not definition.stackable and quantity != 1:
            raise InventoryValidationError(f"Non-stackable item {item_id} must have quantity 1")
        if definition.stackable:
            if item_id in stacked_item_ids:
                raise InventoryValidationError(f"Stackable item {item_id} must use one inventory entry")
            stacked_item_ids.add(item_id)
        entries.append(
            InventoryEntry(
                entry_id=entry_id,
                item_id=item_id,
                quantity=quantity,
                details=_parse_details(entry.get("details", {}), f"entry {entry_id} details"),
            )
        )
    return tuple(entries)


def _apply_spirit_mark_details(
    catalog_path: Path,
    definitions: dict[str, ItemDefinition],
    entries: tuple[InventoryEntry, ...],
    default_spirit_mark_path: str | Path | None,
    spirit_mark_path: str | Path | None,
) -> tuple[dict[str, ItemDefinition], tuple[InventoryEntry, ...]]:
    default_path = Path(default_spirit_mark_path) if default_spirit_mark_path is not None else catalog_path.with_name("default_spirit_marks.json")
    user_path = Path(spirit_mark_path) if spirit_mark_path is not None else catalog_path.with_name("spirit_marks.json")
    try:
        spirit_inventory = load_spirit_mark_inventory(default_path, user_path)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        logger.error("Failed to load spirit marks %s: %s", user_path if user_path.is_file() else default_path, exc)
        return definitions, entries
    if not spirit_inventory.marks:
        return definitions, entries

    merged_definitions = dict(definitions)
    marks_by_entry_id = {mark.entry_id: mark for mark in spirit_inventory.marks}
    enriched_entries: list[InventoryEntry] = []
    for entry in entries:
        mark = marks_by_entry_id.get(entry.entry_id)
        if mark is None:
            enriched_entries.append(entry)
            continue
        definition = definitions[entry.item_id]
        if definition.category_id != SPIRIT_MARK_CATEGORY_ID:
            enriched_entries.append(entry)
            continue
        instance_definition = _spirit_mark_definition(mark, definition)
        merged_definitions[instance_definition.id] = instance_definition
        enriched_entries.append(
            replace(
                entry,
                item_id=instance_definition.id,
                details=(*entry.details, *_spirit_mark_entry_details(mark)),
            )
        )
    return merged_definitions, tuple(enriched_entries)


def _spirit_mark_definition(mark: SpiritMark, base_definition: ItemDefinition) -> ItemDefinition:
    slot = SPIRIT_MARK_SLOTS[mark.slot_id]
    spirit_set = SPIRIT_MARK_SETS[mark.set_id]
    return ItemDefinition(
        id=f"{base_definition.id}#{mark.entry_id}",
        category_id=SPIRIT_MARK_CATEGORY_ID,
        name=mark.name,
        description=mark.source_description or f"{spirit_set.style}风格的{slot.name}灵痕。",
        image=base_definition.image,
        stackable=False,
        details=(
            ("来源描述", mark.source_description or "未记录来源"),
            ("套装风格", spirit_set.style),
            ("部位", slot.name),
            ("套装", spirit_set.name),
            ("主词条", f"{mark.main_stat.name} +{mark.main_stat.value}"),
            ("副词条", _format_sub_stats(mark.sub_stats)),
            ("强化等级", f"+{mark.level}/{mark.max_level}"),
            ("稀有度", f"{mark.rarity} 星"),
            ("收藏", "是" if mark.favorite else "否"),
            ("装备", "是" if mark.equipped else "否"),
            ("裂灵痕", "是" if mark.fractured else "否"),
        ),
    )


def _spirit_mark_entry_details(mark: SpiritMark) -> Details:
    details: list[tuple[str, str]] = []
    if mark.source_type:
        details.append(("来源类型", mark.source_type))
    if mark.created_at:
        details.append(("生成时间", mark.created_at))
    if mark.record_tags:
        details.append(("记录标签", "、".join(mark.record_tags)))
    return tuple(details)


def _format_sub_stats(stats: tuple[Any, ...]) -> str:
    if not stats:
        return "无"
    return "、".join(f"{stat.name} +{stat.value}" for stat in stats)


def _read_object(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return _require_object(json.load(file), str(path))


def _require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InventoryValidationError(f"{label} must be an object")
    return value


def _require_list(data: dict[str, Any], key: str) -> list[Any]:
    value = data.get(key)
    if not isinstance(value, list):
        raise InventoryValidationError(f"{key} must be an array")
    return value


def _require_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise InventoryValidationError(f"{key} must be a non-empty string")
    return value


def _require_int(data: dict[str, Any], key: str, *, default: int | None = None) -> int:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise InventoryValidationError(f"{key} must be an integer")
    return value


def _require_bool(data: dict[str, Any], key: str) -> bool:
    value = data.get(key)
    if not isinstance(value, bool):
        raise InventoryValidationError(f"{key} must be a boolean")
    return value


def _parse_details(value: Any, label: str) -> Details:
    details = _require_object(value, label)
    return tuple((str(key), str(detail)) for key, detail in details.items())
