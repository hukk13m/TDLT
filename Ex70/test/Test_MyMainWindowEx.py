import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Chap5.Ex70.UI.MyMainWindowEx import MyMainWindowEx


if __name__ == "__main__":
    app = QApplication(sys.argv)
    myui = MyMainWindowEx()
    myui.show_window()
    sys.exit(app.exec())
