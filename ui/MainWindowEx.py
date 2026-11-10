"""Application shell: sidebar navigation, shared services, cross-page signals."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QButtonGroup,
    QMainWindow,
    QMenu,
    QMessageBox,
)

from libs import weather as weather_service
from libs.theme import COLORS
from ui import media
from ui.AnalyticsPageEx import AnalyticsPageEx
from ui.StylistPageEx import StylistPageEx
from ui.Ui_MainWindow import Ui_MainWindow
from ui.WardrobePageEx import WardrobePageEx
from ui.widgets import Toast

CAPACITY = 60


class WeatherWorker(QThread):
    """Fetches weather off the UI thread. Never touches the database."""

    result = pyqtSignal(object)

    def __init__(self, lat: float, lon: float, parent=None):
        super().__init__(parent)
        self.lat = lat
        self.lon = lon

    def run(self) -> None:  # noqa: D401
        try:
            self.result.emit(weather_service.fetch(self.lat, self.lon))
        except Exception:  # noqa: BLE001 - the UI falls back to cache/seasonal
            self.result.emit(None)


class MainWindowEx(QMainWindow, Ui_MainWindow):
    def __init__(self, repo):
        super().__init__()
        self.setupUi(self)
        self.repo = repo
        self.context, (self.lat, self.lon) = repo.load_context()
        self._worker: WeatherWorker | None = None

        self._decorate()
        self._create_pages()
        self._connect()
        self._shortcuts()

        self.toast = Toast(self)
        self._go(0)
        self._refresh_sidebar()
        # Show cached/seasonal weather immediately so the stylist never starts
        # with an empty "--°C" card; the live fetch replaces it when it lands.
        self.stylist_page.set_weather(weather_service.cached_or_seasonal(self.repo))
        self._load_weather()

    # ------------------------------------------------------------------ setup
    _NAV_ICONS = ("fa6s.shirt", "fa6s.wand-magic-sparkles", "fa6s.chart-pie")

    def _decorate(self) -> None:
        self.navWardrobe.setIcon(media.icon("fa6s.shirt", COLORS["textMuted"], 16))
        self.navStylist.setIcon(
            media.icon("fa6s.wand-magic-sparkles", COLORS["textMuted"], 16)
        )
        self.navAnalytics.setIcon(media.icon("fa6s.chart-pie", COLORS["textMuted"], 16))
        self.settingsButton.setIcon(media.icon("fa6s.gear", COLORS["textMuted"], 16))

        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        for button in (self.navWardrobe, self.navStylist, self.navAnalytics):
            self._nav_group.addButton(button)
        self.navWardrobe.clicked.connect(lambda: self._go(0))
        self.navStylist.clicked.connect(lambda: self._go(1))
        self.navAnalytics.clicked.connect(lambda: self._go(2))

    def _create_pages(self) -> None:
        self.wardrobe_page = WardrobePageEx(self.repo, self)
        self.stylist_page = StylistPageEx(self.repo, self)
        self.analytics_page = AnalyticsPageEx(self.repo, self)
        for page in (self.wardrobe_page, self.stylist_page, self.analytics_page):
            self.pageStack.addWidget(page)

    def _connect(self) -> None:
        self.wardrobe_page.garmentChanged.connect(self._on_garment_changed)
        self.wardrobe_page.findOutfitsRequested.connect(self._style_item)
        self.wardrobe_page.toastRequested.connect(self._show_toast)

        self.stylist_page.wearLogged.connect(self._on_wear_logged)
        self.stylist_page.toastRequested.connect(self._show_toast)

        self.analytics_page.styleItemRequested.connect(self._style_item)
        self.analytics_page.toastRequested.connect(self._show_toast)

        self.settingsButton.clicked.connect(self._show_settings_menu)

    def _shortcuts(self) -> None:
        for index, keys in enumerate(("Ctrl+1", "Ctrl+2", "Ctrl+3")):
            shortcut = QShortcut(QKeySequence(keys), self)
            shortcut.activated.connect(lambda i=index: self._go(i))
        search = QShortcut(QKeySequence("Ctrl+F"), self)
        search.activated.connect(self._focus_search)
        new_item = QShortcut(QKeySequence("Ctrl+N"), self)
        new_item.activated.connect(self.wardrobe_page.addButton.click)

    # ------------------------------------------------------------------ pages
    def _go(self, index: int) -> None:
        self.pageStack.setCurrentIndex(index)
        buttons = (self.navWardrobe, self.navStylist, self.navAnalytics)
        buttons[index].setChecked(True)
        for position, button in enumerate(buttons):
            colour = COLORS["white"] if position == index else COLORS["textMuted"]
            button.setIcon(media.icon(self._NAV_ICONS[position], colour, 16))
        if index == 1:
            self.stylist_page.refresh()
        elif index == 2:
            self.analytics_page.refresh()

    def _focus_search(self) -> None:
        self._go(0)
        self.wardrobe_page.searchInput.setFocus()
        self.wardrobe_page.searchInput.selectAll()

    def _on_garment_changed(self) -> None:
        self._refresh_sidebar()
        self.stylist_page.refresh()
        self.analytics_page.refresh()

    def _on_wear_logged(self) -> None:
        self.wardrobe_page.refresh()
        self.analytics_page.refresh()
        self.stylist_page.refresh()
        self._refresh_sidebar()

    def _style_item(self, garment_id: str) -> None:
        garment = self.repo.get_garment(garment_id)
        if not garment:
            return
        self.stylist_page.locks = {garment.category: garment.id}
        if garment.category == "outer":
            self.stylist_page.context.outer_mode = "include"
            self.repo.save_context(self.stylist_page.context)
        self._go(1)
        self.stylist_page.refresh()
        # Keep the lock selected in UI but allow user to change after; don't auto-clear.
        self.stylist_page.tabs.setCurrentIndex(0)
        self._show_toast(f"Styling around {garment.name} (slot locked)", "success")

    def _show_toast(self, message: str, tone: str = "ink") -> None:
        self.toast.show_message(message, tone)

    # ------------------------------------------------------------------ misc
    def _refresh_sidebar(self) -> None:
        total = len(self.repo.list_garments())
        self.capacityValue.setText(f"{total} / {CAPACITY}")
        self.capacityBar.setValue(min(total, CAPACITY))
        self.capacityHint.setText(f"{round(100 * total / CAPACITY)}% full")

    def _show_settings_menu(self) -> None:
        menu = QMenu(self)
        refresh = QAction(media.icon("fa6s.rotate", COLORS["text"], 13),
                          "Refresh weather", self)
        refresh.triggered.connect(lambda: self._load_weather(notify=True))
        menu.addAction(refresh)
        about = QAction(media.icon("fa6s.circle-info", COLORS["text"], 13),
                        "How scoring works", self)
        about.triggered.connect(self._show_model_info)
        menu.addAction(about)
        menu.exec(self.settingsButton.mapToGlobal(
            self.settingsButton.rect().bottomLeft()
        ))

    def _show_model_info(self) -> None:
        QMessageBox.information(
            self,
            "How the recommendation is scored",
            "The stylist scores every valid combination with four criteria:\n\n"
            "  • Colour harmony\n"
            "  • Occasion & style fit\n"
            "  • Weather suitability\n"
            "  • Freshness & anti-repetition\n\n"
            "score = 100 x SUM(weight x sub-score), with the weights summing to 1.\n"
            "Because the model is additive, each row in the explanation panel is a "
            "real share of the final score, and the What-If simulator can show the "
            "exact delta per criterion. Weights live in libs/xai/weights.json.",
        )

    # --------------------------------------------------------------- weather
    def _load_weather(self, notify: bool = False) -> None:
        if self._worker and self._worker.isRunning():
            return
        self._worker = WeatherWorker(self.lat, self.lon, self)
        self._worker.result.connect(self._on_weather)
        self._worker.start()
        if notify:
            self._show_toast("Updating weather...", "ink")

    def _on_weather(self, payload) -> None:
        if payload:
            self.repo.set_weather_cache(payload)
            data = payload
        else:
            data = weather_service.cached_or_seasonal(self.repo)
        self.stylist_page.set_weather(data)
        self.analytics_page.refresh()

    # ---------------------------------------------------------------- events
    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "toast") and self.toast.isVisible():
            self.toast.move(
                self.width() - self.toast.width() - 32,
                self.height() - self.toast.height() - 28,
            )

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(1500)
        super().closeEvent(event)
