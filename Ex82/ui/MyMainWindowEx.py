from PyQt6.QtWidgets import QMainWindow, QMessageBox

from Chap5.Ex82.ui.MyMainWindow import Ui_MainWindow
from Chap5.Ex82.libs.my_module import calc1, calc2
from libs.utils import call_close_app


class KWhMainWindowEx(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super().__init__()
        self.setupUi(self)

    def setupUi(self, MainWindow):
        super().setupUi(MainWindow)
        self.MainWindow = MainWindow
        self.setupSignalandSlot()

    def showWindow(self):
        self.show()
    def setupSignalandSlot(self):
        self.Calculate.clicked.connect(self.Calc_Price)
        self.Exit.clicked.connect(call_close_app)

    def Calc_Price(self):
            try:
                n = float(self.KWh.text())                
                if self.Household.isChecked():
                    price = calc1(n)
                elif self.prepaidcard.isChecked():
                    price = calc2(n)
                self.Price.setText(str(price) + " VND")            
            except Exception as Error:
                msgBox = QMessageBox()
                msgBox.setWindowTitle("Error")
                msgBox.setText("Error!! Please try again!!")
                msgBox.setIcon(QMessageBox.Icon.Critical)
                msgBox.exec()