from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from desktop_sprite.models.inventory import (
    InventoryEntry,
    InventorySnapshot,
    append_inventory_entry,
    load_inventory,
    spirit_mark_item_id_for_slot,
)
from desktop_sprite.models.spirit_mark import (
    SpiritMark,
    SpiritMarkGrantRequest,
    SpiritMarkInventory,
    generate_spirit_mark,
    load_spirit_mark_inventory,
    save_spirit_mark_inventory,
)


@dataclass(frozen=True, slots=True)
class SpiritMarkGrantResult:
    mark: SpiritMark
    inventory_snapshot: InventorySnapshot
    spirit_mark_inventory: SpiritMarkInventory


def grant_spirit_mark(
    request: SpiritMarkGrantRequest,
    *,
    items_path: str | Path,
    inventory_path: str | Path,
    spirit_mark_path: str | Path,
) -> SpiritMarkGrantResult:
    items = Path(items_path)
    inventory_file = Path(inventory_path)
    spirit_mark_file = Path(spirit_mark_path)

    current_snapshot = load_inventory(items, inventory_file, spirit_mark_file)
    current_spirit_marks = load_spirit_mark_inventory(spirit_mark_file)
    mark = generate_spirit_mark(request)
    item_id = spirit_mark_item_id_for_slot(current_snapshot, mark.slot_id)

    append_inventory_entry(inventory_file, InventoryEntry(mark.entry_id, item_id))
    updated_spirit_marks = SpiritMarkInventory(
        (*current_spirit_marks.marks, mark),
        current_spirit_marks.materials,
    )
    save_spirit_mark_inventory(spirit_mark_file, updated_spirit_marks)

    return SpiritMarkGrantResult(
        mark=mark,
        inventory_snapshot=load_inventory(items, inventory_file, spirit_mark_file),
        spirit_mark_inventory=updated_spirit_marks,
    )
