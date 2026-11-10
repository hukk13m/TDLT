"""Style Analytics page: KPIs, wear calendar and closet health."""

from __future__ import annotations

import calendar as calendar_module
from datetime import date

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from libs.models import CATEGORY_LABELS
from libs.theme import COLORS
from libs.xai.rationale import build_insights
from ui import media
from ui.Ui_AnalyticsPage import Ui_AnalyticsPage
from ui.widgets import (
    Badge,
    DensityBar,
    Divider,
    ElidedLabel,
    MonthCalendar,
    SectionCard,
    clear_layout,
)


class AnalyticsPageEx(QWidget, Ui_AnalyticsPage):
    styleItemRequested = pyqtSignal(str)
    toastRequested = pyqtSignal(str, str)

    def __init__(self, repo, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.repo = repo
        self.today = date.today()
        self._year = self.today.year
        self._month = self.today.month

        self.calendar = MonthCalendar()
        self.calendarGrid.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        holder = QVBoxLayout(self.calendarGrid)
        holder.setContentsMargins(0, 0, 0, 0)
        holder.addWidget(self.calendar)
        self.calendar.dayClicked.connect(self._on_day_clicked)

        self.prevMonth.setIcon(media.icon("fa6s.chevron-left", COLORS["text"], 14))
        self.nextMonth.setIcon(media.icon("fa6s.chevron-right", COLORS["text"], 14))
        self.prevMonth.clicked.connect(lambda: self._shift_month(-1))
        self.nextMonth.clicked.connect(lambda: self._shift_month(1))

        self.refresh()

    # ------------------------------------------------------------------ month
    def _shift_month(self, delta: int) -> None:
        month = self._month + delta
        year = self._year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        self._year, self._month = year, month
        self.refresh_calendar()

    def refresh(self) -> None:
        analytics = self.repo.analytics()
        stats = analytics["stats"]

        self.kpiTotalValue.setText(str(analytics["total"]))
        categories = len([c for c, n in analytics["density"].items() if n])
        self.kpiTotalHint.setText(f"across {categories} categories")

        self.kpiUtilValue.setText(f"{analytics['utilization']:.0f}%")
        sleeping = analytics["sleeping"]
        self.kpiUtilHint.setText(
            f"{analytics['worn_count']} of {analytics['total']} worn at least once"
        )

        prevention = analytics["rest_compliance"]
        self.kpiRepeatValue.setText(f"{prevention:.0f}%")
        self.kpiRepeatHint.setText(
            f"{prevention:.0f}% of re-wears respected the 3-day rest target"
        )

        self.kpiSleepingValue.setText(f"{len(sleeping)} items")
        self.kpiSleepingHint.setText("unworn for more than 14 days")

        self.refresh_calendar()
        self._build_side(analytics, stats)

    def _repeat_prevention(self) -> float:
        return self.repo.analytics()["rest_compliance"]

    def refresh_calendar(self) -> None:
        self.calendar.set_month(self._year, self._month)
        self.calendarMonth.setText(self.calendar.month_label())

        data: dict[date, dict] = {}
        weeks = calendar_module.Calendar(firstweekday=0).monthdatescalendar(
            self._year, self._month
        )
        weather = self.repo.get_weather_cache() or {}
        for week in weeks:
            for day in week:
                if day.month != self._month:
                    continue
                outfits = self.repo.outfits_on(day)
                entry = {"worn": bool(outfits)}
                if outfits:
                    entry["outfits"] = [o.name or "Untitled look" for o in outfits]
                if day == self.today and weather.get("temperature") is not None:
                    entry["temperature"] = weather["temperature"]
                data[day] = entry
        self.calendar.set_data(data)

        logged = len([d for d in data.values() if d.get("worn")])
        self.calendarFooter.setText(
            f"{logged} outfits logged this month · "
            f"{self._repeat_prevention():.0f}% of re-wears respected the 3-day rest target."
        )

    def _on_day_clicked(self, day: date) -> None:
        outfits = self.repo.outfits_on(day)
        if not outfits:
            self.toastRequested.emit(
                f"No outfit logged on {day.strftime('%d %b')}", "danger"
            )
            return
        names = ", ".join(outfit.name for outfit in outfits)
        self.toastRequested.emit(f"{day.strftime('%d %b')}: {names}", "success")

    # ------------------------------------------------------------------- side
    def _build_side(self, analytics: dict, stats: dict) -> None:
        layout = self.sideHostLayout
        clear_layout(layout)

        layout.addWidget(self._density_card(analytics))
        layout.addWidget(self._favorites_card(analytics, stats))
        layout.addWidget(self._sleeping_card(analytics))
        layout.addWidget(self._insights_card(analytics))
        layout.addStretch(1)

    def _density_card(self, analytics: dict) -> QWidget:
        card = SectionCard("Closet composition")
        body = card.body()
        body.setSpacing(10)
        bar = DensityBar()
        bar.set_counts(analytics["density"])
        body.addWidget(bar)

        total = sum(analytics["density"].values()) or 1
        for key, label, color in DensityBar.SEGMENTS:
            count = analytics["density"].get(key, 0)
            row = QHBoxLayout()
            row.setSpacing(8)
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {color}; font-size: 10px;")
            row.addWidget(dot)
            name = QLabel(label)
            name.setProperty("role", "muted")
            row.addWidget(name)
            row.addStretch(1)
            value = QLabel(f"{count} · {100 * count / total:.0f}%")
            value.setObjectName("attrValue")
            row.addWidget(value)
            body.addLayout(row)
        return card

    def _favorites_card(self, analytics: dict, stats: dict) -> QWidget:
        card = SectionCard("Most worn", "The pieces carrying the rotation.")
        body = card.body()
        worn = [g for g in analytics["most_worn"] if stats.get(g.id, {}).get("count")]
        if not worn:
            hint = QLabel("No wear history yet - log a look to populate this.")
            hint.setProperty("role", "muted")
            hint.setWordWrap(True)
            body.addWidget(hint)
            return card
        for garment in worn[:3]:
            row = QHBoxLayout()
            row.setSpacing(10)
            thumb = QLabel()
            thumb.setPixmap(media.garment_pixmap(garment, 46, 38))
            thumb.setFixedSize(46, 38)
            row.addWidget(thumb)
            text = QVBoxLayout()
            text.setSpacing(1)
            name = ElidedLabel(garment.name)
            name.setObjectName("attrValue")
            text.addWidget(name)
            meta = ElidedLabel(f"{CATEGORY_LABELS.get(garment.category, '')} · {garment.id}")
            meta.setProperty("role", "muted")
            text.addWidget(meta)
            row.addLayout(text, 1)
            count = stats.get(garment.id, {}).get("count", 0)
            row.addWidget(Badge(f"{count} wears", "neutral"))
            body.addLayout(row)
        return card

    def _sleeping_card(self, analytics: dict) -> QWidget:
        card = SectionCard("Sleeping clothes")
        body = card.body()
        sleeping = analytics["sleeping"][:4]
        if not sleeping:
            hint = QLabel("Nothing is sleeping. Every piece has been worn recently.")
            hint.setProperty("role", "muted")
            hint.setWordWrap(True)
            body.addWidget(hint)
            return card
        for garment in sleeping:
            row = QHBoxLayout()
            row.setSpacing(10)
            thumb = QLabel()
            thumb.setPixmap(media.garment_pixmap(garment, 46, 38))
            thumb.setFixedSize(46, 38)
            row.addWidget(thumb)
            text = QVBoxLayout()
            text.setSpacing(1)
            name = ElidedLabel(garment.name)
            name.setObjectName("attrValue")
            text.addWidget(name)
            days = analytics["days_since"].get(garment.id)
            meta = ElidedLabel(
                "never worn" if days is None else f"unworn for {days} days"
            )
            meta.setProperty("role", "muted")
            text.addWidget(meta)
            row.addLayout(text, 1)
            button = QPushButton("Style it")
            button.setProperty("variant", "ghost")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda _=False, gid=garment.id: self.styleItemRequested.emit(gid)
            )
            row.addWidget(button)
            body.addLayout(row)
        return card

    def _insights_card(self, analytics: dict) -> QWidget:
        card = SectionCard("Insights")
        body = card.body()
        body.setSpacing(8)
        for line in build_insights(analytics):
            label = QLabel()
            label.setWordWrap(True)
            label.setTextFormat(Qt.TextFormat.RichText)
            label.setText(f"<p style='margin:0; line-height:160%;'>{self._escape_rich(line)}</p>")
            label.setProperty("role", "muted")
            body.addWidget(label)
        return card

    @staticmethod
    def _escape_rich(text: str) -> str:
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;")
        )
