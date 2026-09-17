from UI.ui_GPA import Ui_MainWindow
from classes.courses import Course

class GPAMainWindowEx(Ui_MainWindow):
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
        self.pushButtonGPA.clicked.connect(self.invoke_gpa)

    def invoke_gpa(self):
        ongoing= float(self.lineEditOnGoing.text())
        midterm = float(self.lineEditMidterm.text())
        final = float(self.lineEditFinal.text())
        talent = float(self.lineEditTalent.text())
        percent_ongoing = float(self.lineEditOnGoingPercent.text())
        percent_midterm = float(self.lineEditMidtermPercent.text())
        percent_final = float(self.lineEditFinalPercent.text())
        percent_talent = float(self.lineEditTalentPercent.text())
        c=Course(ongoing, percent_ongoing, midterm, percent_midterm, final, percent_final, talent, percent_talent)
        gpa=c.calc_GPA()
        self.labelGPAResult.setText(str(gpa))