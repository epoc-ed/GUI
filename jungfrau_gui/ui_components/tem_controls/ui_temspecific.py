from PySide6.QtWidgets import (QGroupBox, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QButtonGroup, 
                               QRadioButton, QSpinBox, QPushButton, QCheckBox,
                               QDoubleSpinBox, QGraphicsEllipseItem, QGraphicsLineItem,
                               QGraphicsRectItem, QSizePolicy)
from ...ui_components.toggle_button import ToggleButton
from ...ui_components.utils import create_horizontal_line_with_margin

class TEMDetector(QGroupBox):
    def __init__(self):
        super().__init__() # "Detector"
        self.initUI()

    def initUI(self):
        detector_section = QVBoxLayout()
        
        self.hbox_mag = QVBoxLayout()
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

        detector_section.addLayout(self.hbox_mag)
        self.setLayout(detector_section)

class TEMStageCtrl(QGroupBox):
    def __init__(self):
        super().__init__() #"Stage Status / Quick Moves"
        self.initUI()

    def initUI(self):
        stage_ctrl_section = QVBoxLayout()

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
        self.rb_speeds.button(2).setChecked(True)
        self.hbox_rot.addWidget(rot_label, 1)
        stage_ctrl_section.addLayout(self.hbox_rot)
        
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
        stage_ctrl_section.addLayout(self.hbox_move)

        for i in self.rb_speeds.buttons():
            self.hbox_rot.addWidget(i, 1)
            # i.setEnabled(enables)
            """ ************** """
            i.setEnabled(True)
            """ ************** """
        for i in self.movestages.buttons():
            self.hbox_move.addWidget(i, 1)
            # i.setEnabled(enables)
            """ ************** """
            i.setEnabled(True)
            """ ************** """
        
        self.setLayout(stage_ctrl_section)

class TEMTasks(QGroupBox):
    def __init__(self, parent):
        super().__init__("")
        self.parent = parent
        self.initUI()

    def initUI(self):
        tasks_section = QVBoxLayout()
        
        CTN_group = QVBoxLayout()
        CTN_section = QHBoxLayout()
        CTN_label = QLabel("Connection", self)
        self.connecttem_button = ToggleButton('Connect to TEM', self)
        self.connecttem_button.setEnabled(False)
        self.gettem_button = QPushButton("Get TEM status", self)
        self.gettem_checkbox = QCheckBox("recording", self)
        """ #################### """
        # self.gettem_button.setEnabled(True)
        # self.gettem_checkbox.setChecked(True) #False
        """ #################### """
        self.centering_button = ToggleButton("Click-on-Centering", self)
        self.centering_button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.centering_button.setEnabled(False) # not secured function
        
        BEAM_group = QVBoxLayout()
        BEAM_label = QLabel("Beam Sweep & Focus", self)

        self.beamAutofocus = ToggleButton('Beam Autofocus', self)
        self.beamAutofocus.setEnabled(False) # set to False for the "testing" version
        self.popup_checkbox = self.parent.checkbox
        self.plotDialog = self.parent.plotDialog

        ROT_group = QVBoxLayout()
        ROT_label = QLabel("Rotation & Stage Control", self)

        ROT_section_1= QHBoxLayout()

        self.rotation_button  = ToggleButton("Rotation", self) # Rotation/Record
        self.withwriter_checkbox = QCheckBox("with Writer", self)
        self.withwriter_checkbox.setChecked(False)
        self.autoreset_checkbox = QCheckBox("Auto reset", self)
        self.autoreset_checkbox.setChecked(False)

        ROT_section_2= QVBoxLayout()

        INPUT_layout = QHBoxLayout()
        input_start_angle_lb = QLabel("Start angle:", self) # current value
        self.input_start_angle = QDoubleSpinBox(self)
        self.input_start_angle.setMaximum(70)
        self.input_start_angle.setMinimum(-70)
        self.input_start_angle.setSuffix('°')
        self.input_start_angle.setDecimals(1)
        # self.input_start_angle.setValue("")
        self.input_start_angle.setReadOnly(True)

        INPUT_layout.addWidget(input_start_angle_lb)
        INPUT_layout.addWidget(self.input_start_angle)

        END_layout = QHBoxLayout()
        end_angle = QLabel("Target angle:", self)
        self.update_end_angle = QDoubleSpinBox(self)
        self.update_end_angle.setMaximum(71) # should be checked with the holder's threshold
        self.update_end_angle.setMinimum(-71)
        self.update_end_angle.setSuffix('°')
        self.update_end_angle.setDecimals(1)
        self.update_end_angle.setValue(65) # will be replaced with configuration file

        END_layout.addWidget(end_angle)
        END_layout.addWidget(self.update_end_angle)

        """ self.exit_button = QPushButton("Exit", self) """

        CTN_group.addWidget(CTN_label)
        CTN_section.addWidget(self.connecttem_button)
        CTN_section.addWidget(self.gettem_button)
        CTN_section.addWidget(self.gettem_checkbox)
        CTN_group.addLayout(CTN_section)
        CTN_group.addWidget(self.centering_button)
        tasks_section.addLayout(CTN_group)

        tasks_section.addWidget(create_horizontal_line_with_margin(50))

        BEAM_group.addWidget(BEAM_label)
        BEAM_group.addWidget(self.beamAutofocus)
        BEAM_group.addWidget(self.popup_checkbox)
        
        
        BeamFocus_layout = QVBoxLayout()
        """ REMOVE ? """
        gauss_H_layout = QHBoxLayout()
        gauss_H_layout.addWidget(self.parent.label_gauss_height)  
        gauss_H_layout.addWidget(self.parent.gauss_height_spBx)
        BeamFocus_layout.addLayout(gauss_H_layout)
        sigma_x_layout = QHBoxLayout()
        sigma_x_layout.addWidget(self.parent.label_sigma_x)  
        sigma_x_layout.addWidget(self.parent.sigma_x_spBx)         
        BeamFocus_layout.addLayout(sigma_x_layout)
        sigma_y_layout = QHBoxLayout()
        sigma_y_layout.addWidget(self.parent.label_sigma_y)  
        sigma_y_layout.addWidget(self.parent.sigma_y_spBx)         
        BeamFocus_layout.addLayout(sigma_y_layout)        
        rot_angle_layout = QHBoxLayout()
        rot_angle_layout.addWidget(self.parent.label_rot_angle)  
        rot_angle_layout.addWidget(self.parent.angle_spBx)         
        BeamFocus_layout.addLayout(rot_angle_layout)
        """ ********** """
        BEAM_group.addLayout(BeamFocus_layout)

        tasks_section.addLayout(BEAM_group)

        tasks_section.addWidget(create_horizontal_line_with_margin(50))

        ROT_group.addWidget(ROT_label)
        ROT_section_1.addWidget(self.rotation_button)
        ROT_section_1.addWidget(self.withwriter_checkbox)
        ROT_section_1.addWidget(self.autoreset_checkbox)
        ROT_group.addLayout(ROT_section_1)
        ROT_section_2.addLayout(INPUT_layout)
        ROT_section_2.addLayout(END_layout)
        ROT_group.addLayout(ROT_section_2)
        tasks_section.addLayout(ROT_group)

        # tasks_section.addWidget(self.input_start_angle)
        # tasks_section.addWidget(self.update_end_angle)
        """ tasks_section.addWidget(self.exit_button) """
        
        self.setLayout(tasks_section)
