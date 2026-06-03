import json

from desktop_sprite.models.spirit_mark import SPIRIT_MARK_SLOTS, SpiritMarkGrantRequest
from desktop_sprite.models.spirit_mark_service import grant_spirit_mark


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
