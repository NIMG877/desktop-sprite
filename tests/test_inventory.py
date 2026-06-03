import json

from desktop_sprite.models.inventory import load_inventory


def _write_catalog(tmp_path):
    catalog_path = tmp_path / "items.json"
    catalog_path.write_text(
        json.dumps(
            {
                "categories": [
                    {"id": "spirit_mark", "name": "灵痕", "order": 0},
                    {"id": "test", "name": "测试", "order": 1},
                ],
                "items": [
                    {
                        "id": "spirit.core",
                        "category_id": "spirit_mark",
                        "name": "灵核",
                        "description": "不可堆叠的灵痕",
                        "image": "../assets/core.png",
                        "stackable": False,
                        "details": {"部位": "灵核", "来源": "默认来源"},
                    },
                    {
                        "id": "test.stack",
                        "category_id": "test",
                        "name": "测试素材",
                        "description": "可堆叠道具",
                        "image": "../assets/test.png",
                        "stackable": True,
                        "details": {"用途": "测试"},
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return catalog_path


def _write_inventory(path, entries):
    path.write_text(json.dumps({"entries": entries}, ensure_ascii=False), encoding="utf-8")
    return path


def test_load_inventory_uses_inventory_entries_and_merges_instance_details(tmp_path):
    catalog_path = _write_catalog(tmp_path)
    inventory_path = _write_inventory(
        tmp_path / "inventory.json",
        [
            {
                "entry_id": "spirit-001",
                "item_id": "spirit.core",
                "details": {"来源": "一次展示", "备注": "首件"},
            },
            {"entry_id": "stack-001", "item_id": "test.stack", "quantity": 4},
        ],
    )

    snapshot = load_inventory(catalog_path, inventory_path)

    assert [category.id for category in snapshot.categories] == ["spirit_mark", "test"]
    assert [entry.entry_id for entry in snapshot.entries_for_category("test")] == ["stack-001"]
    assert snapshot.details_for(snapshot.entries[0]) == (
        ("部位", "灵核"),
        ("来源", "一次展示"),
        ("备注", "首件"),
    )


def test_load_inventory_creates_empty_inventory_when_missing(tmp_path):
    catalog_path = _write_catalog(tmp_path)
    inventory_path = tmp_path / "inventory.json"

    snapshot = load_inventory(catalog_path, inventory_path)

    assert snapshot.entries == ()
    assert json.loads(inventory_path.read_text(encoding="utf-8")) == {"entries": []}


def test_invalid_inventory_keeps_catalog_and_returns_empty_entries(tmp_path):
    catalog_path = _write_catalog(tmp_path)
    inventory_path = _write_inventory(
        tmp_path / "inventory.json",
        [{"entry_id": "bad-stack", "item_id": "spirit.core", "quantity": 2}],
    )

    snapshot = load_inventory(catalog_path, inventory_path)

    assert [category.id for category in snapshot.categories] == ["spirit_mark", "test"]
    assert snapshot.item_definitions
    assert snapshot.entries == ()


def test_unknown_inventory_item_returns_empty_entries(tmp_path):
    catalog_path = _write_catalog(tmp_path)
    inventory_path = _write_inventory(
        tmp_path / "inventory.json",
        [{"entry_id": "unknown", "item_id": "missing"}],
    )

    snapshot = load_inventory(catalog_path, inventory_path)

    assert snapshot.entries == ()


def test_broken_inventory_keeps_catalog_and_returns_empty_entries(tmp_path):
    catalog_path = _write_catalog(tmp_path)
    inventory_path = tmp_path / "inventory.json"
    inventory_path.write_text("{", encoding="utf-8")

    snapshot = load_inventory(catalog_path, inventory_path)

    assert [category.id for category in snapshot.categories] == ["spirit_mark", "test"]
    assert snapshot.entries == ()


def test_broken_catalog_returns_fully_empty_snapshot(tmp_path):
    catalog_path = tmp_path / "items.json"
    catalog_path.write_text("{", encoding="utf-8")
    inventory_path = _write_inventory(tmp_path / "inventory.json", [])

    snapshot = load_inventory(catalog_path, inventory_path)

    assert snapshot.categories == ()
    assert snapshot.item_definitions == {}
    assert snapshot.entries == ()


def test_load_inventory_enriches_existing_spirit_mark_entries_by_entry_id(tmp_path):
    catalog_path = _write_catalog(tmp_path)
    inventory_path = _write_inventory(
        tmp_path / "inventory.json",
        [
            {"entry_id": "mark-001", "item_id": "spirit.core"},
            {"entry_id": "mark-without-traits", "item_id": "spirit.core"},
        ],
    )
    spirit_path = tmp_path / "spirit_marks.json"
    spirit_path.write_text(
        json.dumps(
            {
                "marks": [
                    {
                        "entry_id": "mark-001",
                        "name": "静默守护·灵核",
                        "slot_id": "core",
                        "set_id": "silent_guardian",
                        "rarity": 3,
                        "main_stat": {"name": "稳定", "value": 9},
                        "sub_stats": [{"name": "亲和", "value": 4}],
                        "level": 1,
                        "source_type": "manual",
                        "source_description": "这道灵痕来自一次手动纪念。",
                        "created_at": "2026-06-03T00:00:00+08:00",
                        "favorite": True,
                        "equipped": True,
                    },
                    {
                        "entry_id": "not-in-inventory",
                        "name": "不会显示·灵核",
                        "slot_id": "core",
                        "set_id": "silent_guardian",
                        "rarity": 3,
                        "main_stat": {"name": "稳定", "value": 9},
                    }
                ],
                "materials": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    snapshot = load_inventory(
        catalog_path,
        inventory_path,
        spirit_path,
    )

    spirit_entries = snapshot.entries_for_category("spirit_mark")
    enriched_entry = next(entry for entry in spirit_entries if entry.entry_id == "mark-001")
    plain_entry = next(entry for entry in spirit_entries if entry.entry_id == "mark-without-traits")

    assert [entry.entry_id for entry in spirit_entries] == ["mark-001", "mark-without-traits"]
    assert snapshot.definition_for(enriched_entry).name == "静默守护·灵核"
    assert snapshot.definition_for(plain_entry).name == "灵核"
    assert ("来源描述", "这道灵痕来自一次手动纪念。") in snapshot.details_for(enriched_entry)
    assert ("装备", "是") in snapshot.details_for(enriched_entry)
