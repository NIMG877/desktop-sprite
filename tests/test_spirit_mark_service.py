import json

import pytest

from desktop_sprite.models.spirit_mark import SPIRIT_MARK_SLOTS, SpiritMarkGrantRequest
from desktop_sprite.models.spirit_mark_service import grant_spirit_mark
from desktop_sprite.models.inventory import InventoryValidationError
from desktop_sprite.utils.safe_io import write_json_atomic


def _write_spirit_mark_catalog(path):
    path.write_text(
        json.dumps(
            {
                "categories": [
                    {"id": "spirit_mark", "name": "灵痕", "order": 0},
                ],
                "items": [
                    {
                        "id": f"spirit.{slot_id}",
                        "category_id": "spirit_mark",
                        "name": slot.name,
                        "description": f"{slot.name}灵痕",
                        "image": "../assets/spirit_mark.png",
                        "stackable": False,
                        "details": {"部位": slot.name},
                    }
                    for slot_id, slot in SPIRIT_MARK_SLOTS.items()
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def test_grant_spirit_mark_writes_inventory_and_spirit_mark_files(tmp_path):
    items_path = _write_spirit_mark_catalog(tmp_path / "items.json")
    inventory_path = tmp_path / "inventory.json"
    spirit_mark_path = tmp_path / "spirit_marks.json"

    result = grant_spirit_mark(
        SpiritMarkGrantRequest(
            entry_id="mark-service-001",
            source_type="debug",
            source_id="debug-request",
            source_description="由正式灵痕授予流程生成。",
            quality_hint="completed",
        ),
        items_path=items_path,
        inventory_path=inventory_path,
        spirit_mark_path=spirit_mark_path,
    )

    raw_inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    raw_spirit_marks = json.loads(spirit_mark_path.read_text(encoding="utf-8"))

    assert raw_inventory == {
        "entries": [
            {
                "entry_id": "mark-service-001",
                "item_id": f"spirit.{result.mark.slot_id}",
            }
        ]
    }
    assert [mark["entry_id"] for mark in raw_spirit_marks["marks"]] == ["mark-service-001"]
    assert result.spirit_mark_inventory.mark_by_entry_id("mark-service-001") == result.mark
    assert [entry.entry_id for entry in result.inventory_snapshot.entries] == ["mark-service-001"]
    assert result.inventory_snapshot.definition_for(result.inventory_snapshot.entries[0]).name == result.mark.name


def test_grant_spirit_mark_rejects_inventory_with_null_entries(tmp_path):
    """A user-edited ``inventory.json`` with ``entries: null`` used to
    crash the service with ``TypeError: 'NoneType' is not iterable``.
    It now surfaces a clear ``InventoryValidationError`` from the
    underlying parser."""
    items_path = _write_spirit_mark_catalog(tmp_path / "items.json")
    inventory_path = tmp_path / "inventory.json"
    spirit_mark_path = tmp_path / "spirit_marks.json"
    write_json_atomic(inventory_path, {"entries": None})

    with pytest.raises(InventoryValidationError):
        grant_spirit_mark(
            SpiritMarkGrantRequest(
                entry_id="mark-null-entries",
                source_type="debug",
                source_id="debug-request",
                source_description="故意写坏的 inventory.json。",
                quality_hint="completed",
            ),
            items_path=items_path,
            inventory_path=inventory_path,
            spirit_mark_path=spirit_mark_path,
        )


def test_grant_spirit_mark_rejects_inventory_with_string_entries(tmp_path):
    items_path = _write_spirit_mark_catalog(tmp_path / "items.json")
    inventory_path = tmp_path / "inventory.json"
    spirit_mark_path = tmp_path / "spirit_marks.json"
    write_json_atomic(inventory_path, {"entries": "not a list"})

    with pytest.raises(InventoryValidationError):
        grant_spirit_mark(
            SpiritMarkGrantRequest(
                entry_id="mark-string-entries",
                source_type="debug",
                source_id="debug-request",
                source_description="故意写坏的 inventory.json。",
                quality_hint="completed",
            ),
            items_path=items_path,
            inventory_path=inventory_path,
            spirit_mark_path=spirit_mark_path,
        )


def test_grant_spirit_mark_is_atomic_on_failure(tmp_path, monkeypatch):
    """If the second of the two file writes blows up, both files must
    be restored to their pre-grant state — no orphan inventory entry
    pointing at a non-existent spirit mark.

    Note: ``load_spirit_mark_inventory`` auto-creates the marks file
    if missing, so by the time ``atomic_write`` captures pre-state
    the file already exists with an empty inventory. The rollback
    restores that empty state."""
    items_path = _write_spirit_mark_catalog(tmp_path / "items.json")
    inventory_path = tmp_path / "inventory.json"
    spirit_mark_path = tmp_path / "spirit_marks.json"

    # Trigger the auto-create of the spirit-mark file by loading it
    # once. This mirrors what production callers do before granting.
    from desktop_sprite.models.spirit_mark import load_spirit_mark_inventory
    load_spirit_mark_inventory(spirit_mark_path)
    pre_grant_marks = json.loads(spirit_mark_path.read_text(encoding="utf-8"))

    write_json_atomic(inventory_path, {"entries": []})
    pre_grant_inventory = json.loads(inventory_path.read_text(encoding="utf-8"))

    def fail_on_save(path, inventory):
        # Simulate the second write blowing up; pretend the first
        # write (inventory) already landed successfully.
        write_json_atomic(path, {"marks": []})
        raise OSError("simulated disk full")

    from desktop_sprite.models import spirit_mark_service
    monkeypatch.setattr(spirit_mark_service, "save_spirit_mark_inventory", fail_on_save)

    with pytest.raises(OSError):
        grant_spirit_mark(
            SpiritMarkGrantRequest(
                entry_id="mark-atomic-001",
                source_type="debug",
                source_id="debug-request",
                source_description="原子写测试。",
                quality_hint="completed",
            ),
            items_path=items_path,
            inventory_path=inventory_path,
            spirit_mark_path=spirit_mark_path,
        )

    # Both files must be back to their pre-grant state.
    post_inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    post_marks = json.loads(spirit_mark_path.read_text(encoding="utf-8"))
    assert post_inventory == pre_grant_inventory
    assert post_marks == pre_grant_marks
    # No orphan mark entry_id should appear in either file.
    assert "mark-atomic-001" not in post_inventory.get("entries", [])
    assert "mark-atomic-001" not in {m.get("entry_id") for m in post_marks.get("marks", [])}
