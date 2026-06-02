from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtGui import QMouseEvent, QPixmap
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    SegmentedWidget,
    SmoothScrollArea,
    SubtitleLabel,
    TitleLabel,
)

from desktop_sprite.models.inventory import (
    InventoryEntry,
    InventorySnapshot,
    ItemCategory,
    ItemDefinition,
)


CARD_WIDTH = 148
CARD_HEIGHT = 178
GRID_SPACING = 12


class InventoryItemCard(CardWidget):
    entryClicked = Signal(str)

    def __init__(
        self,
        entry: InventoryEntry,
        definition: ItemDefinition,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.entry = entry
        self.definition = definition
        self.setObjectName(f"inventoryItemCard_{entry.entry_id}")
        self.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        image_container = QWidget(self)
        image_container.setFixedHeight(112)
        image_layout = QGridLayout(image_container)
        image_layout.setContentsMargins(0, 0, 0, 0)

        self.image_label = QLabel(image_container)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setPixmap(_load_pixmap(definition.image, QSize(112, 112)))
        image_layout.addWidget(self.image_label, 0, 0)

        self.quantity_label = CaptionLabel(image_container)
        self.quantity_label.setObjectName("inventoryQuantityLabel")
        self.quantity_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.quantity_label.setText(f"x{entry.quantity}")
        self.quantity_label.setVisible(definition.stackable)
        self.quantity_label.setStyleSheet(
            "background: rgba(0, 0, 0, 180); border-radius: 8px; padding: 2px 6px;"
        )
        image_layout.addWidget(
            self.quantity_label,
            0,
            0,
            alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
        )
        layout.addWidget(image_container)

        self.name_label = BodyLabel(definition.name, self)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setWordWrap(True)
        layout.addWidget(self.name_label, 1)
        self.set_selected(False)

    def set_selected(self, selected: bool) -> None:
        border = "2px solid #60cdff" if selected else "1px solid rgba(255, 255, 255, 32)"
        self.setStyleSheet(f"InventoryItemCard {{ border: {border}; border-radius: 8px; }}")

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self.entryClicked.emit(self.entry.entry_id)


class InventoryDetailsCard(CardWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("inventoryDetailsCard")
        self.setMinimumWidth(236)
        self.setMaximumWidth(300)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.scroll = SmoothScrollArea(self)
        self.scroll.setObjectName("inventoryDetailsScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.enableTransparentBackground()
        self.content = QWidget(self.scroll)
        self.content.setObjectName("inventoryDetailsContent")
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(18, 18, 18, 18)
        content_layout.setSpacing(10)
        self.scroll.setWidget(self.content)
        layout.addWidget(self.scroll)

        self.image_label = QLabel(self.content)
        self.image_label.setObjectName("inventoryDetailsImage")
        self.image_label.setFixedHeight(220)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content_layout.addWidget(self.image_label)

        self.name_label = SubtitleLabel("", self.content)
        self.name_label.setObjectName("inventoryDetailsName")
        self.name_label.setWordWrap(True)
        content_layout.addWidget(self.name_label)

        self.category_label = CaptionLabel("", self.content)
        self.category_label.setObjectName("inventoryDetailsCategory")
        content_layout.addWidget(self.category_label)

        self.description_label = BodyLabel("", self.content)
        self.description_label.setObjectName("inventoryDetailsDescription")
        self.description_label.setWordWrap(True)
        content_layout.addWidget(self.description_label)

        self.details_widget = QWidget(self.content)
        self.details_layout = QVBoxLayout(self.details_widget)
        self.details_layout.setContentsMargins(0, 8, 0, 0)
        self.details_layout.setSpacing(6)
        content_layout.addWidget(self.details_widget)
        content_layout.addStretch(1)
        self.clear()

    def show_entry(
        self,
        entry: InventoryEntry,
        definition: ItemDefinition,
        category: ItemCategory,
        details: tuple[tuple[str, str], ...],
    ) -> None:
        self.image_label.setPixmap(_load_pixmap(definition.image, QSize(220, 220)))
        self.name_label.setText(definition.name)
        self.category_label.setText(category.name)
        self.description_label.setText(definition.description)
        self._clear_details()
        for key, value in details:
            label = BodyLabel(f"{key}：{value}", self.details_widget)
            label.setWordWrap(True)
            self.details_layout.addWidget(label)

    def clear(self) -> None:
        self.image_label.clear()
        self.name_label.clear()
        self.category_label.clear()
        self.description_label.clear()
        self._clear_details()

    def _clear_details(self) -> None:
        while self.details_layout.count():
            item = self.details_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()


class InventoryWidget(QWidget):
    def __init__(
        self,
        snapshot: InventorySnapshot,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("inventoryPage")
        self.snapshot = snapshot
        self.current_category_id: str | None = None
        self.selected_entry_id: str | None = None
        self.cards: list[InventoryItemCard] = []
        self._entries_by_id = {entry.entry_id: entry for entry in snapshot.entries}
        self._categories_by_id = {category.id: category for category in snapshot.categories}
        self._column_count = 0

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(48, 72, 48, 32)
        root_layout.setSpacing(16)
        root_layout.addWidget(TitleLabel("背包", self))

        self.category_navigation = SegmentedWidget(self)
        self.category_navigation.setObjectName("inventoryCategoryNavigation")
        self.category_navigation.currentItemChanged.connect(self.select_category)
        for category in snapshot.categories:
            self.category_navigation.addItem(category.id, category.name)
        root_layout.addWidget(self.category_navigation)

        content_layout = QHBoxLayout()
        content_layout.setSpacing(16)

        self.scroll = SmoothScrollArea(self)
        self.scroll.setObjectName("inventoryGridScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.enableTransparentBackground()
        self.grid_content = QWidget(self.scroll)
        self.grid_content.setObjectName("inventoryGridContent")
        self.grid_layout = QGridLayout(self.grid_content)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.grid_layout.setContentsMargins(0, 0, 8, 0)
        self.grid_layout.setHorizontalSpacing(GRID_SPACING)
        self.grid_layout.setVerticalSpacing(GRID_SPACING)
        self.empty_label = BodyLabel("当前分类暂无道具", self.grid_content)
        self.empty_label.setObjectName("inventoryEmptyLabel")
        self.empty_label.hide()
        self.scroll.setWidget(self.grid_content)
        self.scroll.viewport().installEventFilter(self)
        content_layout.addWidget(self.scroll, 1)

        self.details_card = InventoryDetailsCard(self)
        content_layout.addWidget(self.details_card)
        root_layout.addLayout(content_layout, 1)

        if snapshot.categories:
            first_category = snapshot.categories[0]
            self.category_navigation.setCurrentItem(first_category.id)
            if self.current_category_id is None:
                self.select_category(first_category.id)

    def eventFilter(self, watched, event) -> bool:
        if watched is self.scroll.viewport() and event.type() == QEvent.Type.Resize:
            self._rebuild_grid()
        return super().eventFilter(watched, event)

    def select_category(self, category_id: str) -> None:
        if category_id not in self._categories_by_id:
            return
        self.current_category_id = category_id
        if self.category_navigation.currentRouteKey() != category_id:
            was_blocked = self.category_navigation.blockSignals(True)
            self.category_navigation.setCurrentItem(category_id)
            self.category_navigation.blockSignals(was_blocked)
        self._replace_cards(self.snapshot.entries_for_category(category_id))
        if self.cards:
            self.empty_label.hide()
            self.select_entry(self.cards[0].entry.entry_id)
        else:
            self.empty_label.show()
            self.selected_entry_id = None
            self.details_card.clear()

    def select_entry(self, entry_id: str) -> None:
        entry = self._entries_by_id.get(entry_id)
        if entry is None:
            return
        definition = self.snapshot.definition_for(entry)
        if definition.category_id != self.current_category_id:
            return
        self.selected_entry_id = entry_id
        for card in self.cards:
            card.set_selected(card.entry.entry_id == entry_id)
        category = self._categories_by_id[definition.category_id]
        self.details_card.show_entry(
            entry,
            definition,
            category,
            self.snapshot.details_for(entry),
        )

    def _replace_cards(self, entries: tuple[InventoryEntry, ...]) -> None:
        self._clear_grid(delete_widgets=True)
        self.cards = []
        for entry in entries:
            definition = self.snapshot.definition_for(entry)
            card = InventoryItemCard(entry, definition, self.grid_content)
            card.entryClicked.connect(self.select_entry)
            self.cards.append(card)
        self._column_count = 0
        self._rebuild_grid()

    def _rebuild_grid(self) -> None:
        viewport_width = self.scroll.viewport().width()
        column_count = max(1, (viewport_width + GRID_SPACING) // (CARD_WIDTH + GRID_SPACING))
        if column_count == self._column_count:
            return
        self._clear_grid(delete_widgets=False)
        self._column_count = column_count
        for index, card in enumerate(self.cards):
            self.grid_layout.addWidget(card, index // column_count, index % column_count)
        if not self.cards:
            self.grid_layout.addWidget(self.empty_label, 0, 0)

    def _clear_grid(self, *, delete_widgets: bool) -> None:
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if delete_widgets and widget is not None and widget is not self.empty_label:
                widget.deleteLater()


def _load_pixmap(path: Path, size: QSize) -> QPixmap:
    pixmap = QPixmap(str(path))
    if pixmap.isNull():
        return pixmap
    return pixmap.scaled(
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
