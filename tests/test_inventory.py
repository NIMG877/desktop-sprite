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


def test_load_inventory_uses_default_entries_and_merges_instance_details(tmp_path):
    catalog_path = _write_catalog(tmp_path)
    default_path = _write_inventory(
        tmp_path / "default_inventory.json",
        [
            {
                "entry_id": "spirit-001",
                "item_id": "spirit.core",
                "details": {"来源": "一次展示", "备注": "首件"},
            },
            {"entry_id": "stack-001", "item_id": "test.stack", "quantity": 4},
        ],
    )

    snapshot = load_inventory(catalog_path, default_path, tmp_path / "inventory.json")

    assert [category.id for category in snapshot.categories] == ["spirit_mark", "test"]
    assert [entry.entry_id for entry in snapshot.entries_for_category("test")] == ["stack-001"]
    assert snapshot.details_for(snapshot.entries[0]) == (
        ("部位", "灵核"),
        ("来源", "一次展示"),
        ("备注", "首件"),
    )


def test_load_inventory_prefers_user_inventory_when_present(tmp_path):
    catalog_path = _write_catalog(tmp_path)
    default_path = _write_inventory(
        tmp_path / "default_inventory.json",
        [{"entry_id": "spirit-001", "item_id": "spirit.core"}],
    )
    user_path = _write_inventory(
        tmp_path / "inventory.json",
        [{"entry_id": "stack-001", "item_id": "test.stack", "quantity": 7}],
    )

    snapshot = load_inventory(catalog_path, default_path, user_path)

    assert [entry.entry_id for entry in snapshot.entries] == ["stack-001"]


def test_invalid_inventory_keeps_catalog_and_returns_empty_entries(tmp_path):
    catalog_path = _write_catalog(tmp_path)
    default_path = _write_inventory(
        tmp_path / "default_inventory.json",
        [{"entry_id": "bad-stack", "item_id": "spirit.core", "quantity": 2}],
    )

    snapshot = load_inventory(catalog_path, default_path)

    assert [category.id for category in snapshot.categories] == ["spirit_mark", "test"]
    assert snapshot.item_definitions
    assert snapshot.entries == ()


def test_unknown_inventory_item_returns_empty_entries(tmp_path):
    catalog_path = _write_catalog(tmp_path)
    default_path = _write_inventory(
        tmp_path / "default_inventory.json",
        [{"entry_id": "unknown", "item_id": "missing"}],
    )

    snapshot = load_inventory(catalog_path, default_path)

    assert snapshot.entries == ()


def test_broken_inventory_keeps_catalog_and_returns_empty_entries(tmp_path):
    catalog_path = _write_catalog(tmp_path)
    default_path = tmp_path / "default_inventory.json"
    default_path.write_text("{", encoding="utf-8")

    snapshot = load_inventory(catalog_path, default_path)

    assert [category.id for category in snapshot.categories] == ["spirit_mark", "test"]
    assert snapshot.entries == ()


def test_broken_catalog_returns_fully_empty_snapshot(tmp_path):
    catalog_path = tmp_path / "items.json"
    catalog_path.write_text("{", encoding="utf-8")
    default_path = _write_inventory(tmp_path / "default_inventory.json", [])

    snapshot = load_inventory(catalog_path, default_path)

    assert snapshot.categories == ()
    assert snapshot.item_definitions == {}
    assert snapshot.entries == ()
