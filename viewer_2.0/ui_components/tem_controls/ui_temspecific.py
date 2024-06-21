from PySide6.QtWidgets import (QGroupBox, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QButtonGroup, 
                               QRadioButton, QSpinBox, QPushButton, QCheckBox,
                               QDoubleSpinBox, QGraphicsEllipseItem, QGraphicsLineItem)
from ui_components.toggle_button import ToggleButton

class TEMDetector(QGroupBox):
    def __init__(self):
        super().__init__() # "Detector"
        self.initUI()

    def initUI(self):
        section1 = QVBoxLayout()

        self.hbox_mag = QHBoxLayout()
        magn_label = QLabel("Magnification:", self)
        dist_label = QLabel("Distance:", self)
        self.input_magnification = QLineEdit(self)
        self.input_magnification.setReadOnly(True)
        self.input_det_distance = QLineEdit(self)
        self.input_det_distance.setReadOnly(True)
        self.scale_checkbox = QCheckBox("scale", self)
        self.scale_checkbox.setChecked(False)
        self.hbox_mag.addWidget(magn_label, 1)
        self.hbox_mag.addWidget(self.input_magnification, 1)
        self.hbox_mag.addWidget(dist_label, 1)
        self.hbox_mag.addWidget(self.input_det_distance, 1)
        self.hbox_mag.addWidget(self.scale_checkbox, 1)
        section1.addLayout(self.hbox_mag)
        self.setLayout(section1)

class TEMStageCtrl(QGroupBox):
    def __init__(self):
        super().__init__() #"Stage Status / Quick Moves"
        self.initUI()

    def initUI(self):
        section1 = QVBoxLayout()

        self.hbox_rot = QHBoxLayout()
        rot_label = QLabel("Rotation Speed:", self)
        self.rb_speeds = QButtonGroup()
        self.rb_speed_05 = QRadioButton('0.5 deg/s', self)
        self.rb_speed_1 = QRadioButton('1 deg/s', self)
        self.rb_speed_2 = QRadioButton('2 deg/s', self)
        self.rb_speed_10 = QRadioButton('10 deg/s', self)
        self.rb_speeds.addButton(self.rb_speed_05, 3)
        self.rb_speeds.addButton(self.rb_speed_1, 2)
        self.rb_speeds.addButton(self.rb_speed_2, 1)
        self.rb_speeds.addButton(self.rb_speed_10, 0)
        self.rb_speeds.button(1).setChecked(True)
        self.hbox_rot.addWidget(rot_label, 1)
        section1.addLayout(self.hbox_rot)
        
        self.hbox_move = QHBoxLayout()
        move_label = QLabel("Stage Ctrl:", self)
        self.movestages = QButtonGroup()
        self.movex10ump = QPushButton('+10 µm', self)
        self.movex10umn = QPushButton('-10 µm', self)
        self.move10degp = QPushButton('+10 deg', self)
        self.move10degn = QPushButton('-10 deg', self)
        self.move0deg = QPushButton('0 deg', self)
        self.movestages.addButton(self.movex10ump, 2)
        self.movestages.addButton(self.movex10umn, -2)
        self.movestages.addButton(self.move10degp, 10)
        self.movestages.addButton(self.move10degn, -10)
        self.movestages.addButton(self.move0deg, 0)
        self.hbox_move.addWidget(move_label, 1)
        section1.addLayout(self.hbox_move)

        for i in self.rb_speeds.buttons():
            self.hbox_rot.addWidget(i, 1)
            # i.setEnabled(enables)
        for i in self.movestages.buttons():
            self.hbox_move.addWidget(i, 1)
            # i.setEnabled(enables)
        
        self.setLayout(section1)

class TEMTasks(QGroupBox):
    def __init__(self):
        super().__init__("")
        self.initUI()

    def initUI(self):
        section1 = QHBoxLayout()
        
        self.connecttem_button = ToggleButton('Connect to TEM', self)
        self.gettem_button = QPushButton("Get TEM status", self)
        self.gettem_checkbox = QCheckBox("recording", self)
        self.gettem_checkbox.setChecked(False)
        self.centering_button = ToggleButton("Click-on-Centering", self)
        self.centering_button.setEnabled(False) # not secured function
        self.rotation_button  = ToggleButton("Rotation", self) # Rotation/Record
        self.withwriter_checkbox = QCheckBox("with Writer", self)
        self.withwriter_checkbox.setChecked(False)
        self.autoreset_checkbox = QCheckBox("Auto reset", self)
        self.autoreset_checkbox.setChecked(True)
        # input_start_angle = QLabel("Start angle:", self) # current value
        self.input_start_angle = QDoubleSpinBox(self)
        self.input_start_angle.setMaximum(70)
        self.input_start_angle.setMinimum(-70)
        self.input_start_angle.setSuffix('°')
        self.input_start_angle.setDecimals(1)
        # self.input_start_angle.setValue("")
        self.input_start_angle.setReadOnly(True)
        # end_angle = QLabel("Target angle:", self)
        self.update_end_angle = QDoubleSpinBox(self)
        self.update_end_angle.setMaximum(71) # should be checked with the holder's threshold
        self.update_end_angle.setMinimum(-71)
        self.update_end_angle.setSuffix('°')
        self.update_end_angle.setDecimals(1)
        self.update_end_angle.setValue(65) # will be replaced with configuration file
        self.exit_button = QPushButton("Exit", self)

        section1.addWidget(self.connecttem_button)
        section1.addWidget(self.gettem_button)
        section1.addWidget(self.gettem_checkbox)
        section1.addWidget(self.centering_button)
        section1.addWidget(self.rotation_button)
        section1.addWidget(self.withwriter_checkbox)
        section1.addWidget(self.autoreset_checkbox)
        section1.addWidget(self.input_start_angle)
        section1.addWidget(self.update_end_angle)
        section1.addWidget(self.exit_button)
        
        self.setLayout(section1)