# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'setup_1.ui'
##
## Created by: Qt User Interface Compiler version 6.11.1
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QAbstractButton, QApplication, QDialog, QDialogButtonBox,
    QLabel, QLineEdit, QSizePolicy, QStackedWidget,
    QWidget)

class Ui_Dialog(object):
    def setupUi(self, Dialog):
        if not Dialog.objectName():
            Dialog.setObjectName(u"Dialog")
        Dialog.resize(350, 293)
        self.OK_Cancel_setup_buttonBox = QDialogButtonBox(Dialog)
        self.OK_Cancel_setup_buttonBox.setObjectName(u"OK_Cancel_setup_buttonBox")
        self.OK_Cancel_setup_buttonBox.setGeometry(QRect(130, 250, 211, 32))
        self.OK_Cancel_setup_buttonBox.setOrientation(Qt.Horizontal)
        self.OK_Cancel_setup_buttonBox.setStandardButtons(QDialogButtonBox.Cancel|QDialogButtonBox.Ok)
        self.Pin_name_setup_label = QLabel(Dialog)
        self.Pin_name_setup_label.setObjectName(u"Pin_name_setup_label")
        self.Pin_name_setup_label.setGeometry(QRect(40, 20, 91, 31))
        font = QFont()
        font.setPointSize(10)
        self.Pin_name_setup_label.setFont(font)
        self.Signal_Profile_setup_label = QLabel(Dialog)
        self.Signal_Profile_setup_label.setObjectName(u"Signal_Profile_setup_label")
        self.Signal_Profile_setup_label.setGeometry(QRect(40, 60, 111, 16))
        self.Signal_Profile_setup_label.setFont(font)
        self.stackedWidget = QStackedWidget(Dialog)
        self.stackedWidget.setObjectName(u"stackedWidget")
        self.stackedWidget.setGeometry(QRect(20, 100, 301, 111))
        self.Constant_page = QWidget()
        self.Constant_page.setObjectName(u"Constant_page")
        self.volt_unit_label = QLabel(self.Constant_page)
        self.volt_unit_label.setObjectName(u"volt_unit_label")
        self.volt_unit_label.setGeometry(QRect(260, 20, 21, 16))
        self.volt_unit_label_2 = QLabel(self.Constant_page)
        self.volt_unit_label_2.setObjectName(u"volt_unit_label_2")
        self.volt_unit_label_2.setGeometry(QRect(260, 60, 21, 16))
        self.Amplitude_lineEdit = QLineEdit(self.Constant_page)
        self.Amplitude_lineEdit.setObjectName(u"Amplitude_lineEdit")
        self.Amplitude_lineEdit.setGeometry(QRect(130, 10, 113, 31))
        self.Offset_label = QLabel(self.Constant_page)
        self.Offset_label.setObjectName(u"Offset_label")
        self.Offset_label.setGeometry(QRect(10, 60, 101, 16))
        self.Amplitude_label = QLabel(self.Constant_page)
        self.Amplitude_label.setObjectName(u"Amplitude_label")
        self.Amplitude_label.setGeometry(QRect(10, 20, 81, 16))
        self.Offset_lineEdit = QLineEdit(self.Constant_page)
        self.Offset_lineEdit.setObjectName(u"Offset_lineEdit")
        self.Offset_lineEdit.setGeometry(QRect(130, 50, 113, 31))
        self.stackedWidget.addWidget(self.Constant_page)
        self.Linear_page = QWidget()
        self.Linear_page.setObjectName(u"Linear_page")
        self.volt_unit_label_4 = QLabel(self.Linear_page)
        self.volt_unit_label_4.setObjectName(u"volt_unit_label_4")
        self.volt_unit_label_4.setGeometry(QRect(260, 60, 21, 16))
        self.Min_Amplitude_lineEdit = QLineEdit(self.Linear_page)
        self.Min_Amplitude_lineEdit.setObjectName(u"Min_Amplitude_lineEdit")
        self.Min_Amplitude_lineEdit.setGeometry(QRect(130, 10, 113, 31))
        self.Max_Amplitude_lineEdit = QLineEdit(self.Linear_page)
        self.Max_Amplitude_lineEdit.setObjectName(u"Max_Amplitude_lineEdit")
        self.Max_Amplitude_lineEdit.setGeometry(QRect(130, 50, 113, 31))
        self.Min_Amplitude_label = QLabel(self.Linear_page)
        self.Min_Amplitude_label.setObjectName(u"Min_Amplitude_label")
        self.Min_Amplitude_label.setGeometry(QRect(10, 20, 81, 16))
        self.Max_Amplitude_label = QLabel(self.Linear_page)
        self.Max_Amplitude_label.setObjectName(u"Max_Amplitude_label")
        self.Max_Amplitude_label.setGeometry(QRect(10, 60, 101, 16))
        self.volt_unit_label_3 = QLabel(self.Linear_page)
        self.volt_unit_label_3.setObjectName(u"volt_unit_label_3")
        self.volt_unit_label_3.setGeometry(QRect(260, 20, 21, 16))
        self.stackedWidget.addWidget(self.Linear_page)

        self.retranslateUi(Dialog)
        self.OK_Cancel_setup_buttonBox.accepted.connect(Dialog.accept)
        self.OK_Cancel_setup_buttonBox.rejected.connect(Dialog.reject)

        self.stackedWidget.setCurrentIndex(0)


        QMetaObject.connectSlotsByName(Dialog)
    # setupUi

    def retranslateUi(self, Dialog):
        Dialog.setWindowTitle(QCoreApplication.translate("Dialog", u"Dialog", None))
        self.Pin_name_setup_label.setText(QCoreApplication.translate("Dialog", u"Pin_Name", None))
        self.Signal_Profile_setup_label.setText(QCoreApplication.translate("Dialog", u"Profile", None))
        self.volt_unit_label.setText(QCoreApplication.translate("Dialog", u"V", None))
        self.volt_unit_label_2.setText(QCoreApplication.translate("Dialog", u"V", None))
        self.Offset_label.setText(QCoreApplication.translate("Dialog", u"Offset:", None))
        self.Amplitude_label.setText(QCoreApplication.translate("Dialog", u"Amplitude:", None))
        self.volt_unit_label_4.setText(QCoreApplication.translate("Dialog", u"V", None))
        self.Min_Amplitude_label.setText(QCoreApplication.translate("Dialog", u"Min Amplitude:", None))
        self.Max_Amplitude_label.setText(QCoreApplication.translate("Dialog", u"Max Amplitude:", None))
        self.volt_unit_label_3.setText(QCoreApplication.translate("Dialog", u"V", None))
    # retranslateUi

