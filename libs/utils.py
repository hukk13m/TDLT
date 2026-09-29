from PyQt6.QtWidgets import QMessageBox

def is_leap_year(year):
    if ((year % 4 == 0 and year % 100 != 0) or year % 400 == 0):
        return True
    else:
        return False

def call_close_app():
    msgBox = QMessageBox()
    msgBox.setWindowTitle("Thoat?")
    msgBox.setText("Confirmed?")
    msgBox.setIcon(QMessageBox.Icon.Question)
    buttons = QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    msgBox.setStandardButtons(buttons)
    ret = msgBox.exec()
    if ret == QMessageBox.StandardButton.Yes:
        raise SystemExit(0)