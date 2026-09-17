from ui.BMIMainWindow import Ui_MainWindow
from libs.haw import haw


class BMIMainWindowEx(Ui_MainWindow):
    def __init__(self):
        self.MainWindow = None

    def setupUi(self, MainWindow):
        super().setupUi(MainWindow)
        self.MainWindow = MainWindow
        self.setupSignalandSlot()

    def show_window(self):
        if self.MainWindow is not None:
            self.MainWindow.show()

    def setupSignalandSlot(self):
        self.BMI.clicked.connect(self.invoke_bmi)

    def invoke_bmi(self):
        height_cm = float(self.Height.text())
        weight_kg = float(self.Weight.text())
        calc = haw(height_cm, weight_kg)
        bmi = calc.BMI()
        classify = haw.Classify(bmi)
        risk = haw.RiskOfDisease(bmi)

        self.BMI_result.setText(str(bmi))
        self.RiskOfDisease.setText(str(risk))
        self.Classify.setText((classify))

