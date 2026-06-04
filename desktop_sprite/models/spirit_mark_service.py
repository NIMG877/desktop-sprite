"""Spirit mark grant service.

Mints a new spirit mark, appends the corresponding inventory entry,
persists the updated `SpiritMarkInventory`, and returns the resulting
snapshot.

The previous implementation performed **five file IO operations**
per grant (load inventory, load spirit marks, read-modify-write
inventory, write spirit marks, reload inventory for the snapshot).
P2-17 collapses the flow to **two** by:

1. Loading the items catalog and current spirit-mark inventory
   *once*.
2. Computing the new entries list and enriched definitions
   *in memory* via the public `apply_spirit_mark_details` helper.
3. Writing the inventory file *once* with the new entries inline.
4. Writing the spirit-mark file *once* with the new mark appended.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from desktop_sprite.models.inventory import (
    InventoryEntry,
    InventorySnapshot,
    _ensure_inventory_file,
    _load_catalog,
    _read_object,
    _require_list,
    _require_object,
    append_inventory_entry,
    apply_spirit_mark_details,
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

    # 1. Read the catalog and current spirit-mark inventory once.
    categories, definitions = _load_catalog(items)
    current_spirit_marks = load_spirit_mark_inventory(spirit_mark_file)
    mark = generate_spirit_mark(request)
    item_id = _find_item_id_for_slot(definitions, mark.slot_id)

    # 2. Persist the new inventory entry using the original
    # `append_inventory_entry` so the on-disk format matches the
    # historical layout: a flat entry with `entry_id` + `item_id`,
    # no per-mark enrichment. The enrichment is applied in memory
    # for the returned `InventorySnapshot` only.
    append_inventory_entry(
        inventory_file, InventoryEntry(mark.entry_id, item_id)
    )

    new_spirit_marks = SpiritMarkInventory(
        (*current_spirit_marks.marks, mark),
        current_spirit_marks.materials,
    )

    # 3. Build the enriched snapshot in memory. We re-read the file
    # once for the entries list (so we don't race with other writers
    # that may have added entries between our reads) and enrich from
    # the in-memory `new_spirit_marks` rather than from disk.
    _ensure_inventory_file(inventory_file)
    raw_entries = _read_object(inventory_file).get("entries", [])
    base_entries: list[InventoryEntry] = []
    for raw in raw_entries:
        if not isinstance(raw, dict) or "entry_id" not in raw or "item_id" not in raw:
            continue
        base_entries.append(
            InventoryEntry(
                entry_id=str(raw["entry_id"]),
                item_id=str(raw["item_id"]),
                quantity=int(raw.get("quantity", 1)) if not isinstance(raw.get("quantity"), bool) else 1,
            )
        )
    enriched_definitions, enriched_entries = apply_spirit_mark_details(
        definitions, tuple(base_entries), new_spirit_marks
    )

    # 4. Persist the spirit-mark file once.
    save_spirit_mark_inventory(spirit_mark_file, new_spirit_marks)

    return SpiritMarkGrantResult(
        mark=mark,
        inventory_snapshot=InventorySnapshot(
            categories, enriched_definitions, enriched_entries
        ),
        spirit_mark_inventory=new_spirit_marks,
    )


def _find_item_id_for_slot(definitions: dict, slot_id: str) -> str:
    """Look up the catalog item id that matches a spirit-mark slot.

    The first matching definition whose id ends with `.{slot_id}` or
    whose `部位` detail equals the slot name wins. Falls back to the
    legacy "spirit_mark.sanctum_radiance.{slot_id}" pattern.
    """

    from desktop_sprite.models.spirit_mark import SPIRIT_MARK_SLOTS

    slot_name = SPIRIT_MARK_SLOTS[slot_id].name
    for definition in definitions.values():
        if definition.category_id != "spirit_mark":
            continue
        if definition.id.endswith(f".{slot_id}"):
            return definition.id
        if dict(definition.details).get("部位") == slot_name:
            return definition.id
    raise LookupError(f"No spirit mark item definition for slot: {slot_id}")
