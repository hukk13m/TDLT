"""AI Stylist page: recommendations, the XAI panel and the What-If simulator."""

from __future__ import annotations

from dataclasses import replace

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from libs import recommender
from libs.models import Context, Outfit
from libs.seed_data import OCCASIONS, STYLE_GOALS
from libs.theme import COLORS
from libs.xai.rationale import build_rationale, build_repeat_warning
from libs.xai.scoring import Evaluation, evaluate, item_days_since, load_config
from ui import media
from ui.Ui_StylistPage import Ui_StylistPage
from ui.widgets import (
    Badge,
    ContributionRow,
    Divider,
    ElidedLabel,
    OutfitListItem,
    SectionCard,
    SlotTile,
    ask_wear_date,
    clear_layout,
)


def _slot_order(outfit: Outfit) -> list[str]:
    return [slot for slot in ("top", "outer", "bottom", "shoes") if slot in outfit.items]


class StylistPageEx(QWidget, Ui_StylistPage):
    wearLogged = pyqtSignal()
    toastRequested = pyqtSignal(str, str)

    def __init__(self, repo, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.repo = repo
        self.config = load_config()
        self.context, coords = repo.load_context()
        self._lat, self._lon = coords
        self.weather: dict = {}
        self.picks: list[tuple[Outfit, Evaluation]] = []
        self.index = 0
        self.base_evaluation: Evaluation | None = None
        self._rows: list[ContributionRow] = []
        self._delta_label: QLabel | None = None
        self._what_if_outfit: Outfit | None = None
        self.locks: dict[str, str] = {}
        self._slot_combos: dict[str, QComboBox] = {}
        self._last_pool_counts: dict = {}

        self._decorate()
        self._build_slot_selector()
        self._connect()
        self._build_history_filter()
        self.regenerate()
        self._build_saved()
        self._build_history()

    # ------------------------------------------------------------------ setup
    def _decorate(self) -> None:
        for occasion in OCCASIONS:
            self.occasionFilter.addItem(occasion)
        for goal in STYLE_GOALS:
            self.styleGoalFilter.addItem(goal)
        self.occasionFilter.setCurrentText(self.context.occasion)
        self.styleGoalFilter.setCurrentText(self.context.style_goal)
        self.strictToggle.setChecked(self.context.strict_anti_rep)
        self.antiRepDays.setValue(self.context.anti_rep_days)

        self.generateButton.setIcon(
            media.icon("fa6s.wand-magic-sparkles", COLORS["white"], 16)
        )
        self.weatherIcon.setPixmap(
            media.icon("fa6s.cloud-sun", COLORS["amberDeep"], 26).pixmap(26, 26)
        )

    def _build_slot_selector(self) -> None:
        """General per-slot controls: pick/lock any component or set outer mode."""
        bar = QFrame(self)
        bar.setObjectName("slotSelectorBar")
        bar.setProperty("card", False)
        layout = QVBoxLayout(bar)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(8)
        title = QLabel("Components")
        title.setProperty("role", "label")
        head.addWidget(title)
        head.addStretch(1)
        reset = QPushButton("Reset")
        reset.setProperty("variant", "quiet")
        reset.setCursor(Qt.CursorShape.PointingHandCursor)
        reset.clicked.connect(self._reset_slot_selection)
        head.addWidget(reset)
        layout.addLayout(head)

        row = QHBoxLayout()
        row.setSpacing(12)
        slot_defs = [
            ("top", "Top"),
            ("bottom", "Bottom"),
            ("shoes", "Footwear"),
            ("outer", "Outerwear"),
        ]
        for slot, label_text in slot_defs:
            block = QVBoxLayout()
            block.setSpacing(4)
            label = QLabel(label_text)
            label.setProperty("role", "label")
            block.addWidget(label)
            combo = QComboBox()
            combo.setMinimumHeight(36)
            combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            combo.setProperty("slot", slot)
            combo.currentIndexChanged.connect(lambda _i, s=slot: self._on_slot_changed(s))
            self._slot_combos[slot] = combo
            block.addWidget(combo)
            row.addLayout(block, 1)
        layout.addLayout(row)

        # Insert between context bar (index 1) and tabs (index 2).
        self.rootLayout.insertWidget(2, bar)
        self._populate_slot_combos()

    def _populate_slot_combos(self) -> None:
        garments = self.repo.list_garments()
        by_cat = {"top": [], "bottom": [], "shoes": [], "outer": []}
        for g in garments:
            if g.category in by_cat:
                by_cat[g.category].append(g)
        for slot, items in by_cat.items():
            combo = self._slot_combos.get(slot)
            if combo is None:
                continue
            combo.blockSignals(True)
            combo.clear()
            if slot == "outer":
                combo.addItem("Auto (by weather)", ("mode", "auto"))
                combo.addItem("Always include (any)", ("mode", "include"))
                combo.addItem("No outerwear", ("mode", "exclude"))
            else:
                combo.addItem("Any", ("any", ""))
            combo.insertSeparator(combo.count())
            for g in sorted(items, key=lambda x: (x.name, x.id)):
                combo.addItem(f"{g.name}  ({g.id})", ("item", g.id))
            # Restore selection
            self._set_slot_combo_value(slot)
            combo.blockSignals(False)

    def _set_slot_combo_value(self, slot: str) -> None:
        combo = self._slot_combos.get(slot)
        if combo is None:
            return
        if slot == "outer":
            # locked specific outer takes precedence over mode
            if slot in self.locks:
                target = ("item", self.locks[slot])
            else:
                target = ("mode", getattr(self.context, "outer_mode", "auto"))
        else:
            target = ("item", self.locks[slot]) if slot in self.locks else ("any", "")
        for i in range(combo.count()):
            if combo.itemData(i) == target:
                combo.setCurrentIndex(i)
                return
        combo.setCurrentIndex(0)

    def _on_slot_changed(self, slot: str) -> None:
        combo = self._slot_combos.get(slot)
        if combo is None:
            return
        data = combo.itemData(combo.currentIndex())
        if not data:
            return
        kind, value = data
        if slot == "outer":
            if kind == "item":
                self.locks["outer"] = value
                # force include when a specific outer is chosen
                self.context.outer_mode = "include"
            elif kind == "mode":
                self.locks.pop("outer", None)
                self.context.outer_mode = value
            self.repo.save_context(self.context)
        else:
            if kind == "item":
                self.locks[slot] = value
            else:
                self.locks.pop(slot, None)
        self._update_slot_summary()
        self.regenerate()

    def _reset_slot_selection(self) -> None:
        self.locks = {}
        self.context.outer_mode = "auto"
        self.repo.save_context(self.context)
        self._populate_slot_combos()
        self._update_slot_summary()
        self.regenerate()

    def _update_slot_summary(self) -> None:
        # Kept intentionally minimal to avoid clutter in the selector bar.
        return

    def _connect(self) -> None:
        self.generateButton.clicked.connect(self.regenerate)
        self.occasionFilter.currentTextChanged.connect(self._on_occasion)
        self.styleGoalFilter.currentTextChanged.connect(self._on_goal)
        self.strictToggle.toggled.connect(self._on_strict)
        self.antiRepDays.valueChanged.connect(self._on_days)
        self.tabs.currentChanged.connect(self._on_tab)

    # ----------------------------------------------------------------- inputs
    def _on_occasion(self, value: str) -> None:
        self.context.occasion = value
        self.repo.save_context(self.context)
        self.regenerate()

    def _on_goal(self, value: str) -> None:
        self.context.style_goal = value
        self.repo.save_context(self.context)

    def _on_strict(self, checked: bool) -> None:
        self.context.strict_anti_rep = checked
        self.repo.save_context(self.context)
        self.regenerate()

    def _on_days(self, value: int) -> None:
        self.context.anti_rep_days = value
        self.repo.save_context(self.context)
        self.regenerate()

    def _on_tab(self, index: int) -> None:
        if index == 1:
            self._build_saved()
        elif index == 2:
            self._build_history()

    def refresh(self) -> None:
        """Called when wardrobe/context data changes elsewhere."""
        # Refresh slot options (items may have been added/removed/renamed).
        if self._slot_combos:
            self._populate_slot_combos()
        self.regenerate()
        self._build_saved()
        self._build_history()

    def set_weather(self, weather: dict) -> None:
        self.weather = weather
        temperature = weather.get("temperature", self.context.temperature)
        condition = weather.get("condition", self.context.condition)
        source = weather.get("source", "live")
        self.context.temperature = temperature
        self.context.condition = condition
        self.context.is_rain = bool(weather.get("is_rain", False))

        self.weatherTemp.setText(f"{temperature:.0f}°C")
        suffix = {"live": "live", "cached": "cached", "offline": "offline estimate"}.get(
            source, source
        )
        self.weatherMeta.setText(f"{condition} · {self.context.city} · {suffix}")
        icon_name = "fa6s.cloud-rain" if self.context.is_rain else "fa6s.sun"
        color = COLORS["textMuted"] if self.context.is_rain else COLORS["amberDeep"]
        self.weatherIcon.setPixmap(media.icon(icon_name, color, 26).pixmap(26, 26))
        self.regenerate()

    # ------------------------------------------------------------- generation
    def regenerate(self) -> None:
        garments = self.repo.list_garments()
        stats = self.repo.wear_stats()

        # Validate locks against current wardrobe.
        valid_ids = {g.id for g in garments}
        dropped = [s for s, gid in self.locks.items() if gid not in valid_ids]
        for slot in dropped:
            self.locks.pop(slot, None)

        # Candidate counts for transparency.
        candidates = recommender.build_candidates(garments, self.context, self.locks)
        after = candidates
        if self.context.strict_anti_rep and candidates:
            fresh = [o for o in candidates if not recommender.is_recent_repeat(o, stats, self.context)]
            if fresh:
                after = fresh
        self._last_pool_counts = {
            "candidates": len(candidates),
            "after_filter": len(after),
        }

        self.picks = recommender.recommend(
            garments, self.context, stats, self.config, top_n=6, locks=self.locks
        )
        self.index = 0
        self._render_suggestions()
        self._update_slot_summary()

    def _render_suggestions(self) -> None:
        layout = self.suggestHostLayout
        clear_layout(layout)
        if not self.picks:
            layout.addWidget(self._empty_state(
                "fa6s-shirt", "No outfit fits these filters",
                "Relax the anti-repetition window or add more pieces to the wardrobe.",
            ))
            clear_layout(self.xaiHostLayout)
            return

        outfit, evaluation = self.picks[self.index]
        layout.addWidget(self._suggestion_card(outfit, evaluation))

        others = [pair for position, pair in enumerate(self.picks) if position != self.index]
        if others:
            header = QLabel("Other strong options")
            header.setProperty("role", "label")
            layout.addWidget(header)
        for outfit_option, evaluation_option in others[:3]:
            note = self._rank_note(outfit_option, evaluation_option)
            row = OutfitListItem(
                outfit_option, evaluation_option.score, note,
                actions=(("use", "Use this", "ghost"),),
            )
            row.clicked.connect(lambda _id, pair=(outfit_option, evaluation_option):
                                self._use_pair(pair))
            row.actionTriggered.connect(lambda _key, _id, pair=(outfit_option, evaluation_option):
                                        self._use_pair(pair))
            layout.addWidget(row)
        layout.addStretch(1)

        self._render_xai(outfit, evaluation)

    def _rank_note(self, outfit: Outfit, evaluation: Evaluation) -> str:
        gaps = [item_days_since(g, self.context, self.repo.wear_stats()) for g in outfit.ordered_items()]
        gaps = [g for g in gaps if g is not None]
        fresh = f"rested {min(gaps)}d" if gaps else "never worn"
        return f"{evaluation.score:.0f}/100 · {self.context.weather_summary} · {fresh}"

    def _use_pair(self, pair: tuple[Outfit, Evaluation]) -> None:
        outfit, evaluation = pair
        if pair in self.picks:
            self.index = self.picks.index(pair)
        else:
            self.picks.insert(0, pair)
            self.index = 0
        self._render_suggestions()

    def _suggestion_card(self, outfit: Outfit, evaluation: Evaluation) -> QWidget:
        card = SectionCard()
        layout = card.body()

        header = QHBoxLayout()
        header.setSpacing(8)
        header.addWidget(Badge(f"Rank #{self.index + 1}", "neutral"))
        score = QLabel(
            f"<span style='font-size:23px;font-weight:700'>{evaluation.score:.1f}</span>"
            f"<span style='color:{COLORS['textMuted']};font-size:12px'> / 100</span>"
        )
        score.setObjectName("scorePill")
        header.addWidget(score)
        header.addStretch(1)
        repeat = build_repeat_warning(evaluation, self.context)
        header.addWidget(Badge("Repeat risk", "danger") if repeat else
                         Badge("No repeat detected", "success"))
        layout.addLayout(header)

        grid = QGridLayout()
        grid.setSpacing(10)
        slots = _slot_order(outfit)
        columns = 3 if len(slots) == 3 else 2
        for position, slot in enumerate(slots):
            tile = SlotTile(outfit.items[slot], slot)
            row, col = divmod(position, columns)
            grid.addWidget(tile, row, col)
        for col in range(columns):
            grid.setColumnStretch(col, 1)
        layout.addLayout(grid)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        wear = QPushButton("Log wear…")
        wear.setProperty("variant", "primary")
        wear.setMinimumHeight(40)
        wear.setIcon(media.icon("fa6s.calendar-check", COLORS["white"], 16))
        wear.setCursor(Qt.CursorShape.PointingHandCursor)
        wear.clicked.connect(lambda: self._log_wear(outfit))
        save = QPushButton("Save look")
        save.setProperty("variant", "ghost")
        save.setMinimumHeight(40)
        save.setCursor(Qt.CursorShape.PointingHandCursor)
        save.clicked.connect(lambda: self._save_look(outfit, evaluation))
        shuffle = QPushButton("Shuffle")
        shuffle.setProperty("variant", "quiet")
        shuffle.setMinimumHeight(40)
        shuffle.setIcon(media.icon("fa6s.arrows-rotate", COLORS["textMuted"], 16))
        shuffle.setCursor(Qt.CursorShape.PointingHandCursor)
        shuffle.clicked.connect(self._shuffle)
        actions.addWidget(wear)
        actions.addWidget(save)
        actions.addWidget(shuffle)
        actions.addStretch(1)
        layout.addLayout(actions)

        note = QLabel(self._rank_note(outfit, evaluation))
        note.setProperty("role", "muted")
        layout.addWidget(note)
        return card

    def _shuffle(self) -> None:
        if not self.picks:
            return
        if len(self.picks) > 1:
            self.index = (self.index + 1) % len(self.picks)
            self._render_suggestions()
            return
        outfit = self.picks[0][0]
        top = outfit.items.get("top")
        self.locks = {"top": top.id} if top else {}
        self.regenerate()
        self.locks = {}

    # -------------------------------------------------------------------- XAI
    def _render_xai(self, outfit: Outfit, evaluation: Evaluation) -> None:
        layout = self.xaiHostLayout
        clear_layout(layout)
        self.base_evaluation = evaluation
        self._what_if_outfit = outfit
        self._rows = []

        head = QHBoxLayout()
        title = QLabel("Why this outfit")
        title.setProperty("role", "h2")
        head.addWidget(title)
        head.addStretch(1)
        layout.addWidget(self._wrap(head))

        card = SectionCard()
        body = card.body()
        body.setSpacing(14)

        for index, contribution in enumerate(evaluation.contributions):
            row = ContributionRow()
            row.set_data(index, contribution)
            self._rows.append(row)
            body.addWidget(row)

        body.addWidget(Divider())

        total = QHBoxLayout()
        total_label = QLabel("Total")
        total_label.setObjectName("contribLabel")
        total.addWidget(total_label)
        total.addStretch(1)
        total_value = QLabel(f"{evaluation.score:.1f} / 100")
        total_value.setObjectName("totalScore")
        total.addWidget(total_value)
        self._delta_label = QLabel("")
        self._delta_label.setProperty("badge", True)
        self._delta_label.setProperty("tone", "neutral")
        self._delta_label.hide()
        total.addWidget(self._delta_label)
        body.addLayout(total)

        layout.addWidget(card)

        text = build_rationale(evaluation, self.context, outfit).strip()
        if text:
            rationale = SectionCard()
            label = QLabel()
            label.setWordWrap(True)
            label.setObjectName("rationaleText")
            label.setTextFormat(Qt.TextFormat.RichText)
            escaped = (
                text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\n", "<br>")
            )
            label.setText(f"<div style='line-height:160%; margin:0;'>{escaped}</div>")
            rationale.add(label)
            layout.addWidget(rationale)

        layout.addWidget(self._what_if_card(outfit, evaluation))
        layout.addStretch(1)

    def _wrap(self, layout) -> QWidget:
        holder = QWidget()
        holder.setLayout(layout)
        layout.setContentsMargins(0, 0, 0, 0)
        return holder

    def _what_if_card(self, outfit: Outfit, evaluation: Evaluation) -> QWidget:
        card = SectionCard("What-If")
        body = card.body()

        temp_row = QHBoxLayout()
        label = QLabel("Temperature")
        label.setProperty("role", "muted")
        temp_row.addWidget(label)
        temp_row.addStretch(1)
        value = QLabel(f"{self.context.temperature:.0f}°C")
        value.setObjectName("whatIfValue")
        temp_row.addWidget(value)
        body.addLayout(temp_row)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(14, 40)
        slider.setValue(int(round(self.context.temperature)))
        body.addWidget(slider)

        controls = QHBoxLayout()
        controls.setSpacing(10)
        rain = QCheckBox("Rain")
        rain.setChecked(self.context.is_rain)
        controls.addWidget(rain)
        occasion = QComboBox()
        occasion.addItems(OCCASIONS)
        occasion.setCurrentText(self.context.occasion)
        controls.addWidget(occasion, 1)
        reset = QPushButton("Reset")
        reset.setProperty("variant", "quiet")
        reset.setCursor(Qt.CursorShape.PointingHandCursor)
        controls.addWidget(reset)
        body.addLayout(controls)

        def apply() -> None:
            context = replace(
                self.context,
                temperature=float(slider.value()),
                is_rain=rain.isChecked(),
                occasion=occasion.currentText(),
            )
            value.setText(f"{slider.value()}°C")
            result = evaluate(outfit, context, self.repo.wear_stats(), self.config)
            for index, row in enumerate(self._rows):
                contribution = result.contributions[index]
                delta = contribution.points - evaluation.contributions[index].points
                row.set_data(index, contribution, delta=delta)
            diff = result.score - evaluation.score
            self._delta_label.setText(
                f"{evaluation.score:.0f} → {result.score:.0f}  ({diff:+.1f})"
            )
            self._delta_label.setProperty(
                "tone", "success" if diff > 0.05 else ("danger" if diff < -0.05 else "neutral")
            )
            self._delta_label.style().unpolish(self._delta_label)
            self._delta_label.style().polish(self._delta_label)
            self._delta_label.show()

        def on_reset() -> None:
            slider.setValue(int(round(self.context.temperature)))
            rain.setChecked(self.context.is_rain)
            occasion.setCurrentText(self.context.occasion)
            for index, row in enumerate(self._rows):
                row.set_data(index, evaluation.contributions[index])
            self._delta_label.setText("")
            self._delta_label.setProperty("tone", "neutral")
            self._delta_label.style().unpolish(self._delta_label)
            self._delta_label.style().polish(self._delta_label)
            self._delta_label.hide()

        slider.valueChanged.connect(lambda _: apply())
        rain.toggled.connect(lambda _: apply())
        occasion.currentTextChanged.connect(lambda _: apply())
        reset.clicked.connect(on_reset)
        return card

    # ---------------------------------------------------------------- actions
    def _log_wear(self, outfit: Outfit) -> None:
        worn_on = ask_wear_date(self, "Log wear")
        if worn_on is None:
            return
        self.repo.log_wear(outfit, worn_on=worn_on, feedback=None, note="from stylist")
        self.wearLogged.emit()
        self.toastRequested.emit(f"Logged “{outfit.name}” for {worn_on.isoformat()}", "success")
        self._build_history()

    def _save_look(self, outfit: Outfit, evaluation: Evaluation) -> None:
        saved = Outfit(
            id="", name=outfit.name, score=evaluation.score, source="ai",
            is_favorite=True, items=dict(outfit.items),
        )
        self.repo.save_outfit(saved)
        self.toastRequested.emit(f"Saved “{outfit.name}” to your looks", "success")
        self._build_saved()

    # ------------------------------------------------------------ saved looks
    def _build_saved(self) -> None:
        host = self.savedHost
        if host.layout() is None:
            layout = QVBoxLayout(host)
            layout.setContentsMargins(0, 0, 8, 0)
            layout.setSpacing(10)
        else:
            layout = host.layout()
            clear_layout(layout)

        outfits = self.repo.list_outfits()
        if not outfits:
            layout.addWidget(self._empty_state(
                "fa6s.bookmark", "No saved looks yet",
                "Press “Save look” on a recommendation and it will appear here, "
                "ready to wear again.",
            ))
            layout.addStretch(1)
            return

        stats = self.repo.wear_stats()
        for outfit in outfits:
            evaluation = evaluate(outfit, self.context, stats, self.config)
            row = OutfitListItem(
                outfit, evaluation.score,
                f"saved {outfit.created_at[:10]} · {len(outfit.items)} pieces",
                actions=(("wear", "Wear", "primary"), ("delete", "Delete", "danger")),
            )
            row.clicked.connect(lambda _id, o=outfit: self._show_outfit_in_tab(o))
            row.actionTriggered.connect(self._saved_action)
            layout.addWidget(row)
        layout.addStretch(1)

    def _show_outfit_in_tab(self, outfit: Outfit) -> None:
        stats = self.repo.wear_stats()
        pair = (outfit, evaluate(outfit, self.context, stats, self.config))
        self._use_pair(pair)
        self.tabs.setCurrentIndex(0)

    def _saved_action(self, action: str, outfit_id: str) -> None:
        outfit = self.repo.get_outfit(outfit_id)
        if not outfit:
            return
        if action == "wear":
            self._log_wear(outfit)
        elif action == "delete":
            self.repo.delete_outfit(outfit_id)
            self.toastRequested.emit("Look removed", "danger")
            self._build_saved()

    # ---------------------------------------------------------------- history
    def _build_history_filter(self) -> None:
        self.historyMonthFilter.addItem("All time", "")
        entries = self.repo.wear_entries(limit=400)
        months = sorted({entry.worn_on[:7] for entry in entries}, reverse=True)
        for month in months[:8]:
            label = month
            try:
                year, month_number = month.split("-")
                label = f"{['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][int(month_number) - 1]} {year}"
            except (ValueError, IndexError):
                pass
            self.historyMonthFilter.addItem(label, month)
        self.historyMonthFilter.currentIndexChanged.connect(lambda _: self._build_history())

    def _build_history(self) -> None:
        layout = self.historyHostLayout
        clear_layout(layout)
        month = self.historyMonthFilter.currentData() or ""
        entries = self.repo.wear_entries(limit=80, month=month)
        if not entries:
            layout.addWidget(self._empty_state(
                "fa6s.clock-rotate-left", "Nothing logged yet",
                "Wear an outfit from the Suggested tab and it shows up here.",
            ))
            layout.addStretch(1)
            return

        for entry in entries:
            layout.addWidget(self._history_row(entry))
        layout.addStretch(1)

    def _history_row(self, entry) -> QWidget:
        frame = QFrame()
        frame.setProperty("listCard", True)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)

        day = QLabel(entry.worn_on[8:10])
        day.setObjectName("historyDay")
        layout.addWidget(day)

        month = QLabel(entry.worn_on[:7])
        month.setProperty("role", "label")
        layout.addWidget(month)

        if entry.outfit:
            for garment in entry.outfit.ordered_items()[:3]:
                thumb = QLabel()
                thumb.setPixmap(media.garment_pixmap(garment, 52, 40))
                thumb.setFixedSize(52, 40)
                layout.addWidget(thumb)

        text = QVBoxLayout()
        text.setSpacing(1)
        title = ElidedLabel(entry.outfit.name if entry.outfit else "Removed outfit")
        title.setObjectName("listTitle")
        text.addWidget(title)
        note = ElidedLabel(entry.note or "logged wear")
        note.setProperty("role", "muted")
        text.addWidget(note)
        layout.addLayout(text, 1)

        for value, icon_name, tone in (
            (1, "fa6s.thumbs-up", COLORS["successDeep"]),
            (0, "fa6s.thumbs-down", COLORS["danger"]),
        ):
            button = QPushButton()
            button.setCheckable(True)
            button.setChecked(entry.feedback == value)
            button.setProperty("variant", "quiet")
            button.setFixedSize(34, 34)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setIcon(media.icon(
                icon_name, tone if button.isChecked() else COLORS["textFaint"], 13
            ))
            button.clicked.connect(
                lambda _checked, entry_id=entry.id, val=value, btn=button:
                self._set_feedback(entry_id, val, btn)
            )
            layout.addWidget(button)
        return frame

    def _set_feedback(self, entry_id: int, value: int, button) -> None:
        self.repo.set_feedback(entry_id, value)
        self._build_history()
        self.toastRequested.emit("Feedback saved", "success")

    # ------------------------------------------------------------------ misc
    def _empty_state(self, icon_name: str, title: str, hint: str) -> QWidget:
        holder = QWidget()
        holder.setMinimumHeight(280)
        layout = QVBoxLayout(holder)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(10)
        icon = QLabel()
        icon.setPixmap(media.icon(icon_name, COLORS["textFaint"], 32).pixmap(32, 32))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading = QLabel(title)
        heading.setProperty("role", "h2")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text = QLabel(hint)
        text.setProperty("role", "muted")
        text.setWordWrap(True)
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text.setMaximumWidth(420)
        layout.addWidget(icon)
        layout.addWidget(heading)
        layout.addWidget(text)
        return holder
