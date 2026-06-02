import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from desktop_sprite.models.inventory import (
    InventoryEntry,
    InventorySnapshot,
    ItemCategory,
    ItemDefinition,
)
from desktop_sprite.ui.inventory_widget import (
    ITEM_CARD_MAX_SIZE,
    ITEM_CARD_MIN_SIZE,
    DraggableSmoothScrollArea,
    InventoryWidget,
)


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


def test_inventory_widget_details_use_scroll_area():
    _app()
    widget = InventoryWidget(_snapshot())

    assert widget.details_card.scroll.widget() is widget.details_card.content
    assert widget.details_card.scroll.widgetResizable()
    assert isinstance(widget.scroll, DraggableSmoothScrollArea)
    assert isinstance(widget.details_card.scroll, DraggableSmoothScrollArea)
    assert "background: transparent" in widget.grid_content.styleSheet()
    assert "background: transparent" in widget.details_card.content.styleSheet()


def test_inventory_widget_cards_are_adaptive_squares_without_names():
    app = _app()
    widget = InventoryWidget(_snapshot())
    widget.resize(720, 560)
    widget.show()
    app.processEvents()

    assert all(card.width() == card.height() for card in widget.cards)
    assert all(ITEM_CARD_MIN_SIZE <= card.width() <= ITEM_CARD_MAX_SIZE for card in widget.cards)
    assert all(not hasattr(card, "name_label") for card in widget.cards)


def test_draggable_scroll_area_scrolls_content_with_mouse_drag():
    app = _app()
    scroll = DraggableSmoothScrollArea()
    scroll.resize(200, 160)
    scroll.setWidgetResizable(True)
    content = QWidget()
    content.setMinimumHeight(600)
    QVBoxLayout(content)
    scroll.setWidget(content)
    scroll.show()
    app.processEvents()

    _send_mouse_event(
        content,
        QEvent.Type.MouseButtonPress,
        QPointF(50, 100),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
    )
    _send_mouse_event(
        content,
        QEvent.Type.MouseMove,
        QPointF(50, 40),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
    )
    _send_mouse_event(
        content,
        QEvent.Type.MouseButtonRelease,
        QPointF(50, 40),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
    )

    assert scroll.verticalScrollBar().value() == 60


def test_inventory_widget_clicking_card_updates_selected_entry():
    _app()
    widget = InventoryWidget(_snapshot())
    widget.show()

    QTest.mouseClick(widget.cards[1], Qt.MouseButton.LeftButton)

    assert widget.selected_entry_id == "spirit-002"


def test_inventory_widget_clears_details_for_empty_category():
    _app()
    widget = InventoryWidget(_snapshot())

    widget.select_category("empty")

    assert widget.selected_entry_id is None
    assert widget.cards == []
    assert not widget.empty_label.isHidden()
    assert widget.details_card.name_label.text() == ""
    assert widget.details_card.description_label.text() == ""


def _send_mouse_event(
    target: QWidget,
    event_type: QEvent.Type,
    position: QPointF,
    button: Qt.MouseButton,
    buttons: Qt.MouseButton,
) -> None:
    event = QMouseEvent(
        event_type,
        position,
        position,
        button,
        buttons,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(target, event)
