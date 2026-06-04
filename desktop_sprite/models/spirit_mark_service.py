"""Spirit mark grant service.

Mints a new spirit mark and persists the resulting inventory +
spirit-mark state. The on-disk side effects of one grant are:

* ``spirit_marks.json`` — appended with the new mark.
* ``inventory.json`` — appended with a flat entry pointing at the
  base spirit-mark definition (no per-mark enrichment on disk; the
  enrichment is computed at load time by :func:`apply_spirit_mark_details`).

Both writes happen inside :func:`atomic_write` so a crash or
``OSError`` between them rolls back to the pre-grant state — the
inventory never references a mark that isn't on disk, and vice versa.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from desktop_sprite.models.inventory import (
    InventoryEntry,
    InventorySnapshot,
    _ensure_inventory_file,
    _load_catalog,
    _load_entries,
    apply_spirit_mark_details,
    write_inventory_entries,
)
from desktop_sprite.models.spirit_mark import (
    SpiritMark,
    SpiritMarkGrantRequest,
    SpiritMarkInventory,
    generate_spirit_mark,
    load_spirit_mark_inventory,
    save_spirit_mark_inventory,
)
from desktop_sprite.utils.safe_io import atomic_write


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

    # 2. Make sure the inventory file exists, then read & validate
    # the current entries exactly the way ``load_inventory`` would.
    # We use the same parser so a corrupt file produces the same
    # ``InventoryValidationError`` a regular load would.
    _ensure_inventory_file(inventory_file)
    base_entries = _load_entries(inventory_file, definitions)
    if any(entry.entry_id == mark.entry_id for entry in base_entries):
        raise LookupError(f"Duplicate spirit mark entry id: {mark.entry_id}")

    new_entry = InventoryEntry(mark.entry_id, item_id)
    merged_entries = (*base_entries, new_entry)
    new_spirit_marks = SpiritMarkInventory(
        (*current_spirit_marks.marks, mark),
        current_spirit_marks.materials,
    )

    # 3. Build the enriched snapshot *in memory* before any write
    # happens. This is the same logic ``load_inventory`` runs at read
    # time, just driven by the in-memory ``new_spirit_marks`` rather
    # than a fresh on-disk read.
    enriched_definitions, enriched_entries = apply_spirit_mark_details(
        definitions, merged_entries, new_spirit_marks
    )

    # 4. Persist both files inside one atomic transaction. If either
    # write fails (disk full, permission denied, process killed mid
    # rename), the captured pre-state is restored and the grant leaves
    # zero observable side effect.
    with atomic_write([inventory_file, spirit_mark_file]):
        write_inventory_entries(inventory_file, merged_entries)
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

    The first matching definition whose id ends with ``.{slot_id}`` or
    whose ``部位`` detail equals the slot name wins.
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
