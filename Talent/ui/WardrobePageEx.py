"""Digital Wardrobe page: grid, filters, inspector and the add/edit dialog."""

from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from libs.models import CATEGORY_LABELS, Context, Outfit, Garment
from libs.theme import COLORS
from libs.xai.scoring import load_config
from ui import media
from ui.GarmentDialogEx import GarmentDialogEx
from ui.Ui_WardrobePage import Ui_WardrobePage
from ui.widgets import (
    Badge,
    Chip,
    Divider,
    ElidedLabel,
    FlowLayout,
    GarmentCard,
    ask_wear_date,
    clear_layout,
    freshness_state,
)


class WardrobePageEx(QWidget, Ui_WardrobePage):
    garmentChanged = pyqtSignal()
    findOutfitsRequested = pyqtSignal(str)
    toastRequested = pyqtSignal(str, str)

    def __init__(self, repo, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.repo = repo
        self.config = load_config()
        self.current_id = ""
        self._cards: dict[str, GarmentCard] = {}
        self._category = ""
        self._season = ""

        self._flow = FlowLayout(self.gridHost, margin=0, spacing=14)
        self.gridHost.setLayout(self._flow)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(180)
        self._search_timer.timeout.connect(self.refresh)

        self._decorate()
        self._populate_filters()
        self._build_chips()
        self._connect()
        self.refresh()

    # ------------------------------------------------------------------ setup
    def _decorate(self) -> None:
        self.searchInput.addAction(
            media.icon("fa6s.magnifying-glass", COLORS["textFaint"], 14),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self.addButton.setIcon(media.icon("fa6s.plus", COLORS["white"], 16))
        self.inspectorClose.setIcon(media.icon("fa6s.xmark", COLORS["textFaint"], 14))
        self.seasonFilter.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sortFilter.setCursor(Qt.CursorShape.PointingHandCursor)
        self._show_empty_inspector()

    def _populate_filters(self) -> None:
        self.seasonFilter.addItem("All seasons", "")
        for season in ("Spring", "Summer", "Autumn", "Winter"):
            self.seasonFilter.addItem(season, season)
        for label, key in (
            ("Recently added", "recent"),
            ("Least worn", "least_worn"),
            ("Last worn", "last_worn"),
            ("Name A–Z", "name"),
        ):
            self.sortFilter.addItem(label, key)

    def _build_chips(self) -> None:
        self._chip_group = QButtonGroup(self)
        self._chip_group.setExclusive(True)
        all_items = self.repo.list_garments()
        counts = {"": len(all_items)}
        for garment in all_items:
            counts[garment.category] = counts.get(garment.category, 0) + 1

        options = [("All", "")] + [(CATEGORY_LABELS[c], c) for c in
                                   ("top", "bottom", "outer", "shoes")]
        for label, key in options:
            chip = Chip(label, counts.get(key, 0))
            chip.setProperty("chipKey", key)
            chip.setChecked(key == self._category)
            chip.clicked.connect(lambda _=False, k=key: self._set_category(k))
            self._chip_group.addButton(chip)
            self.chipLayout.addWidget(chip)

    def _connect(self) -> None:
        self.searchInput.textChanged.connect(lambda _: self._search_timer.start())
        self.addButton.clicked.connect(lambda: self._open_dialog(None))
        self.seasonFilter.currentIndexChanged.connect(self._on_season)
        self.sortFilter.currentIndexChanged.connect(lambda _: self.refresh())
        self.inspectorClose.clicked.connect(self._clear_selection)

    # ----------------------------------------------------------------- events
    def _set_category(self, key: str) -> None:
        self._category = key
        self.refresh()

    def _on_season(self, index: int) -> None:
        self._season = self.seasonFilter.itemData(index) or ""
        self.refresh()

    def refresh(self) -> None:
        garments = self.repo.list_garments(
            search=self.searchInput.text().strip(),
            category=self._category,
            sort=self.sortFilter.currentData() or "recent",
            season=self._season,
        )
        stats = self.repo.wear_stats()
        analytics = self.repo.analytics()
        sleeping_ids = {g.id for g in analytics["sleeping"]}

        self.pageSubtitle.setText(
            f"{analytics['total']} items · {len(sleeping_ids)} sleeping · "
            f"{analytics['utilization']:.0f}% utilized"
        )

        total_all = analytics["total"]
        self._update_chip_counts(total_all, garments)

        self._flow.clear()
        self._cards.clear()
        if not garments:
            self._flow.addWidget(self._empty_grid())
            self._show_empty_inspector()
            return

        for garment in garments:
            wear = stats.get(garment.id, {})
            card = GarmentCard(
                garment,
                wears=wear.get("count", 0),
                days_since=analytics["days_since"].get(garment.id),
                selected=garment.id == self.current_id,
            )
            card.clicked.connect(self.select_garment)
            card.editRequested.connect(lambda gid: self._open_dialog(self.repo.get_garment(gid)))
            card.deleteRequested.connect(self._delete_garment)
            card.logRequested.connect(self._log_single_wear)
            self._cards[garment.id] = card
            self._flow.addWidget(card)

        if self.current_id and self.current_id in self._cards:
            self.select_garment(self.current_id)
        elif self.current_id:
            self._clear_selection()

    def _update_chip_counts(self, total_all: int, garments) -> None:
        counts = {"": total_all}
        for garment in self.repo.list_garments():
            counts[garment.category] = counts.get(garment.category, 0) + 1
        for chip in self.chipLayout.parentWidget().findChildren(Chip):
            key = chip.property("chipKey") or ""
            label = "All" if key == "" else CATEGORY_LABELS.get(key, key)
            chip.setText(f"{label}  {counts.get(key, 0)}")

    def _empty_grid(self) -> QWidget:
        holder = QWidget()
        holder.setMinimumHeight(320)
        layout = QVBoxLayout(holder)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(10)
        icon = QLabel()
        icon.setPixmap(media.icon("fa6s.shirt", COLORS["textFaint"], 34).pixmap(34, 34))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel("Nothing matches those filters")
        title.setProperty("role", "h2")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint = QLabel("Try a different category, season or search term.")
        hint.setProperty("role", "muted")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        clear = QPushButton("Clear filters")
        clear.setProperty("variant", "ghost")
        clear.setCursor(Qt.CursorShape.PointingHandCursor)
        clear.clicked.connect(self._clear_filters)
        layout.addWidget(icon)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(clear, alignment=Qt.AlignmentFlag.AlignCenter)
        return holder

    def _clear_filters(self) -> None:
        self._category = ""
        self._season = ""
        self.searchInput.clear()
        self.seasonFilter.setCurrentIndex(0)
        for chip in self.chipLayout.parentWidget().findChildren(Chip):
            if (chip.property("chipKey") or "") == "":
                chip.setChecked(True)
        self.refresh()

    # -------------------------------------------------------------- inspector
    def select_garment(self, garment_id: str) -> None:
        self.current_id = garment_id
        for key, card in self._cards.items():
            card.set_selected(key == garment_id)
        garment = self.repo.get_garment(garment_id)
        if not garment:
            self._show_empty_inspector()
            return
        self._render_inspector(garment)

    def _clear_selection(self) -> None:
        self.current_id = ""
        for card in self._cards.values():
            card.set_selected(False)
        self._show_empty_inspector()

    def _reset_inspector(self) -> QVBoxLayout:
        body = self.inspectorBody
        if body.layout() is None:
            layout = QVBoxLayout(body)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(12)
        else:
            clear_layout(body.layout())
            layout = body.layout()
        return layout

    def _show_empty_inspector(self) -> None:
        layout = self._reset_inspector()
        layout.addStretch(1)
        icon = QLabel()
        icon.setPixmap(media.icon("fa6s.hand-pointer", COLORS["textFaint"], 28).pixmap(28, 28))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel("Inspect a garment")
        title.setProperty("role", "h2")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint = QLabel("Pick a card to see its attributes, wear history "
                      "and what the recommender does with it.")
        hint.setProperty("role", "muted")
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addStretch(1)

    def _render_inspector(self, garment: Garment) -> None:
        layout = self._reset_inspector()
        stats = self.repo.wear_stats().get(garment.id, {})
        analytics = self.repo.analytics()
        days_since = analytics["days_since"].get(garment.id)

        picture = QLabel()
        picture.setPixmap(media.garment_pixmap(garment, 312, 168))
        picture.setFixedHeight(168)
        picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        picture.setObjectName("inspectorImage")
        layout.addWidget(picture)

        head = QVBoxLayout()
        head.setSpacing(3)
        name = QLabel(garment.name)
        name.setProperty("role", "h2")
        name.setWordWrap(True)
        head.addWidget(name)
        meta = QLabel(f"{garment.id} · {CATEGORY_LABELS.get(garment.category, '')} · "
                      f"{garment.color_name}")
        meta.setProperty("role", "muted")
        head.addWidget(meta)
        layout.addLayout(head)

        chip_row = QHBoxLayout()
        chip_row.setSpacing(6)
        chip_row.addWidget(Badge("AI extracted", "neutral"))
        chip_row.addWidget(Badge("98.4% confidence", "success"))
        chip_row.addStretch(1)
        layout.addLayout(chip_row)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        pairs = [
            ("Category", CATEGORY_LABELS.get(garment.category, garment.category)),
            ("Colour", garment.color_name),
            ("Pattern", garment.pattern),
            ("Material", garment.material),
            ("Season", ", ".join(garment.seasons) or "All"),
            ("Occasion", ", ".join(garment.occasions) or "Any"),
        ]
        for index, (label, value) in enumerate(pairs):
            cell = QVBoxLayout()
            cell.setSpacing(1)
            key = QLabel(label.upper())
            key.setProperty("role", "label")
            val = QLabel(value)
            val.setObjectName("attrValue")
            val.setWordWrap(True)
            cell.addWidget(key)
            cell.addWidget(val)
            grid.addLayout(cell, index // 2, index % 2)
        layout.addLayout(grid)

        layout.addWidget(Divider())

        header = QLabel("WEAR HISTORY")
        header.setProperty("role", "label")
        layout.addWidget(header)

        wear_row = QHBoxLayout()
        wear_row.setSpacing(14)
        count = QLabel(str(stats.get("count", 0)))
        count.setObjectName("wearCount")
        wear_row.addWidget(count)
        text = QVBoxLayout()
        text.setSpacing(1)
        total = QLabel("total wears")
        total.setProperty("role", "muted")
        last = QLabel(
            "never worn yet" if days_since is None else f"last worn {days_since} days ago"
        )
        last.setObjectName("attrValue")
        text.addWidget(total)
        text.addWidget(last)
        wear_row.addLayout(text)
        wear_row.addStretch(1)
        wear_row.addWidget(Badge(*freshness_state(days_since)))
        layout.addLayout(wear_row)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        edit = QPushButton("Edit")
        edit.setProperty("variant", "ghost")
        edit.setCursor(Qt.CursorShape.PointingHandCursor)
        edit.clicked.connect(lambda: self._open_dialog(garment))
        wear = QPushButton("Log wear")
        wear.setProperty("variant", "primary")
        wear.setCursor(Qt.CursorShape.PointingHandCursor)
        wear.clicked.connect(lambda: self._log_single_wear(garment.id))
        buttons.addWidget(edit)
        buttons.addWidget(wear)
        layout.addLayout(buttons)

        find = QPushButton("Find outfits with this piece")
        find.setProperty("variant", "quiet")
        find.setCursor(Qt.CursorShape.PointingHandCursor)
        find.setIcon(media.icon("fa6s.wand-magic-sparkles", COLORS["textMuted"], 16))
        find.clicked.connect(lambda: self.findOutfitsRequested.emit(garment.id))
        layout.addWidget(find)

        layout.addStretch(1)

    # ----------------------------------------------------------------- dialog
    def _open_dialog(self, garment: Garment | None) -> None:
        dialog = GarmentDialogEx(self.repo, garment, self)
        if dialog.exec():
            saved = dialog.result_garment()
            if saved:
                self.repo.upsert_garment(saved)
                self.current_id = saved.id
                self.refresh()
                self.select_garment(saved.id)
                self.garmentChanged.emit()
                self.toastRequested.emit(
                    f"{'Updated' if garment else 'Added'} {saved.name}", "success"
                )

    def _delete_garment(self, garment_id: str) -> None:
        garment = self.repo.get_garment(garment_id)
        if not garment:
            return
        answer = QMessageBox.question(
            self,
            "Delete garment",
            f"Remove “{garment.name}” from the wardrobe?\n"
            "Past wear entries stay in the history.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.repo.delete_garment(garment_id)
        if self.current_id == garment_id:
            self.current_id = ""
        self.refresh()
        self.garmentChanged.emit()
        self.toastRequested.emit(f"Deleted {garment.name}", "danger")

    def _log_single_wear(self, garment_id: str) -> None:
        garment = self.repo.get_garment(garment_id)
        if not garment:
            return
        worn_on = ask_wear_date(self, f"Log wear — {garment.name}")
        if worn_on is None:
            return
        outfit = Outfit(id="", name=garment.name, source="manual")
        outfit.items[garment.category] = garment
        self.repo.log_wear(outfit, worn_on=worn_on, feedback=None, note="logged from wardrobe")
        self.refresh()
        self.garmentChanged.emit()
        self.toastRequested.emit(f"Logged a wear for {garment.name} on {worn_on.isoformat()}", "success")
