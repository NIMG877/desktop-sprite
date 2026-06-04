import os
from dataclasses import replace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from desktop_sprite.models.pet_attribute import PetAttributeSheet
from desktop_sprite.models.inventory import (
    InventoryEntry,
    InventorySnapshot,
    ItemCategory,
    ItemDefinition,
)
from desktop_sprite.models.spirit_mark import SpiritMark, SpiritMarkInventory, SpiritMarkStat
from desktop_sprite.ui.growth_widget import (
    ATTRIBUTE_CATEGORY_TITLES,
    DraggableSmoothScrollArea,
    PetGrowthWidget,
    SpiritMarkEquipmentPage,
)
from desktop_sprite.utils.config import (
    AppConfig,
    AttributesConfig,
    BehaviorConfig,
    CharacterConfig,
    InteractionConfig,
    PetConfig,
    PhysicsConfig,
    RuntimeConfig,
)


def _attributes() -> AttributesConfig:
    return AttributesConfig(
        wander=100,
        vigor=210,
        recovery=5,
        awareness=100,
        focus=2,
        satiety=100,
        spark=5,
        radiance=50,
        trail=0,
        resonance=0,
        aura=50,
        arcana=100,
        attunement=100,
    )


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _config() -> AppConfig:
    return AppConfig(
        app=RuntimeConfig(60, True, False, "INFO"),
        pet=PetConfig(84, 104, 300, 300),
        physics=PhysicsConfig(1800, 120, 92, 180, -520, 1100, 0.65, 10),
        behavior=BehaviorConfig(1.0, 2.5, True, 3.5),
        interaction=InteractionConfig(True, True, True, True, 220, 80),
        character=CharacterConfig("pet", {"pet": "characters/pet.json"}),
        attributes=_attributes(),
    )


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
    assert isinstance(widget.attributes_page.summary_scroll, DraggableSmoothScrollArea)
    assert isinstance(widget.attributes_page.detail_scroll, DraggableSmoothScrollArea)
    assert widget.attributes_page.summary_detail_button.text() == "详细属性"
    assert widget.attributes_page.detail_summary_button.text() == "属性"

    widget.section_navigation.setCurrentItem("spiritMarks")

    assert widget.pages.currentWidget() is widget.equipment_page


def test_growth_widget_attribute_page_reflects_spirit_mark_modifiers():
    _app()
    mark = _mark("mark-core-001", equipped=True)
    mark = replace(mark, main_stat=SpiritMarkStat("机动", 10), sub_stats=())
    widget = PetGrowthWidget(
        _snapshot(),
        SpiritMarkInventory((mark,)),
        PetAttributeSheet.from_config(_config()),
    )

    assert widget.attributes_page._summary_value_labels["mobility"].text() == "130"
    assert "radiance" not in widget.attributes_page._summary_value_labels


def test_growth_widget_attribute_details_show_categories_base_bonus_and_tooltips():
    _app()
    inventory = SpiritMarkInventory(
        (
            replace(
                _mark("mark-core-001", equipped=True),
                main_stat=SpiritMarkStat("机动", 12),
                sub_stats=(SpiritMarkStat("机动", 10, "percent"),),
            ),
        )
    )
    widget = PetGrowthWidget(_snapshot(), inventory, PetAttributeSheet.from_config(_config()))

    widget.attributes_page.show_details()

    assert len(widget.attributes_page._detail_base_labels) == 16
    assert set(ATTRIBUTE_CATEGORY_TITLES) == {"basic", "visual", "special"}
    assert widget.attributes_page._detail_base_labels["mobility"].text() == "120"
    assert "white" in widget.attributes_page._detail_base_labels["mobility"].styleSheet()
    assert widget.attributes_page._detail_base_labels["mobility"].alignment() & Qt.AlignmentFlag.AlignRight
    assert widget.attributes_page._detail_bonus_labels["mobility"].text() == "+24"
    assert widget.attributes_page._detail_bonus_labels["mobility"].alignment() & Qt.AlignmentFlag.AlignLeft
    assert "基础水平移动速度" in widget.attributes_page._detail_help_icons["mobility"].toolTip()
    assert "walk_speed" in widget.attributes_page._detail_help_icons["mobility"].toolTip()
    assert widget.attributes_page._detail_base_labels["radiance"].text() == "50"
    assert widget.attributes_page._detail_bonus_labels["radiance"].text() == ""
    assert not widget.attributes_page._detail_bonus_labels["radiance"].isHidden()


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
