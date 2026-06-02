import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from desktop_sprite.models.inventory import (
    InventoryEntry,
    InventorySnapshot,
    ItemCategory,
    ItemDefinition,
)
from desktop_sprite.ui.inventory_widget import InventoryWidget


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _snapshot() -> InventorySnapshot:
    categories = (
        ItemCategory("spirit_mark", "灵痕", 0),
        ItemCategory("test", "测试", 1),
        ItemCategory("empty", "空分类", 2),
    )
    definitions = {
        "spirit.core": ItemDefinition(
            "spirit.core",
            "spirit_mark",
            "灵核",
            "一件不可堆叠的灵痕。",
            Path("missing-core.png"),
            False,
            (("部位", "灵核"),),
        ),
        "test.stack": ItemDefinition(
            "test.stack",
            "test",
            "测试素材",
            "一件可堆叠的测试物品。",
            Path("missing-test.png"),
            True,
            (("用途", "测试"),),
        ),
    }
    entries = (
        InventoryEntry("spirit-001", "spirit.core"),
        InventoryEntry("spirit-002", "spirit.core", details=(("来源", "另一条记录"),)),
        InventoryEntry("stack-001", "test.stack", quantity=3),
    )
    return InventorySnapshot(categories, definitions, entries)


def test_inventory_widget_selects_first_category_and_first_entry():
    _app()

    widget = InventoryWidget(_snapshot())

    assert widget.current_category_id == "spirit_mark"
    assert widget.selected_entry_id == "spirit-001"
    assert widget.details_card.name_label.text() == "灵核"
    assert [card.entry.entry_id for card in widget.cards] == ["spirit-001", "spirit-002"]


def test_inventory_widget_shows_quantity_for_stackable_items():
    _app()
    widget = InventoryWidget(_snapshot())

    widget.select_category("test")

    assert widget.selected_entry_id == "stack-001"
    assert len(widget.cards) == 1
    assert widget.cards[0].quantity_label.text() == "x3"
    assert not widget.cards[0].quantity_label.isHidden()


def test_inventory_widget_clears_details_for_empty_category():
    _app()
    widget = InventoryWidget(_snapshot())

    widget.select_category("empty")

    assert widget.selected_entry_id is None
    assert widget.cards == []
    assert not widget.empty_label.isHidden()
    assert widget.details_card.name_label.text() == ""
    assert widget.details_card.description_label.text() == ""
