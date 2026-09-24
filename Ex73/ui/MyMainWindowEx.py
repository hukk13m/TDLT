from PyQt6.QtWidgets import QMainWindow

from Chap5.Ex73.ui.MyMainWindow import Ui_MainWindow
from Chap5.Ex73.libs.My_Module import quadratic_equation


class MyMainWindowEx(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.setupSignalandSlot()

    def show_window(self):
        self.show()

    def setupSignalandSlot(self):
        self.pushButton.clicked.connect(self.calculate)

    def calculate(self):
        a = int(self.lineEdit_2.text())
        b = int(self.lineEdit_3.text())
        c = int(self.lineEdit_4.text())
        result = quadratic_equation(a, b, c)
        self.lineEdit.setText(str(result))