import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QMainWindow

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ui.BMIMainWindowEx import BMIMainWindowEx

app = QApplication(sys.argv)
main_window = QMainWindow()
bmi_ui = BMIMainWindowEx()
bmi_ui.setupUi(main_window)
bmi_ui.show_window()

sys.exit(app.exec())