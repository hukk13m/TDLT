from PyQt6.QtWidgets import QMainWindow

from Chap5.Ex70.UI.MyMainWindow import Ui_MainWindow
from Chap5.Ex70.libs.my_module import get_number_of_days


class MyMainWindowEx(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.setupSignalandSlot()

    def show_window(self):
        self.show()

    def setupSignalandSlot(self):
        self.pushButton.clicked.connect(self.count_days)

    def count_days(self):
        year = int(self.yearLineEdit.text())
        month = int(self.monthLineEdit.text())
        day = get_number_of_days(year, month)
        self.resultLineEdit.setText(str(day))