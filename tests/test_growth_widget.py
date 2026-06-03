import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from desktop_sprite.models.inventory import (
    InventoryEntry,
    InventorySnapshot,
    ItemCategory,
    ItemDefinition,
)
from desktop_sprite.models.spirit_mark import SpiritMark, SpiritMarkInventory, SpiritMarkStat
from desktop_sprite.ui.growth_widget import PetGrowthWidget, SpiritMarkEquipmentPage


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _snapshot() -> InventorySnapshot:
    categories = (ItemCategory("spirit_mark", "灵痕", 0),)
    definitions = {
        "spirit.core": ItemDefinition("spirit.core", "spirit_mark", "灵核", "灵痕", "missing.png", False),
    }
    entries = (
        InventoryEntry("mark-core-001", "spirit.core"),
        InventoryEntry("mark-core-002", "spirit.core"),
    )
    return InventorySnapshot(categories, definitions, entries)


def _mark(entry_id: str, *, slot_id: str = "core", equipped: bool = False) -> SpiritMark:
    return SpiritMark(
        entry_id=entry_id,
        name=f"静默守护·{entry_id}",
        slot_id=slot_id,
        set_id="silent_guardian",
        rarity=3,
        main_stat=SpiritMarkStat("稳定", 9),
        sub_stats=(SpiritMarkStat("亲和", 4),),
        equipped=equipped,
        source_description="一段安静的来源记录。",
    )


def test_growth_widget_has_attributes_and_spirit_mark_sections():
    _app()

    widget = PetGrowthWidget(_snapshot(), SpiritMarkInventory((_mark("mark-core-001"),)))

    assert widget.objectName() == "petGrowthPage"
    assert widget.pages.currentWidget() is widget.attributes_page

    widget.section_navigation.setCurrentItem("spiritMarks")

    assert widget.pages.currentWidget() is widget.equipment_page


def test_spirit_mark_equipment_opens_slot_page_and_lists_only_backpack_marks():
    _app()
    inventory = SpiritMarkInventory(
        (
            _mark("mark-core-001", equipped=True),
            _mark("mark-core-002"),
            _mark("not-in-backpack"),
        )
    )
    page = SpiritMarkEquipmentPage(_snapshot(), inventory)

    assert page.detail_stack.currentWidget() is page.overview_page

    page.open_slot("core")

    assert page.detail_stack.currentWidget() is page.slot_page
    assert [card.entry.entry_id for card in page._candidate_cards] == ["mark-core-001", "mark-core-002"]
    assert page.selected_entry_id == "mark-core-001"
    assert page.action_button.text() == "卸下"


def test_spirit_mark_equipment_replaces_same_slot_exclusively():
    _app()
    saved: list[SpiritMarkInventory] = []
    inventory = SpiritMarkInventory((_mark("mark-core-001", equipped=True), _mark("mark-core-002")))
    page = SpiritMarkEquipmentPage(_snapshot(), inventory, saved.append)
    page.open_slot("core")

    page.select_entry("mark-core-002")
    assert page.action_button.text() == "替换"
    page.equip_selected()

    updated = saved[-1]
    assert updated.mark_by_entry_id("mark-core-001").equipped is False
    assert updated.mark_by_entry_id("mark-core-002").equipped is True


def test_spirit_mark_equipment_can_unequip_selected_mark():
    _app()
    saved: list[SpiritMarkInventory] = []
    page = SpiritMarkEquipmentPage(
        _snapshot(),
        SpiritMarkInventory((_mark("mark-core-001", equipped=True),)),
        saved.append,
    )
    page.open_slot("core")

    page.unequip_selected()

    assert saved[-1].mark_by_entry_id("mark-core-001").equipped is False
