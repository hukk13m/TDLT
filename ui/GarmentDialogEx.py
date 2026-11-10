"""Add / edit garment dialog.

The "auto-fill" button is a keyword extractor, not a black box: it reads the
name and fills the attributes a real tagging model would predict, then says so
in the subtitle so nobody mistakes it for magic.
"""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import QColorDialog, QDialog, QFileDialog, QMessageBox

from libs.models import CATEGORY_LABELS, Garment
from libs.palette import family_for_hex
from libs.seed_data import OCCASIONS
from libs.theme import COLORS
from ui import media
from ui.Ui_GarmentDialog import Ui_GarmentDialog
from ui.widgets import Chip

PATTERNS = ["Solid", "Striped", "Checked", "Textured", "Printed"]
ALL_SEASONS = ["Spring", "Summer", "Autumn", "Winter"]

# name keyword -> attribute hints used by the auto-fill button
KEYWORDS: list[tuple[tuple[str, ...], dict]] = [
    (("t-shirt", "tee"), dict(subtype="tee", material="Cotton Jersey", breathability=8,
                              warmth=2, seasons=["Summer"],
                              occasions=["Casual", "Sport"])),
    (("hoodie", "sweatshirt"), dict(subtype="hoodie", material="Cotton Fleece",
                                    breathability=5, warmth=6,
                                    seasons=["Autumn", "Winter"],
                                    occasions=["Casual", "Sport"])),
    (("cardigan", "knit", "sweater", "jumper"), dict(subtype="knit", material="Merino Wool",
                                                     breathability=5, warmth=8,
                                                     seasons=["Autumn", "Winter"],
                                                     occasions=["Casual", "Smart Casual"])),
    (("blouse",), dict(subtype="blouse", material="Silk", breathability=7, warmth=2,
                       seasons=["Spring", "Summer"],
                       occasions=["Formal", "Smart Casual"])),
    (("polo",), dict(subtype="polo", material="Cotton Piqué", breathability=7, warmth=3,
                     seasons=["Spring", "Summer"], occasions=["Casual", "University"])),
    (("oxford shirt", "poplin", "dress shirt", "shirt"), dict(
        subtype="shirt", material="Cotton Poplin", breathability=7, warmth=3,
        seasons=ALL_SEASONS, occasions=["Formal", "University", "Smart Casual"])),
    (("chino short", "shorts"), dict(subtype="shorts", material="Cotton Twill",
                                     breathability=9, warmth=1, seasons=["Summer"],
                                     occasions=["Casual", "Sport"])),
    (("jean", "denim"), dict(subtype="jeans", material="Denim", breathability=6, warmth=4,
                             seasons=ALL_SEASONS,
                             occasions=["Casual", "University"])),
    (("chino", "trouser", "pant"), dict(subtype="trousers", material="Cotton Stretch",
                                        breathability=7, warmth=4, seasons=ALL_SEASONS,
                                        occasions=["University", "Smart Casual"])),
    (("trench", "coat"), dict(subtype="coat", material="Cotton Gabardine",
                              breathability=4, warmth=6,
                              seasons=["Spring", "Autumn"],
                              occasions=["Smart Casual", "University"])),
    (("blazer",), dict(subtype="blazer", material="Wool", breathability=4, warmth=7,
                       seasons=ALL_SEASONS,
                       occasions=["Formal", "Smart Casual"])),
    (("jacket",), dict(subtype="jacket", material="Cotton Canvas", breathability=5,
                       warmth=6, seasons=["Autumn"], occasions=["Casual"])),
    (("boot",), dict(subtype="boot", material="Leather", breathability=5, warmth=5,
                     seasons=["Autumn", "Winter"],
                     occasions=["Smart Casual", "Casual"])),
    (("loafer",), dict(subtype="loafer", material="Suede", breathability=6, warmth=3,
                       seasons=["Spring", "Summer"],
                       occasions=["Smart Casual", "Formal"])),
    (("oxford shoe", "derby", "dress shoe"), dict(subtype="oxford", material="Calf Leather",
                                                 breathability=5, warmth=4,
                                                 seasons=ALL_SEASONS,
                                                 occasions=["Formal", "Smart Casual"])),
    (("sneaker", "trainer", "runner"), dict(subtype="sneaker", material="Leather",
                                            breathability=7, warmth=3,
                                            seasons=ALL_SEASONS,
                                            occasions=["Casual", "University"])),
]

COLOUR_WORDS: list[tuple[str, str, str]] = [
    ("white", "Neutral White", "#FAFAF9"),
    ("black", "Jet Black", "#141518"),
    ("navy", "Deep Navy", "#1F3A5F"),
    ("indigo", "Raw Indigo", "#2C3A5A"),
    ("grey", "Mid Grey", "#70757D"),
    ("gray", "Mid Grey", "#70757D"),
    ("charcoal", "Charcoal", "#3A3F47"),
    ("beige", "Warm Beige", "#D9C9A8"),
    ("cream", "Warm Cream", "#F3EBDD"),
    ("sand", "Sand", "#CFBB96"),
    ("camel", "Camel", "#B58F63"),
    ("tan", "Tan Suede", "#A98457"),
    ("olive", "Field Olive", "#4F5A3C"),
    ("sage", "Sage Green", "#9AAF93"),
    ("green", "Olive", "#4C5740"),
    ("rust", "Rust", "#A65A32"),
    ("brown", "Chestnut", "#7A5236"),
    ("blue", "Cobalt Blue", "#2A4B7C"),
    ("red", "Brick Red", "#A33B36"),
    ("pink", "Dusty Pink", "#D8A7A7"),
]


class GarmentDialogEx(QDialog, Ui_GarmentDialog):
    def __init__(self, repo, garment: Garment | None = None, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.repo = repo
        self.garment = garment
        self._color_hex = garment.color_hex if garment else "#FAFAF9"
        self._image_path = garment.image_path if garment else ""
        self._saved: Garment | None = None
        self._season_chips: dict[str, Chip] = {}
        self._occasion_chips: dict[str, Chip] = {}

        self.setWindowTitle("Edit garment" if garment else "Add garment")
        self.dialogTitle.setText("Edit garment" if garment else "Add garment")
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

        self._populate_combos()
        self._build_chips()
        self._connect()
        self._preview_colour()
        self._preview_image()
        if garment:
            self._fill(garment)
        self.nameInput.setFocus()

    # ------------------------------------------------------------------ setup
    def _populate_combos(self) -> None:
        for key in ("top", "bottom", "outer", "shoes"):
            self.categoryInput.addItem(CATEGORY_LABELS[key], key)
        for pattern in PATTERNS:
            self.patternInput.addItem(pattern, pattern)

    def _build_chips(self) -> None:
        for season in ALL_SEASONS:
            chip = Chip(season)
            chip.setMinimumHeight(32)
            self._season_chips[season] = chip
            self.seasonsLayout.addWidget(chip)
        self.seasonsLayout.addStretch(1)
        for occasion in OCCASIONS:
            chip = Chip(occasion)
            chip.setMinimumHeight(32)
            self._occasion_chips[occasion] = chip
            self.occasionsLayout.addWidget(chip)
        self.occasionsLayout.addStretch(1)

    def _connect(self) -> None:
        self.cancelButton.clicked.connect(self.reject)
        self.saveButton.clicked.connect(self._save)
        self.autoFillButton.setIcon(media.icon("fa6s.wand-magic-sparkles",
                                               COLORS["textMuted"], 16))
        self.autoFillButton.clicked.connect(self._auto_fill)
        self.chooseImageButton.clicked.connect(self._choose_image)
        self.colourSwatch.clicked.connect(self._pick_colour)
        self.breathSlider.valueChanged.connect(
            lambda v: self.breathValue.setText(f"{v} / 10"))
        self.warmthSlider.valueChanged.connect(
            lambda v: self.warmthValue.setText(f"{v} / 10"))
        self.nameInput.textChanged.connect(self._preview_colour)

    def _fill(self, garment: Garment) -> None:
        self.nameInput.setText(garment.name)
        index = self.categoryInput.findData(garment.category)
        if index >= 0:
            self.categoryInput.setCurrentIndex(index)
        self.colourNameInput.setText(garment.color_name)
        self.materialInput.setText(garment.material)
        pattern_index = self.patternInput.findData(garment.pattern)
        if pattern_index >= 0:
            self.patternInput.setCurrentIndex(pattern_index)
        self.breathSlider.setValue(garment.breathability)
        self.warmthSlider.setValue(garment.warmth)
        for season, chip in self._season_chips.items():
            chip.setChecked(season in garment.seasons)
        for occasion, chip in self._occasion_chips.items():
            chip.setChecked(occasion in garment.occasions)

    # -------------------------------------------------------------- colour
    def _pick_colour(self) -> None:
        colour = QColorDialog.getColor(QColor(self._color_hex), self, "Garment colour")
        if colour.isValid():
            self._color_hex = colour.name().upper()
            self._preview_colour()

    def _preview_colour(self) -> None:
        self.colourSwatch.setStyleSheet(
            f"background: {self._color_hex};"
            f" border: 2px solid {COLORS['textMuted']};"
            " border-radius: 8px;"
        )
        self._preview_image()

    def _preview_image(self) -> None:
        preview = Garment(
            id=self.garment.id if self.garment else "PREVIEW",
            name=self.nameInput.text() or "New garment",
            category=self.categoryInput.currentData() or "top",
            subtype=self._guess_subtype(),
            color_name=self.colourNameInput.text(),
            color_hex=self._color_hex,
            color_family=family_for_hex(self._color_hex),
            pattern=self.patternInput.currentData() or "Solid",
            material=self.materialInput.text(),
            breathability=self.breathSlider.value(),
            warmth=self.warmthSlider.value(),
            seasons=[],
            occasions=[],
            image_path=self._image_path,
        )
        self.imagePreview.setPixmap(media.garment_pixmap(preview, 176, 220))

    def _choose_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose garment photo", "", "Images (*.png *.jpg *.jpeg *.webp)"
        )
        if not path:
            return
        media.GARMENT_DIR.mkdir(parents=True, exist_ok=True)
        garment_id = self.garment.id if self.garment else self.repo.next_garment_id()
        suffix = Path(path).suffix.lower() or ".jpg"
        target = media.GARMENT_DIR / f"{garment_id}{suffix}"
        try:
            shutil.copyfile(path, target)
        except OSError as error:
            QMessageBox.warning(self, "Could not copy image", str(error))
            return
        self._image_path = str(target)
        media.clear_cache()
        self._preview_image()

    # ------------------------------------------------------------- auto fill
    def _guess_subtype(self) -> str:
        name = self.nameInput.text().lower()
        for words, hints in KEYWORDS:
            if any(word in name for word in words):
                return hints.get("subtype", "shirt")
        return {
            "top": "shirt", "bottom": "trousers", "outer": "coat", "shoes": "sneaker",
        }.get(self.categoryInput.currentData() or "top", "shirt")

    def _auto_fill(self) -> None:
        name = self.nameInput.text().strip().lower()
        if not name:
            QMessageBox.information(
                self, "Name needed",
                "Type a garment name first - the extractor reads the name."
            )
            return

        filled = 0
        for words, hints in KEYWORDS:
            if not any(word in name for word in words):
                continue
            category = hints.get("subtype")
            mapping = {
                "shirt": "top", "polo": "top", "blouse": "top", "tee": "top",
                "knit": "top", "hoodie": "top", "trousers": "bottom", "jeans": "bottom",
                "shorts": "bottom", "coat": "outer", "blazer": "outer", "jacket": "outer",
                "sneaker": "shoes", "boot": "shoes", "loafer": "shoes", "oxford": "shoes",
            }
            if category in mapping:
                index = self.categoryInput.findData(mapping[category])
                if index >= 0:
                    self.categoryInput.setCurrentIndex(index)
                filled += 1
            if hints.get("material"):
                self.materialInput.setText(hints["material"])
                filled += 1
            if hints.get("breathability"):
                self.breathSlider.setValue(hints["breathability"])
                filled += 1
            if hints.get("warmth"):
                self.warmthSlider.setValue(hints["warmth"])
                filled += 1
            for season in hints.get("seasons", []):
                if season in self._season_chips:
                    self._season_chips[season].setChecked(True)
            for occasion in hints.get("occasions", []):
                if occasion in self._occasion_chips:
                    self._occasion_chips[occasion].setChecked(True)
            break

        for word, colour_name, hex_value in COLOUR_WORDS:
            if word in name:
                self.colourNameInput.setText(colour_name)
                self._color_hex = hex_value
                filled += 1
                break

        if not self.patternInput.currentData():
            self.patternInput.setCurrentIndex(0)
        if not self.materialInput.text():
            self.materialInput.setText("Cotton Blend")
        if filled:
            self._preview_colour()
            self.dialogSubtitle.setText(
                f"Auto-filled {filled} attributes from the name - review before saving"
            )
        else:
            self.dialogSubtitle.setText(
                "No matching attribute pattern - please fill the fields manually"
            )

    # ----------------------------------------------------------------- save
    def _save(self) -> None:
        name = self.nameInput.text().strip()
        if not name:
            QMessageBox.warning(self, "Name required", "Give the garment a name first.")
            self.nameInput.setFocus()
            return

        seasons = [s for s, chip in self._season_chips.items() if chip.isChecked()]
        occasions = [o for o, chip in self._occasion_chips.items() if chip.isChecked()]
        if not seasons:
            seasons = ["Spring", "Summer", "Autumn", "Winter"]
        if not occasions:
            occasions = ["Casual"]

        self._saved = Garment(
            id=self.garment.id if self.garment else self.repo.next_garment_id(),
            name=name,
            category=self.categoryInput.currentData() or "top",
            subtype=self._guess_subtype(),
            color_name=self.colourNameInput.text().strip() or "Unnamed colour",
            color_hex=self._color_hex,
            color_family=family_for_hex(self._color_hex),
            pattern=self.patternInput.currentData() or "Solid",
            material=self.materialInput.text().strip() or "Cotton Blend",
            breathability=self.breathSlider.value(),
            warmth=self.warmthSlider.value(),
            seasons=seasons,
            occasions=occasions,
            image_path=self._image_path,
            created_at=self.garment.created_at if self.garment else date.today().isoformat(),
        )
        self.accept()

    def result_garment(self) -> Garment | None:
        return self._saved
