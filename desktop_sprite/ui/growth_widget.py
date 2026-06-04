from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    CaptionLabel,
    FluentIcon as FIF,
    IconWidget,
    SmoothScrollArea,
    PrimaryPushButton,
    PushButton,
    SegmentedWidget,
    SubtitleLabel,
    ToolTipFilter,
    ToolTipPosition,
    TitleLabel,
)

from desktop_sprite.models.inventory import InventorySnapshot
from desktop_sprite.models.pet_attribute import PetAttributeSheet
from desktop_sprite.models.spirit_mark import (
    SPIRIT_MARK_CATEGORY_ID,
    SPIRIT_MARK_SETS,
    SPIRIT_MARK_SLOTS,
    SpiritMark,
    SpiritMarkInventory,
)
from desktop_sprite.ui.inventory_widget import (
    DraggableSmoothScrollArea,
    InventoryDetailsCard,
    InventoryItemCard,
    _load_pixmap,
)


ATTRIBUTE_CATEGORY_TITLES = {
    "basic": "基础属性",
    "visual": "视觉呈现",
    "special": "特殊能力",
}
SUMMARY_ATTRIBUTE_CATEGORY = "basic"
ATTRIBUTE_ICONS = {
    "mobility": FIF.SPEED_HIGH,
    "cling": FIF.LINK,
    "leap": FIF.UP,
    "wander": FIF.COMPASS if hasattr(FIF, "COMPASS") else FIF.MOVE,
    "vigor": FIF.HEART,
    "recovery": FIF.SYNC,
    "awareness": FIF.VIEW,
    "focus": FIF.QUIET_HOURS,
    "satiety": FIF.CAFE,
    "spark": FIF.ASTERISK,
    "radiance": FIF.BRIGHTNESS,
    "trail": FIF.SCROLL,
    "resonance": FIF.FEEDBACK,
    "aura": FIF.PALETTE,
    "arcana": FIF.GAME,
    "attunement": FIF.MIX_VOLUMES,
}


class PetGrowthWidget(QWidget):
    def __init__(
        self,
        inventory_snapshot: InventorySnapshot,
        spirit_mark_inventory: SpiritMarkInventory,
        pet_attribute_sheet: PetAttributeSheet | None = None,
        on_spirit_marks_changed: Callable[[SpiritMarkInventory], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("petGrowthPage")
        self.on_spirit_marks_changed = on_spirit_marks_changed or (lambda _inventory: None)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 72, 48, 32)
        layout.setSpacing(16)
        layout.addWidget(TitleLabel("桌宠养成", self))

        self.section_navigation = SegmentedWidget(self)
        self.section_navigation.setObjectName("growthSectionNavigation")
        self.section_navigation.addItem("attributes", "基本属性")
        self.section_navigation.addItem("spiritMarks", "灵痕装备")
        layout.addWidget(self.section_navigation)

        self.base_attribute_sheet = pet_attribute_sheet or PetAttributeSheet(())
        self.pages = QStackedWidget(self)
        self.attributes_page = PetAttributesPage(
            self.base_attribute_sheet.with_modifiers(spirit_mark_inventory.attribute_modifiers()),
            self,
        )
        self.equipment_page = SpiritMarkEquipmentPage(
            inventory_snapshot,
            spirit_mark_inventory,
            self._handle_spirit_marks_changed,
            self,
        )
        self.pages.addWidget(self.attributes_page)
        self.pages.addWidget(self.equipment_page)
        layout.addWidget(self.pages, 1)

        self.section_navigation.currentItemChanged.connect(self._select_section)
        self.section_navigation.setCurrentItem("attributes")

    def _select_section(self, route_key: str) -> None:
        if route_key == "spiritMarks":
            self.pages.setCurrentWidget(self.equipment_page)
        else:
            self.pages.setCurrentWidget(self.attributes_page)

    def _handle_spirit_marks_changed(self, spirit_mark_inventory: SpiritMarkInventory) -> None:
        self.attributes_page.set_sheet(
            self.base_attribute_sheet.with_modifiers(spirit_mark_inventory.attribute_modifiers())
        )
        self.on_spirit_marks_changed(spirit_mark_inventory)

    def set_data(
        self,
        inventory_snapshot: InventorySnapshot,
        spirit_mark_inventory: SpiritMarkInventory,
    ) -> None:
        self.attributes_page.set_sheet(
            self.base_attribute_sheet.with_modifiers(spirit_mark_inventory.attribute_modifiers())
        )
        self.equipment_page.set_data(inventory_snapshot, spirit_mark_inventory)


class PetAttributesPage(QWidget):
    def __init__(
        self,
        attribute_sheet: PetAttributeSheet,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.attribute_sheet = attribute_sheet
        self._summary_value_labels: dict[str, QLabel] = {}
        self._detail_base_labels: dict[str, QLabel] = {}
        self._detail_bonus_labels: dict[str, QLabel] = {}
        self._detail_help_icons: dict[str, IconWidget] = {}

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        self.preview_card = CardWidget(self)
        self.preview_card.setObjectName("petAttributePreviewCard")
        preview_layout = QVBoxLayout(self.preview_card)
        preview_layout.setContentsMargins(18, 18, 18, 18)
        preview_layout.setSpacing(12)
        preview_layout.addStretch(1)
        preview_label = TitleLabel("桌宠形象", self.preview_card)
        preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_layout.addWidget(preview_label)
        preview_hint = BodyLabel("预留展示区", self.preview_card)
        preview_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_layout.addWidget(preview_hint)
        preview_layout.addStretch(1)
        root.addWidget(self.preview_card, 1)

        self.attribute_stack = QStackedWidget(self)
        self.summary_page = self._create_summary_page()
        self.detail_page = self._create_detail_page()
        self.attribute_stack.addWidget(self.summary_page)
        self.attribute_stack.addWidget(self.detail_page)
        root.addWidget(self.attribute_stack, 1)

        self.set_sheet(attribute_sheet)

    def set_sheet(self, attribute_sheet: PetAttributeSheet) -> None:
        self.attribute_sheet = attribute_sheet
        self._clear_layout(self.summary_layout)
        self._clear_layout(self.detail_layout)
        self._summary_value_labels.clear()
        self._detail_base_labels.clear()
        self._detail_bonus_labels.clear()
        self._detail_help_icons.clear()
        for value in attribute_sheet.values:
            if value.definition.category == SUMMARY_ATTRIBUTE_CATEGORY:
                self.summary_layout.addWidget(self._summary_row(value.definition.id))
        for category, title in ATTRIBUTE_CATEGORY_TITLES.items():
            values = tuple(value for value in attribute_sheet.values if value.definition.category == category)
            if not values:
                continue
            self.detail_layout.addWidget(self._category_label(title, self.detail_content))
            for value in values:
                self.detail_layout.addWidget(self._detail_row(value.definition.id))
        self.summary_layout.addStretch(1)
        self.detail_layout.addStretch(1)
        self._refresh_values()

    def show_summary(self) -> None:
        self.attribute_stack.setCurrentWidget(self.summary_page)

    def show_details(self) -> None:
        self.attribute_stack.setCurrentWidget(self.detail_page)

    def _create_summary_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.addWidget(SubtitleLabel("属性", page))
        header.addStretch(1)
        self.summary_detail_button = PushButton("详细属性", page)
        self.summary_detail_button.clicked.connect(self.show_details)
        header.addWidget(self.summary_detail_button)
        layout.addLayout(header)

        self.summary_scroll = DraggableSmoothScrollArea(page)
        self.summary_scroll.setWidgetResizable(True)
        self.summary_content = QWidget(self.summary_scroll)
        self.summary_layout = QVBoxLayout(self.summary_content)
        self.summary_layout.setContentsMargins(0, 0, 8, 0)
        self.summary_layout.setSpacing(0)
        self.summary_scroll.setWidget(self.summary_content)
        self.summary_scroll.enableTransparentBackground()
        layout.addWidget(self.summary_scroll, 1)
        return page

    def _create_detail_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.addWidget(SubtitleLabel("详细属性", page))
        header.addStretch(1)
        self.detail_summary_button = PushButton("属性", page)
        self.detail_summary_button.clicked.connect(self.show_summary)
        header.addWidget(self.detail_summary_button)
        layout.addLayout(header)

        self.detail_scroll = DraggableSmoothScrollArea(page)
        self.detail_scroll.setWidgetResizable(True)
        self.detail_content = QWidget(self.detail_scroll)
        self.detail_layout = QVBoxLayout(self.detail_content)
        self.detail_layout.setContentsMargins(0, 0, 8, 0)
        self.detail_layout.setSpacing(0)
        self.detail_scroll.setWidget(self.detail_content)
        self.detail_scroll.enableTransparentBackground()
        layout.addWidget(self.detail_scroll, 1)
        return page

    def _category_label(self, title: str, parent: QWidget) -> QLabel:
        label = CaptionLabel(title, parent)
        label.setContentsMargins(14, 14, 14, 6)
        # Bold via QFont, NOT via stylesheet. qfluentwidgets' theme
        # switch calls `widget.setStyleSheet(...)` on registered labels
        # (see `addStyleSheet(register=True)` in
        # `qfluentwidgets.common.style_sheet`), which wipes any prior
        # `setStyleSheet("font-weight: ...")` call. QFont weight is
        # a widget property and survives the wipe. CaptionLabel's theme-
        # aware text color also stays intact because we don't touch it.
        font = label.font()
        font.setWeight(QFont.DemiBold)
        label.setFont(font)
        return label

    def _summary_row(self, attribute_id: str) -> QWidget:
        value = self.attribute_sheet.value_for(attribute_id)
        row = QWidget(self.summary_content)
        row.setObjectName(f"petAttributeSummaryRow_{attribute_id}")
        row.setMinimumHeight(42)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(14, 6, 14, 6)
        layout.setSpacing(12)
        layout.addWidget(self._attribute_icon(attribute_id, row))
        layout.addWidget(BodyLabel(value.definition.name, row))
        layout.addStretch(1)
        # BodyLabel adopts the active theme's text color, so light/dark
        # switching keeps the value readable.
        value_label = BodyLabel("", row)
        value_label.setObjectName(f"petAttributeValue_{attribute_id}")
        value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(value_label)
        self._summary_value_labels[attribute_id] = value_label
        return row

    def _detail_row(self, attribute_id: str) -> QWidget:
        value = self.attribute_sheet.value_for(attribute_id)
        row = QWidget(self.detail_content)
        row.setObjectName(f"petAttributeDetailRow_{attribute_id}")
        row.setMinimumHeight(46)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(14, 6, 14, 6)
        layout.setSpacing(12)

        layout.addWidget(self._attribute_icon(attribute_id, row))
        layout.addWidget(BodyLabel(value.definition.name, row))
        layout.addStretch(1)

        base_label = self._detail_number_label(row)
        bonus_label = self._detail_number_label(row, bonus=True)
        layout.addWidget(base_label)
        layout.addWidget(bonus_label)
        help_icon = IconWidget(FIF.QUESTION, row)
        help_icon.setFixedSize(18, 18)
        help_icon.setToolTip(f"{value.definition.role}\n{value.definition.mapped_content}")
        help_icon.installEventFilter(ToolTipFilter(help_icon, 300, ToolTipPosition.TOP))
        layout.addWidget(help_icon)

        self._detail_base_labels[attribute_id] = base_label
        self._detail_bonus_labels[attribute_id] = bonus_label
        self._detail_help_icons[attribute_id] = help_icon
        return row

    def _detail_number_label(self, parent: QWidget, *, bonus: bool = False) -> QLabel:
        # Base value uses the theme's text color via BodyLabel. Bonus
        # value uses qfluentwidgets' `setTextColor(light, dark)` instead
        # of `setStyleSheet("color: ...")` — the latter gets wiped on
        # theme switch (see `_category_label` for the same root cause).
        # The two greens are tuned separately: a bright pastel reads
        # well on a dark surface, but on a light surface the same hue
        # would wash out, so light theme gets a deeper variant.
        label = BodyLabel("", parent)
        label.setMinimumWidth(88)
        if bonus:
            label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            label.setTextColor(QColor("#2e7d32"), QColor("#7ddc5c"))
        else:
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return label

    def _attribute_icon(self, attribute_id: str, parent: QWidget) -> IconWidget:
        icon = IconWidget(ATTRIBUTE_ICONS.get(attribute_id, FIF.INFO), parent)
        icon.setFixedSize(20, 20)
        return icon

    def _refresh_values(self) -> None:
        for value in self.attribute_sheet.values:
            value_label = self._summary_value_labels.get(value.definition.id)
            if value_label is not None:
                value_label.setText(value.formatted_total())
            if (label := self._detail_base_labels.get(value.definition.id)) is not None:
                label.setText(value.formatted_base())
            if (label := self._detail_bonus_labels.get(value.definition.id)) is not None:
                has_bonus = value.total_bonus != 0
                label.setText(value.formatted_total_bonus() if has_bonus else "")

    def _clear_layout(self, layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()


class SpiritMarkEquipmentPage(QWidget):
    def __init__(
        self,
        inventory_snapshot: InventorySnapshot,
        spirit_mark_inventory: SpiritMarkInventory,
        on_spirit_marks_changed: Callable[[SpiritMarkInventory], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.inventory_snapshot = inventory_snapshot
        self.spirit_mark_inventory = spirit_mark_inventory
        self.on_spirit_marks_changed = on_spirit_marks_changed or (lambda _inventory: None)
        self.current_slot_id = next(iter(SPIRIT_MARK_SLOTS))
        self.selected_entry_id: str | None = None
        self._slot_cards: dict[str, SpiritMarkOverviewSlotCard] = {}
        self._candidate_cards: list[InventoryItemCard] = []
        self._entries_by_id = {entry.entry_id: entry for entry in inventory_snapshot.entries}
        self._category_by_id = {category.id: category for category in inventory_snapshot.categories}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.summary_label = BodyLabel("", self)
        self.summary_label.setWordWrap(True)
        self.detail_stack = QStackedWidget(self)
        self.overview_page = self._create_overview_page()
        self.slot_page = self._create_slot_page()
        self.detail_stack.addWidget(self.overview_page)
        self.detail_stack.addWidget(self.slot_page)
        root.addWidget(self.detail_stack, 1)

        self.refresh()

    def set_data(
        self,
        inventory_snapshot: InventorySnapshot,
        spirit_mark_inventory: SpiritMarkInventory,
    ) -> None:
        self.inventory_snapshot = inventory_snapshot
        self.spirit_mark_inventory = spirit_mark_inventory
        self._entries_by_id = {entry.entry_id: entry for entry in inventory_snapshot.entries}
        self._category_by_id = {category.id: category for category in inventory_snapshot.categories}
        if self.selected_entry_id not in self._entries_by_id:
            self.selected_entry_id = None
        self.refresh()

    def open_slot(self, slot_id: str) -> None:
        self.current_slot_id = slot_id
        self.slot_navigation.setCurrentItem(slot_id)
        equipped = self._equipped_by_slot().get(slot_id)
        self.selected_entry_id = equipped.entry_id if equipped is not None else None
        self.detail_stack.setCurrentWidget(self.slot_page)
        self.refresh()

    def show_overview(self) -> None:
        self.detail_stack.setCurrentWidget(self.overview_page)
        self.refresh()

    def equip_selected(self) -> None:
        mark = self._selected_mark()
        if mark is None:
            return
        self.spirit_mark_inventory = self.spirit_mark_inventory.equip(mark.entry_id)
        self.selected_entry_id = mark.entry_id
        self._commit_changes()

    def unequip_selected(self) -> None:
        mark = self._selected_mark()
        if mark is None:
            return
        self.spirit_mark_inventory = self.spirit_mark_inventory.unequip(mark.entry_id)
        self.selected_entry_id = mark.entry_id
        self._commit_changes()

    def refresh(self) -> None:
        self._refresh_overview()
        self._refresh_summary()
        self._refresh_slot_candidates()
        self._refresh_selected_detail()
        self._refresh_actions()

    def _commit_changes(self) -> None:
        self.on_spirit_marks_changed(self.spirit_mark_inventory)
        self.refresh()

    def _create_overview_page(self) -> QWidget:
        page = QWidget(self)
        root = QHBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        left = QGridLayout()
        left.setHorizontalSpacing(12)
        left.setVerticalSpacing(12)
        for index, slot in enumerate(SPIRIT_MARK_SLOTS.values()):
            card = SpiritMarkOverviewSlotCard(slot.id, self)
            card.slotClicked.connect(self.open_slot)
            self._slot_cards[slot.id] = card
            left.addWidget(card, index // 2, index % 2)
        root.addLayout(left, 2)

        right = QVBoxLayout()
        right.setSpacing(12)
        right.addWidget(self._summary_card())
        self.set_bonus_card = CardWidget(page)
        set_layout = QVBoxLayout(self.set_bonus_card)
        set_layout.setContentsMargins(18, 16, 18, 16)
        set_layout.setSpacing(8)
        set_layout.addWidget(SubtitleLabel("套装状态", self.set_bonus_card))
        self.set_bonus_label = BodyLabel("", self.set_bonus_card)
        self.set_bonus_label.setWordWrap(True)
        set_layout.addWidget(self.set_bonus_label)
        right.addWidget(self.set_bonus_card)
        right.addStretch(1)
        root.addLayout(right, 1)
        return page

    def _create_slot_page(self) -> QWidget:
        page = QWidget(self)
        root = QHBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        left = QVBoxLayout()
        left.setSpacing(12)
        header = QHBoxLayout()
        self.back_button = PushButton("返回", page)
        self.back_button.clicked.connect(self.show_overview)
        header.addWidget(self.back_button)
        self.slot_navigation = SegmentedWidget(page)
        self.slot_navigation.setObjectName("spiritMarkSlotNavigation")
        for slot in SPIRIT_MARK_SLOTS.values():
            self.slot_navigation.addItem(slot.id, slot.name)
        self.slot_navigation.currentItemChanged.connect(self._select_slot)
        header.addWidget(self.slot_navigation, 1)
        left.addLayout(header)

        self.candidate_scroll = DraggableSmoothScrollArea(page)
        self.candidate_scroll.setWidgetResizable(True)
        self.candidate_content = QWidget(self.candidate_scroll)
        self.candidate_grid = QGridLayout(self.candidate_content)
        self.candidate_grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.candidate_grid.setContentsMargins(0, 0, 8, 0)
        self.candidate_grid.setHorizontalSpacing(10)
        self.candidate_grid.setVerticalSpacing(10)
        self.empty_slot_label = BodyLabel("当前部位暂无可装备灵痕", self.candidate_content)
        self.empty_slot_label.hide()
        self.candidate_scroll.setWidget(self.candidate_content)
        self.candidate_scroll.enableTransparentBackground()
        left.addWidget(self.candidate_scroll, 1)
        root.addLayout(left, 2)

        right = QVBoxLayout()
        right.setSpacing(12)
        self.details_card = InventoryDetailsCard(page)
        right.addWidget(self.details_card, 1)
        self.action_button = PrimaryPushButton("装备", page)
        self.action_button.clicked.connect(self._run_primary_action)
        right.addWidget(self.action_button, alignment=Qt.AlignmentFlag.AlignRight)
        root.addLayout(right, 1)
        return page

    def _select_slot(self, slot_id: str) -> None:
        self.current_slot_id = slot_id
        equipped = self._equipped_by_slot().get(slot_id)
        self.selected_entry_id = equipped.entry_id if equipped is not None else None
        self.refresh()

    def _refresh_overview(self) -> None:
        equipped_by_slot = self._equipped_by_slot()
        for slot_id, card in self._slot_cards.items():
            mark = equipped_by_slot.get(slot_id)
            entry = self._entry_for_mark(mark)
            definition = None if entry is None else self.inventory_snapshot.definition_for(entry)
            card.show_mark(mark, definition)

    def _refresh_summary(self) -> None:
        totals = self.spirit_mark_inventory.formatted_stat_totals()
        if totals:
            total_text = "、".join(totals)
        else:
            total_text = "暂无装备加成"
        equipped_count = len(self.spirit_mark_inventory.equipped_marks())
        self.summary_label.setText(f"已装备 {equipped_count}/5。{total_text}")
        set_lines = []
        for set_id, count in sorted(self.spirit_mark_inventory.set_counts().items()):
            spirit_set = SPIRIT_MARK_SETS[set_id]
            if count >= 4:
                set_lines.append(f"{spirit_set.name} {count}件：{spirit_set.four_piece_description}")
            elif count >= 2:
                suffix = "%" if spirit_set.two_piece_bonus_type == "percent" else ""
                set_lines.append(f"{spirit_set.name} {count}件：{spirit_set.two_piece_stat} +{spirit_set.two_piece_value}{suffix}")
            else:
                set_lines.append(f"{spirit_set.name} {count}件")
        self.set_bonus_label.setText("\n".join(set_lines) if set_lines else "暂无套装效果")

    def _refresh_slot_candidates(self) -> None:
        self._clear_candidate_grid()
        marks = self._marks_for_current_slot()
        self._candidate_cards = []
        if not marks:
            self.empty_slot_label.show()
            self.candidate_grid.addWidget(self.empty_slot_label, 0, 0)
            self.selected_entry_id = None
            return
        self.empty_slot_label.hide()
        if self.selected_entry_id not in {mark.entry_id for mark in marks}:
            equipped = next((mark for mark in marks if mark.equipped), None)
            self.selected_entry_id = (equipped or marks[0]).entry_id
        for index, mark in enumerate(marks):
            entry = self._entry_for_mark(mark)
            if entry is None:
                continue
            definition = self.inventory_snapshot.definition_for(entry)
            card = InventoryItemCard(entry, definition, self.candidate_content, edge=96)
            card.entryClicked.connect(self.select_entry)
            card.set_selected(mark.entry_id == self.selected_entry_id)
            self._candidate_cards.append(card)
            self.candidate_grid.addWidget(card, index // 5, index % 5)

    def select_entry(self, entry_id: str) -> None:
        self.selected_entry_id = entry_id
        for card in self._candidate_cards:
            card.set_selected(card.entry.entry_id == entry_id)
        self._refresh_selected_detail()
        self._refresh_actions()

    def _refresh_selected_detail(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            self.details_card.clear()
        else:
            definition = self.inventory_snapshot.definition_for(entry)
            category = self._category_by_id[definition.category_id]
            self.details_card.show_entry(
                entry,
                definition,
                category,
                self.inventory_snapshot.details_for(entry),
            )

    def _refresh_actions(self) -> None:
        mark = self._selected_mark()
        if mark is None:
            self.action_button.setText("装备")
            self.action_button.setEnabled(False)
            return
        if mark.equipped:
            self.action_button.setText("卸下")
        elif self._equipped_by_slot().get(mark.slot_id) is None:
            self.action_button.setText("装备")
        else:
            self.action_button.setText("替换")
        self.action_button.setEnabled(True)

    def _run_primary_action(self) -> None:
        mark = self._selected_mark()
        if mark is None:
            return
        if mark.equipped:
            self.unequip_selected()
        else:
            self.equip_selected()

    def _summary_card(self) -> CardWidget:
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)
        layout.addWidget(SubtitleLabel("灵痕装备", card))
        layout.addWidget(self.summary_label)
        return card

    def _marks_for_current_slot(self) -> list[SpiritMark]:
        backpack_entry_ids = {entry.entry_id for entry in self.inventory_snapshot.entries_for_category(SPIRIT_MARK_CATEGORY_ID)}
        return [
            mark
            for mark in self.spirit_mark_inventory.marks
            if mark.slot_id == self.current_slot_id and mark.entry_id in backpack_entry_ids
        ]

    def _entry_for_mark(self, mark: SpiritMark | None):
        if mark is None:
            return None
        return self._entries_by_id.get(mark.entry_id)

    def _selected_mark(self) -> SpiritMark | None:
        if self.selected_entry_id is None:
            return None
        return self.spirit_mark_inventory.mark_by_entry_id(self.selected_entry_id)

    def _selected_entry(self):
        if self.selected_entry_id is None:
            return None
        return self._entries_by_id.get(self.selected_entry_id)

    def _equipped_by_slot(self) -> dict[str, SpiritMark]:
        return {mark.slot_id: mark for mark in self.spirit_mark_inventory.equipped_marks()}

    def _clear_candidate_grid(self) -> None:
        while self.candidate_grid.count():
            item = self.candidate_grid.takeAt(0)
            widget = item.widget()
            if widget is not None and widget is not self.empty_slot_label:
                widget.deleteLater()


class SpiritMarkOverviewSlotCard(CardWidget):
    slotClicked = Signal(str)

    def __init__(self, slot_id: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.slot_id = slot_id
        self.setObjectName(f"spiritMarkSlot_{slot_id}")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(96, 116)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.setStyleSheet("background: transparent; border: none;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        self.slot_label = CaptionLabel(SPIRIT_MARK_SLOTS[slot_id].name, self)
        self.slot_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.slot_label)
        self.image_label = QLabel(self)
        self.image_label.setMinimumSize(88, 88)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.image_label, 1)
        layout.addStretch(1)

    def show_mark(self, mark: SpiritMark | None, definition=None) -> None:
        if mark is None or definition is None:
            self.image_label.clear()
            return
        image_edge = max(88, min(128, self.image_label.width(), self.image_label.height()))
        self.image_label.setPixmap(_load_pixmap(definition.image, QSize(image_edge, image_edge)))

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self.slotClicked.emit(self.slot_id)


