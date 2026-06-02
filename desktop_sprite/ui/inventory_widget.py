from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path
from weakref import WeakSet

from PySide6.QtCore import QEvent, QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
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


ITEM_CARD_MIN_SIZE = 80
ITEM_CARD_MAX_SIZE = 112
GRID_SPACING = 10
ITEM_CARD_MARGIN = 8
GRID_RESIZE_DEBOUNCE_MS = 60


class DraggableSmoothScrollArea(SmoothScrollArea):
    """Smooth scroll area that also supports mouse drag scrolling."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._drag_start_position: QPoint | None = None
        self._drag_last_position: QPoint | None = None
        self._is_drag_scrolling = False
        self._watched_widgets: WeakSet[QWidget] = WeakSet()
        self.viewport().installEventFilter(self)

    def setWidget(self, widget: QWidget) -> None:
        super().setWidget(widget)
        self._watch_tree(widget)

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.ChildAdded:
            child = event.child()
            if isinstance(child, QWidget):
                self._watch_tree(child)

        if not self._is_scroll_surface(watched):
            return super().eventFilter(watched, event)

        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            position = event.globalPosition().toPoint()
            self._drag_start_position = position
            self._drag_last_position = position
            self._is_drag_scrolling = False

        elif event.type() == QEvent.Type.MouseMove and self._drag_last_position is not None:
            if not event.buttons() & Qt.MouseButton.LeftButton:
                self._reset_drag()
                return super().eventFilter(watched, event)

            position = event.globalPosition().toPoint()
            if not self._is_drag_scrolling:
                distance = (position - self._drag_start_position).manhattanLength()
                if distance < QApplication.startDragDistance():
                    return super().eventFilter(watched, event)
                self._is_drag_scrolling = True

            delta = position - self._drag_last_position
            self._drag_last_position = position
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return True

        elif event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            was_drag_scrolling = self._is_drag_scrolling
            self._reset_drag()
            if was_drag_scrolling:
                event.accept()
                return True

        return super().eventFilter(watched, event)

    def _is_scroll_surface(self, watched) -> bool:
        content = self.widget()
        return (
            watched is self.viewport()
            or watched is content
            or (content is not None and isinstance(watched, QWidget) and content.isAncestorOf(watched))
        )

    def _watch_tree(self, widget: QWidget) -> None:
        if widget in self._watched_widgets:
            return
        self._watched_widgets.add(widget)
        widget.installEventFilter(self)
        for child in widget.findChildren(QWidget):
            if child in self._watched_widgets:
                continue
            self._watched_widgets.add(child)
            child.installEventFilter(self)

    def _reset_drag(self) -> None:
        self._drag_start_position = None
        self._drag_last_position = None
        self._is_drag_scrolling = False


class InventoryItemCard(CardWidget):
    entryClicked = Signal(str)

    def __init__(
        self,
        entry: InventoryEntry,
        definition: ItemDefinition,
        parent: QWidget | None = None,
        edge: int = ITEM_CARD_MAX_SIZE,
    ) -> None:
        super().__init__(parent)
        self.entry = entry
        self.definition = definition
        self.setObjectName(f"inventoryItemCard_{entry.entry_id}")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._selected = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(ITEM_CARD_MARGIN, ITEM_CARD_MARGIN, ITEM_CARD_MARGIN, ITEM_CARD_MARGIN)
        layout.setSpacing(0)

        self.image_container = QWidget(self)
        image_layout = QGridLayout(self.image_container)
        image_layout.setContentsMargins(0, 0, 0, 0)

        self.image_label = QLabel(self.image_container)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image_layout.addWidget(self.image_label, 0, 0)

        self.quantity_label = CaptionLabel(self.image_container)
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
        layout.addWidget(self.image_container)
        self.set_card_size(edge)
        self.set_selected(False)

    def set_card_size(self, edge: int) -> None:
        self.setFixedSize(edge, edge)
        image_edge = edge - 2 * ITEM_CARD_MARGIN
        self.image_container.setFixedSize(image_edge, image_edge)
        self.image_label.setPixmap(_load_pixmap(self.definition.image, QSize(image_edge, image_edge)))

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self.entryClicked.emit(self.entry.entry_id)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self._selected:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#60cdff"), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 7, 7)


class InventoryDetailsCard(CardWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("inventoryDetailsCard")
        self.setMinimumWidth(236)
        self.setMaximumWidth(300)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.scroll = DraggableSmoothScrollArea(self)
        self.scroll.setObjectName("inventoryDetailsScroll")
        self.scroll.setWidgetResizable(True)
        self.content = QWidget(self.scroll)
        self.content.setObjectName("inventoryDetailsContent")
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(18, 18, 18, 18)
        content_layout.setSpacing(10)
        self.scroll.setWidget(self.content)
        self.scroll.enableTransparentBackground()
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
        self._cards_by_category: dict[str, list[InventoryItemCard]] = {}
        self._column_count = 0
        self._card_size = 0
        self._grid_rebuild_timer = QTimer(self)
        self._grid_rebuild_timer.setSingleShot(True)
        self._grid_rebuild_timer.setInterval(GRID_RESIZE_DEBOUNCE_MS)
        self._grid_rebuild_timer.timeout.connect(self._rebuild_grid)

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

        self.grid_card = CardWidget(self)
        self.grid_card.setObjectName("inventoryGridCard")
        grid_card_layout = QVBoxLayout(self.grid_card)
        grid_card_layout.setContentsMargins(12, 12, 12, 12)

        self.scroll = DraggableSmoothScrollArea(self.grid_card)
        self.scroll.setObjectName("inventoryGridScroll")
        self.scroll.setWidgetResizable(True)
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
        self.scroll.enableTransparentBackground()
        self.scroll.viewport().installEventFilter(self)
        grid_card_layout.addWidget(self.scroll)
        content_layout.addWidget(self.grid_card, 1)

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
            self._grid_rebuild_timer.start()
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
        self._grid_rebuild_timer.stop()
        self._clear_grid(delete_widgets=False)
        for card in self.cards:
            card.hide()

        category_id = self.current_category_id or ""
        cards = self._cards_by_category.get(category_id)
        if cards is None:
            _column_count, card_size = self._grid_metrics()
            cards = []
            for entry in entries:
                definition = self.snapshot.definition_for(entry)
                card = InventoryItemCard(entry, definition, self.grid_content, edge=card_size)
                card.entryClicked.connect(self.select_entry)
                cards.append(card)
            self._cards_by_category[category_id] = cards
        self.cards = cards
        self._column_count = 0
        self._card_size = 0
        self._rebuild_grid()

    def _rebuild_grid(self) -> None:
        column_count, card_size = self._grid_metrics()

        if column_count == self._column_count and card_size == self._card_size:
            return

        if column_count == self._column_count:
            self._card_size = card_size
            for card in self.cards:
                card.set_card_size(card_size)
            return

        self._clear_grid(delete_widgets=False)
        self._column_count = column_count
        self._card_size = card_size
        for index, card in enumerate(self.cards):
            if card.width() != card_size:
                card.set_card_size(card_size)
            card.show()
            self.grid_layout.addWidget(card, index // column_count, index % column_count)
        if not self.cards:
            self.grid_layout.addWidget(self.empty_label, 0, 0)

    def _grid_metrics(self) -> tuple[int, int]:
        viewport_width = max(1, self.scroll.viewport().width() - self.grid_layout.contentsMargins().right())
        column_count = max(1, math.ceil((viewport_width + GRID_SPACING) / (ITEM_CARD_MAX_SIZE + GRID_SPACING)))
        card_size = (viewport_width - GRID_SPACING * (column_count - 1)) // column_count
        while column_count > 1 and card_size < ITEM_CARD_MIN_SIZE:
            column_count -= 1
            card_size = (viewport_width - GRID_SPACING * (column_count - 1)) // column_count
        card_size = max(ITEM_CARD_MIN_SIZE, min(card_size, ITEM_CARD_MAX_SIZE))
        return column_count, card_size

    def _clear_grid(self, *, delete_widgets: bool) -> None:
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if delete_widgets and widget is not None and widget is not self.empty_label:
                widget.deleteLater()


def _load_pixmap(path: Path, size: QSize) -> QPixmap:
    return _load_scaled_pixmap(str(path), size.width(), size.height())


@lru_cache(maxsize=256)
def _load_scaled_pixmap(path: str, width: int, height: int) -> QPixmap:
    pixmap = _load_source_pixmap(path)
    if pixmap.isNull():
        return pixmap
    return pixmap.scaled(
        QSize(width, height),
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


@lru_cache(maxsize=32)
def _load_source_pixmap(path: str) -> QPixmap:
    return QPixmap(path)
