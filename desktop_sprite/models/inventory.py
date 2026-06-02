from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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
