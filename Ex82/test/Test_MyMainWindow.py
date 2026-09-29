import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Chap5.Ex82.ui.MyMainWindowEx import KWhMainWindowEx


if __name__ == "__main__":
    app = QApplication(sys.argv)
    myui = KWhMainWindowEx()
    myui.showWindow()
    sys.exit(app.exec())
