"""Acloset Studio - smart wardrobe desktop app (PyQt6).

Run from the project root:

    python main.py

The SQLite database is created and seeded on first launch, so there is no
setup step. Weather is optional: without a network connection the app falls
back to a seasonal estimate and says so on screen.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from libs import db, theme
from libs.repo import Repository
from ui import media
from ui.MainWindowEx import MainWindowEx


def build_stylesheet() -> str:
    qss_path = media.ASSETS / "qss" / "app.qss"
    raw = qss_path.read_text(encoding="utf-8")
    rendered = theme.render_qss(raw)
    return rendered.replace("{{assets}}", str(media.ASSETS).replace("\\", "/"))


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("Acloset Studio")
    app.setApplicationDisplayName("Acloset Studio")
    app.setOrganizationName("Talent K24")

    media.load_fonts()
    app.setFont(media.body_font(10))
    app.setStyleSheet(build_stylesheet())

    connection = db.connect()
    repo = Repository(connection)
    if repo.ensure_seeded():
        print("Seeded demo wardrobe: 28 garments + 20 wear entries")

    window = MainWindowEx(repo)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
