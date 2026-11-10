"""Reusable widgets.

Qt Designer is used for the page skeletons; everything that repeats (cards,
score bars, calendar cells, chips) is built here because a static .ui file
cannot express a list whose length depends on the database.
"""

from __future__ import annotations

import calendar
from datetime import date

from datetime import date

from PyQt6.QtCore import QEvent, QPoint, QRect, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import (
    QCalendarWidget,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QMenu,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetItem,
)

from libs.models import CATEGORY_LABELS, SLOT_LABELS, Garment
from libs.theme import COLORS
from ui import media


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def elide(text: str, widget: QWidget, width: int) -> str:
    metrics = QFontMetrics(widget.font())
    return metrics.elidedText(text, Qt.TextElideMode.ElideRight, max(10, width))


def clear_layout(layout) -> None:
    """Remove and destroy every widget inside a layout."""
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())


class ElidedLabel(QLabel):
    """A label that cuts with an ellipsis instead of widening its parent."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._full = text
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def setText(self, text: str) -> None:  # noqa: N802 - Qt naming
        self._full = text
        self.setToolTip(text)
        self._refresh()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._refresh()

    def _refresh(self) -> None:
        width = max(10, self.contentsRect().width())
        super().setText(QFontMetrics(self.font()).elidedText(
            self._full, Qt.TextElideMode.ElideRight, width
        ))


class FlowLayout(QLayout):
    """Left-to-right layout that wraps, so the garment grid reflows on resize."""

    def __init__(self, parent=None, margin: int = 0, spacing: int = 14):
        super().__init__(parent)
        self._items: list[QWidgetItem] = []
        self._spacing = spacing
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item) -> None:  # noqa: N802
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):  # noqa: N802
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int):  # noqa: N802
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):  # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._do_layout(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._do_layout(rect, apply=True)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(margins.left() + margins.right(), margins.top() + margins.bottom())

    def clear(self) -> None:
        while self._items:
            item = self._items.pop()
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _do_layout(self, rect: QRect, apply: bool) -> int:
        margins = self.contentsMargins()
        area = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x, y = area.x(), area.y()
        line_height = 0
        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + self._spacing
            if next_x - self._spacing > area.right() and line_height > 0:
                x = area.x()
                y = y + line_height + self._spacing
                next_x = x + hint.width() + self._spacing
                line_height = 0
            if apply:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + margins.bottom()


# --------------------------------------------------------------------------
# small atoms
# --------------------------------------------------------------------------
class Chip(QPushButton):
    def __init__(self, text: str, count: int | None = None, parent=None):
        label = f"{text}  {count}" if count is not None else text
        super().__init__(label, parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("chip", True)
        self.setMinimumHeight(34)


class Badge(QLabel):
    """Status pill. Tone drives the colour, text always carries the meaning."""

    def __init__(self, text: str = "", tone: str = "neutral", parent=None):
        super().__init__(text, parent)
        self.setProperty("badge", True)
        self.set_tone(tone)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def set_tone(self, tone: str) -> None:
        self.setProperty("tone", tone)
        self.style().unpolish(self)
        self.style().polish(self)

    def set_state(self, text: str, tone: str) -> None:
        self.setText(text)
        self.set_tone(tone)


class MetricBar(QWidget):
    """Slim progress bar with a per-criterion colour."""

    def __init__(self, value: float = 0.0, tone: str = "#111827", parent=None):
        super().__init__(parent)
        self._value = max(0.0, min(1.0, value))
        self._tone = QColor(tone)
        self.setFixedHeight(8)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_value(self, value: float) -> None:
        self._value = max(0.0, min(1.0, value))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        rect = QRectF(0, 0, self.width(), self.height())
        painter.setBrush(QColor(COLORS["border"]))
        painter.drawRoundedRect(rect, 4, 4)
        filled = QRectF(0, 0, rect.width() * self._value, rect.height())
        if filled.width() > 0.5:
            painter.setBrush(self._tone)
            painter.drawRoundedRect(filled, 4, 4)


class Divider(QFrame):
    def __init__(self, vertical: bool = False, parent=None):
        super().__init__(parent)
        self.setProperty("divider", True)
        if vertical:
            self.setFixedWidth(1)
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        else:
            self.setFixedHeight(1)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)


class Toast(QLabel):
    """Transient confirmation in the corner - no modal dialog for routine saves."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("toast")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_message(self, text: str, tone: str = "ink", msec: int = 2600) -> None:
        self.setProperty("tone", tone)
        self.setText(text)
        self.style().unpolish(self)
        self.style().polish(self)
        self.adjustSize()
        parent = self.parentWidget()
        if parent:
            self.move(parent.width() - self.width() - 32, parent.height() - self.height() - 28)
        self.show()
        self.raise_()
        self._timer.start(msec)


class SectionCard(QFrame):
    """White card with an optional heading and a body layout."""

    def __init__(self, title: str = "", subtitle: str = "", parent=None):
        super().__init__(parent)
        self.setProperty("card", True)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(20, 18, 20, 18)
        self._layout.setSpacing(14)
        if title:
            header = QHBoxLayout()
            header.setSpacing(8)
            label = QLabel(title)
            label.setProperty("role", "h2")
            header.addWidget(label)
            header.addStretch(1)
            self.header = header
            self._layout.addLayout(header)
        if subtitle:
            hint = QLabel(subtitle)
            hint.setProperty("role", "muted")
            hint.setWordWrap(True)
            self._layout.addWidget(hint)

    def body(self) -> QVBoxLayout:
        return self._layout

    def add(self, widget: QWidget) -> None:
        self._layout.addWidget(widget)


# --------------------------------------------------------------------------
# garment card
# --------------------------------------------------------------------------
class GarmentCard(QFrame):
    clicked = pyqtSignal(str)
    editRequested = pyqtSignal(str)
    deleteRequested = pyqtSignal(str)
    logRequested = pyqtSignal(str)

    WIDTH = 236
    IMAGE_HEIGHT = 172

    def __init__(self, garment: Garment, wears: int = 0, days_since: int | None = None,
                 selected: bool = False, parent=None):
        super().__init__(parent)
        self.garment = garment
        self.setObjectName("garmentCard")
        self.setFixedSize(self.WIDTH, 292)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("selected", selected)
        self._build(wears, days_since)

    def _build(self, wears: int, days_since: int | None) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        image_holder = QFrame()
        image_holder.setObjectName("cardImageHolder")
        image_holder.setFixedHeight(self.IMAGE_HEIGHT)
        root.addWidget(image_holder)

        grid = QGridLayout(image_holder)
        grid.setContentsMargins(10, 10, 10, 10)

        picture = QLabel()
        picture.setPixmap(media.garment_pixmap(
            self.garment, self.WIDTH, self.IMAGE_HEIGHT
        ))
        picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(picture, 0, 0, 1, 1)

        self.badge = Badge(*freshness_state(days_since))
        grid.addWidget(self.badge, 0, 0, 1, 1,
                       Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        self.menu_button = QToolButton()
        self.menu_button.setObjectName("cardMenu")
        self.menu_button.setIcon(media.icon("fa6s.ellipsis", COLORS["text"], 14))
        self.menu_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.menu_button.clicked.connect(self._show_menu)
        grid.addWidget(self.menu_button, 0, 0, 1, 1,
                       Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)

        body = QVBoxLayout()
        body.setContentsMargins(14, 12, 14, 14)
        body.setSpacing(6)

        name = QLabel(self.garment.name)
        name.setObjectName("cardTitle")
        name.setWordWrap(True)
        name.setFixedHeight(38)
        name.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        body.addWidget(name)

        meta = ElidedLabel(
            f"{CATEGORY_LABELS.get(self.garment.category, '')} · {self.garment.material}"
        )
        meta.setProperty("role", "muted")
        body.addWidget(meta)

        body.addStretch(1)

        footer = QHBoxLayout()
        footer.setSpacing(6)
        code = QLabel(self.garment.id)
        code.setObjectName("cardCode")
        footer.addWidget(code)
        footer.addStretch(1)
        wear_label = QLabel(
            f"{wears} wear" if wears == 1 else (f"{wears} wears" if wears else "never worn")
        )
        wear_label.setObjectName("cardWears")
        footer.addWidget(wear_label)
        body.addLayout(footer)

        root.addLayout(body)
        self._apply_shadow(False)

    def _show_menu(self) -> None:
        menu = QMenu(self)
        menu.addAction(media.icon("fa6s.pen", COLORS["text"], 14), "Edit details",
                       lambda: self.editRequested.emit(self.garment.id))
        menu.addAction(media.icon("fa6s.calendar-check", COLORS["text"], 14), "Log a wear",
                       lambda: self.logRequested.emit(self.garment.id))
        menu.addSeparator()
        menu.addAction(media.icon("fa6s.trash", COLORS["danger"], 14), "Delete",
                       lambda: self.deleteRequested.emit(self.garment.id))
        menu.exec(self.menu_button.mapToGlobal(QPoint(0, self.menu_button.height())))

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)
        self._apply_shadow(selected)

    def _apply_shadow(self, enabled: bool) -> None:
        from PyQt6.QtGui import QColor as _QColor
        from PyQt6.QtWidgets import QGraphicsDropShadowEffect

        if not enabled:
            self.setGraphicsEffect(None)
            return
        effect = QGraphicsDropShadowEffect(self)
        effect.setBlurRadius(24)
        effect.setOffset(0, 6)
        effect.setColor(_QColor(17, 24, 39, 38))
        self.setGraphicsEffect(effect)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.garment.id)
        super().mousePressEvent(event)


def freshness_state(days_since: int | None) -> tuple[str, str]:
    """Single source of truth for the wear badge text + tone."""
    from libs.theme import FRESHNESS

    if days_since is None:
        return "New · never worn", "neutral"
    if days_since <= FRESHNESS["danger_days"]:
        return f"Worn {days_since}d ago · skip", "danger"
    if days_since <= FRESHNESS["warning_days"]:
        return f"Worn {days_since}d ago · rest", "warning"
    return f"Ready · {days_since}d", "success"


def ask_wear_date(parent: QWidget, title: str = "Log wear") -> date | None:
    """Ask the user which day an outfit was worn. Returns None if cancelled."""
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setModal(True)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(18, 16, 18, 16)
    layout.setSpacing(10)

    hint = QLabel("Pick the day you wore this look.")
    hint.setWordWrap(True)
    layout.addWidget(hint)

    picker = QDateEdit(dialog)
    picker.setCalendarPopup(True)
    picker.setDisplayFormat("yyyy-MM-dd")
    picker.setDate(date.today())
    picker.setMinimumHeight(36)
    layout.addWidget(picker)

    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        dialog,
    )
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    if dialog.exec() == QDialog.DialogCode.Accepted:
        qd = picker.date()
        return date(qd.year(), qd.month(), qd.day())
    return None


# --------------------------------------------------------------------------
# stylist widgets
# --------------------------------------------------------------------------
class SlotTile(QFrame):
    """One garment inside the outfit collage."""

    def __init__(self, garment: Garment, slot: str, parent=None):
        super().__init__(parent)
        self.garment = garment
        self.slot = slot
        self.setProperty("slotTile", True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        picture = QLabel()
        picture.setPixmap(media.garment_pixmap(garment, 190, 150))
        picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        picture.setFixedHeight(150)
        layout.addWidget(picture)

        top_row = QHBoxLayout()
        top_row.setSpacing(6)
        slot_label = QLabel(SLOT_LABELS.get(slot, slot).upper())
        slot_label.setProperty("role", "label")
        top_row.addWidget(slot_label)
        top_row.addStretch(1)
        code = QLabel(garment.id)
        code.setProperty("cardCode", True)
        top_row.addWidget(code)
        layout.addLayout(top_row)

        name = ElidedLabel(garment.name)
        name.setObjectName("slotName")
        layout.addWidget(name)

        meta = ElidedLabel(f"{garment.color_name} · {garment.material}")
        meta.setProperty("role", "muted")
        layout.addWidget(meta)


class ContributionRow(QWidget):
    """One explainable criterion: label, points, bar, evidence."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(8)
        self.label = QLabel()
        self.label.setObjectName("contribLabel")
        head.addWidget(self.label)
        head.addStretch(1)
        self.points = QLabel()
        self.points.setObjectName("contribPoints")
        head.addWidget(self.points)
        self.share = QLabel()
        self.share.setProperty("badge", True)
        self.share.setProperty("tone", "neutral")
        head.addWidget(self.share)
        layout.addLayout(head)

        self.bar = MetricBar()
        layout.addWidget(self.bar)

        self.evidence = QLabel()
        self.evidence.setProperty("role", "muted")
        self.evidence.setWordWrap(True)
        self.evidence.setTextFormat(Qt.TextFormat.RichText)
        self.evidence.setStyleSheet("margin-top: 2px;")
        layout.addWidget(self.evidence)

    def set_data(self, index: int, contribution, delta: float | None = None) -> None:
        tones = [COLORS["ink"], COLORS["amber"], COLORS["success"], "#7C8FA6"]
        tone = tones[index % len(tones)]
        self.label.setText(contribution.label)
        suffix = ""
        if delta is not None and abs(delta) >= 0.05:
            suffix = f"  ({delta:+.1f})"
        self.points.setText(f"{contribution.points:+.1f} pts{suffix}")
        self.share.setText(f"{contribution.percent:.0f}%")
        self.bar._tone = QColor(tone)
        self.bar.set_value(contribution.subscore)
        text = f"{contribution.detail} · {contribution.evidence}"
        escaped = (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        self.evidence.setText(f"<span style='line-height:155%;'>{escaped}</span>")


class OutfitListItem(QFrame):
    """Compact row used for rank #2, #3 and for saved looks."""

    clicked = pyqtSignal(str)
    actionTriggered = pyqtSignal(str, str)

    def __init__(self, outfit, score: float, note: str = "", actions=(), parent=None):
        super().__init__(parent)
        self.setProperty("listCard", True)
        self.outfit = outfit
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        thumbs = QHBoxLayout()
        thumbs.setSpacing(4)
        for garment in outfit.ordered_items()[:3]:
            thumb = QLabel()
            thumb.setPixmap(media.garment_pixmap(garment, 56, 44))
            thumb.setFixedSize(56, 44)
            thumbs.addWidget(thumb)
        layout.addLayout(thumbs)

        text = QVBoxLayout()
        text.setSpacing(2)
        title = ElidedLabel(outfit.name or "Untitled look")
        title.setObjectName("listTitle")
        text.addWidget(title)
        hint = ElidedLabel(note or ", ".join(g.id for g in outfit.ordered_items()))
        hint.setProperty("role", "muted")
        text.addWidget(hint)
        layout.addLayout(text, 1)

        score_label = QLabel(f"{score:.1f}")
        score_label.setObjectName("listScore")
        layout.addWidget(score_label)

        for key, label, variant in actions:
            button = QPushButton(label)
            button.setProperty("variant", variant)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda _=False, k=key: self.actionTriggered.emit(k, self.outfit.id)
            )
            layout.addWidget(button)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.outfit.id)
        super().mousePressEvent(event)


# --------------------------------------------------------------------------
# analytics
# --------------------------------------------------------------------------
class MonthCalendar(QWidget):
    """Month grid with one row of wear data per day.

    QCalendarWidget cannot render "which outfit was worn", so the grid is
    painted directly - it also keeps the styling consistent with the rest.
    """

    dayClicked = pyqtSignal(object)

    WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._year = date.today().year
        self._month = date.today().month
        self._data: dict[date, dict] = {}
        self._hover: date | None = None
        self.setMouseTracking(True)
        self.setMinimumHeight(360)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_month(self, year: int, month: int) -> None:
        self._year, self._month = year, month
        self.update()

    def set_data(self, data: dict[date, dict]) -> None:
        self._data = data
        self.update()

    def month_label(self) -> str:
        return date(self._year, self._month, 1).strftime("%B %Y")

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(COLORS["bg"]))

        weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(self._year, self._month)
        rows = len(weeks)
        header_h = 34
        cell_w = self.width() / 7
        cell_h = (self.height() - header_h) / max(1, rows)

        painter.setFont(media.body_font(8, 600))
        painter.setPen(QColor(COLORS["textMuted"]))
        for index, name in enumerate(self.WEEKDAYS):
            painter.drawText(
                QRectF(index * cell_w, 0, cell_w, header_h),
                Qt.AlignmentFlag.AlignCenter, name.upper(),
            )

        today = date.today()
        for row, week in enumerate(weeks):
            for col, day in enumerate(week):
                rect = QRectF(col * cell_w + 4, header_h + row * cell_h + 4,
                              cell_w - 8, cell_h - 8)
                self._paint_cell(painter, day, rect, today)
        painter.end()

    def _paint_cell(self, painter: QPainter, day: date, rect: QRectF, today: date) -> None:
        in_month = day.month == self._month
        info = self._data.get(day, {})
        is_today = day == today
        hovered = self._hover == day
        worn = bool(info.get("worn"))

        if not in_month:
            base = QColor(COLORS["surfaceAlt"])
            border = QColor(COLORS["border"])
        elif worn:
            base = QColor(COLORS["amberSoft"])
            border = QColor("#FCD34D")
        else:
            base = QColor(COLORS["surface"])
            border = QColor(COLORS["border"])
        if hovered and in_month:
            base = QColor("#FFFBEB") if worn else QColor("#F9FAFB")

        painter.setPen(QPen(border, 1))
        painter.setBrush(base)
        painter.drawRoundedRect(rect, 10, 10)

        if is_today:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(COLORS["amber"]), 2.0))
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 9, 9)

        text_color = QColor(COLORS["text"] if in_month else COLORS["textFaint"])
        painter.setPen(text_color)
        painter.setFont(media.body_font(9, 700 if (is_today or worn) else 500))
        painter.drawText(
            QRectF(rect.x() + 8, rect.y() + 5, rect.width() - 12, 16),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            str(day.day),
        )

        temperature = info.get("temperature")
        if temperature is not None and in_month:
            painter.setPen(QColor(COLORS["textMuted"]))
            painter.setFont(media.body_font(7))
            painter.drawText(
                QRectF(rect.x(), rect.y() + 5, rect.width() - 8, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{temperature:.0f}°",
            )

        names = info.get("outfits", [])
        if names and in_month:
            painter.setFont(media.body_font(7, 500))
            for index, name in enumerate(names[:2]):
                chip = QRectF(rect.x() + 6, rect.y() + 26 + index * 18,
                              rect.width() - 12, 16)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(COLORS["white"]))
                painter.drawRoundedRect(chip, 5, 5)
                painter.setPen(QPen(QColor(COLORS["border"]), 1))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(chip, 5, 5)
                painter.setPen(QColor(COLORS["text"]))
                painter.drawText(
                    chip.adjusted(6, 0, -4, 0),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    QFontMetrics(painter.font()).elidedText(
                        name, Qt.TextElideMode.ElideRight, int(chip.width() - 10)
                    ),
                )
            if len(names) > 2:
                painter.setPen(QColor(COLORS["textMuted"]))
                painter.drawText(
                    QRectF(rect.x() + 6, rect.bottom() - 16, rect.width() - 12, 14),
                    Qt.AlignmentFlag.AlignLeft,
                    f"+{len(names) - 2} more",
                )

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        day = self._day_at(event.position().x(), event.position().y())
        if day != self._hover:
            self._hover = day
            self.setCursor(
                Qt.CursorShape.PointingHandCursor if day else Qt.CursorShape.ArrowCursor
            )
            self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = None
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        day = self._day_at(event.position().x(), event.position().y())
        if day:
            self.dayClicked.emit(day)

    def _day_at(self, x: float, y: float) -> date | None:
        weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(self._year, self._month)
        header_h = 34
        cell_w = self.width() / 7
        cell_h = (self.height() - header_h) / max(1, len(weeks))
        if y < header_h:
            return None
        row = int((y - header_h) / cell_h)
        col = int(x / cell_w)
        if 0 <= row < len(weeks) and 0 <= col < 7:
            return weeks[row][col]
        return None


class DensityBar(QWidget):
    """Stacked bar showing how the closet splits across categories."""

    SEGMENTS = [
        ("top", "Tops", COLORS["ink"]),
        ("bottom", "Bottoms", COLORS["amber"]),
        ("shoes", "Shoes", COLORS["success"]),
        ("outer", "Outerwear", "#7C8FA6"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._counts: dict[str, int] = {}
        self.setFixedHeight(14)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_counts(self, counts: dict[str, int]) -> None:
        self._counts = counts
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        total = sum(self._counts.values()) or 1
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        x = 0.0
        for key, _label, color in self.SEGMENTS:
            value = self._counts.get(key, 0)
            if not value:
                continue
            width = self.width() * value / total
            painter.setBrush(QColor(color))
            painter.drawRoundedRect(QRectF(x, 0, max(0.0, width - 2), self.height()), 4, 4)
            x += width
        painter.end()


class DonutMeter(QWidget):
    """Small ring showing a single percentage (used for utilization)."""

    def __init__(self, value: float = 0.0, tone: str = COLORS["success"], parent=None):
        super().__init__(parent)
        self._value = max(0.0, min(1.0, value))
        self._tone = QColor(tone)
        self.setFixedSize(84, 84)

    def set_value(self, value: float) -> None:
        self._value = max(0.0, min(1.0, value))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(6, 6, self.width() - 12, self.height() - 12)
        painter.setPen(QPen(QColor(COLORS["border"]), 9, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap))
        painter.drawArc(rect, 0, 360 * 16)
        painter.setPen(QPen(self._tone, 9, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap))
        painter.drawArc(rect, 90 * 16, -int(360 * 16 * self._value))
        painter.setPen(QColor(COLORS["text"]))
        painter.setFont(media.headline_font(13, 700))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                         f"{self._value * 100:.0f}%")
        painter.end()
