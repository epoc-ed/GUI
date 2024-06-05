from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QButtonGroup, 
                               QRadioButton, QSpinBox, QPushButton, QCheckBox,
                               QDoubleSpinBox, QGraphicsEllipseItem, QGraphicsLineItem)
from PySide6.QtCore import QRectF

from toolbox.tool import *
import pyqtgraph as pg
import toolbox.config as cfg_jf
class ToggleButton(QPushButton):
    def __init__(self, label, window):
        super().__init__(label, window)
        self.started = False

class Ui_TEMctrl(object):
    def setupUI_temctrl(self, main_window):
        self.scale = None
        self.hbox_mag = QHBoxLayout()
        magn_label = QLabel("Magnification:", self)
        dist_label = QLabel("Distance:", self)
        self.input_magnification = QLineEdit(self)
        # self.input_magnification.setSuffix(" x")
        self.input_magnification.setReadOnly(True)
        self.input_det_distance = QLineEdit(self)
        # self.input_det_distance.setSuffix(" cm")
        self.input_det_distance.setReadOnly(True)
        self.scale_checkbox = QCheckBox("scale", self)
        self.scale_checkbox.setChecked(False)
        self.hbox_mag.addWidget(magn_label, 1)
        self.hbox_mag.addWidget(self.input_magnification, 1)
        self.hbox_mag.addWidget(dist_label, 1)
        self.hbox_mag.addWidget(self.input_det_distance, 1)
        self.hbox_mag.addWidget(self.scale_checkbox, 1)
        
        self.hbox_rot = QHBoxLayout()
        rot_label = QLabel("Rotation Speed:", self)
        self.rb_speeds = QButtonGroup()
        self.rb_speed_05 = QRadioButton('0.5 deg/s', self)
        self.rb_speed_1 = QRadioButton('1 deg/s', self)
        self.rb_speed_2 = QRadioButton('2 deg/s', self)
        self.rb_speed_10 = QRadioButton('10 deg/s', self)
        self.rb_speeds.addButton(self.rb_speed_05, 3)
        self.rb_speeds.addButton(self.rb_speed_1, 1)
        self.rb_speeds.addButton(self.rb_speed_2, 2)
        self.rb_speeds.addButton(self.rb_speed_10, 0)
        self.rb_speeds.button(1).setChecked(True)
        # self.rb_speeds.buttonClicked.connect(self.toggle_rb_speeds)
        self.hbox_rot.addWidget(rot_label, 1)

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
        # self.movex10ump.clicked.connect(lambda: self.control.send.emit("stage.SetXRel(10000)"))
        # self.movex10umn.clicked.connect(lambda: self.control.send.emit("stage.SetXRel(-10000)"))
        # self.move10degp.clicked.connect(lambda: self.control.send.emit("stage.SetTXRel(10)"))
        # self.move10degn.clicked.connect(lambda: self.control.send.emit("stage.SetTXRel(-10)"))
        # self.move0deg.clicked.connect(lambda: self.control.send.emit("stage.SetTiltXAngle(0)"))
        self.hbox_move.addWidget(move_label, 1)

        self.exit_button = QPushButton("Exit", self)
        self.connecttem_button = ToggleButton('Connect to TEM', self)
        self.gettem_button = QPushButton("Get TEM status", self)
        self.gettem_checkbox = QCheckBox("recording", self)
        self.gettem_checkbox.setChecked(False)
        self.centering_button = ToggleButton("Click-on-Centering", self)
        self.rotation_button = ToggleButton("Rotation/Record", self)
        input_start_angle = QLabel("Start angle:", self) # current value
        self.input_start_angle = QDoubleSpinBox(self)
        self.input_start_angle.setMaximum(70)
        self.input_start_angle.setMinimum(-70)
        self.input_start_angle.setSuffix('°')
        self.input_start_angle.setDecimals(1)
        # self.input_start_angle.setValue("")
        self.input_start_angle.setReadOnly(True)
        end_angle = QLabel("Target angle:", self)
        self.update_end_angle = QDoubleSpinBox(self)
        self.update_end_angle.setMaximum(70)
        self.update_end_angle.setMinimum(-70)
        self.update_end_angle.setSuffix('°')
        self.update_end_angle.setDecimals(1)
        self.update_end_angle.setValue(65) # will be replaced with configuration file
        stagectrl_layout = QHBoxLayout()
        stagectrl_layout.addWidget(self.centering_button)
        stagectrl_layout.addWidget(self.rotation_button)
        stagectrl_layout.addWidget(self.input_start_angle)
        stagectrl_layout.addWidget(self.update_end_angle)
        # self.gettem_button.clicked.connect(self.do_exit)
        gettem_layout = QHBoxLayout()
        gettem_layout.addWidget(self.gettem_button)
        gettem_layout.addWidget(self.gettem_checkbox)
        self.bottom_layout = QHBoxLayout()
        self.bottom_layout.addWidget(self.connecttem_button)
        self.bottom_layout.addLayout(gettem_layout)
        # self.bottom_layout.addWidget(self.centering_button)
        self.bottom_layout.addLayout(stagectrl_layout)
        self.bottom_layout.addWidget(self.exit_button)

        self.focus_layout = QHBoxLayout()
        self.btnBeamFocus = ToggleButton("Beam Gaussian Fit", self)
        self.btnBeamSweep = QPushButton('Start Focus-sweeping', self)
        self.focus_layout.addWidget(self.btnBeamFocus)
        self.focus_layout.addWidget(self.btnBeamSweep)
        
        self.writer_for_rotation = QCheckBox("Write during rotation", self)
        self.writer_for_rotation.setChecked(False) #True
        
        self.index_layout = QHBoxLayout()
        xds_label = QLabel("XDS:", self)
        dials_label = QLabel("DIALS:", self)
        self.input_index_xds = QLineEdit(self)
        self.input_index_xds.setReadOnly(True)
        self.input_index_dials = QLineEdit(self)
        self.input_index_dials.setReadOnly(True)
        self.index_layout.addWidget(xds_label, 1)
        self.index_layout.addWidget(self.input_index_xds, 3)
        self.index_layout.addWidget(dials_label, 1)
        self.index_layout.addWidget(self.input_index_dials, 3)
        
    def setupUI_temctrl_ready(self, main_window, enables=True):
        for i in self.rb_speeds.buttons():
            self.hbox_rot.addWidget(i, 1)
            i.setEnabled(enables)
        for i in self.movestages.buttons():
            self.hbox_move.addWidget(i, 1)
            i.setEnabled(enables)
        self.scale_checkbox.setEnabled(enables)
        self.gettem_button.setEnabled(enables)
        self.gettem_checkbox.setEnabled(enables)
        self.centering_button.setEnabled(False) #enables)
        self.update_end_angle.setEnabled(enables)
        self.rotation_button.setEnabled(enables)
        self.input_start_angle.setEnabled(enables)
        self.update_end_angle.setEnabled(enables)
        self.btnBeamSweep.setEnabled(enables)

    def drawscale_overlay(self, main_window, xo=0, yo=0, l_draw=1, pixel=0.075):
        if self.scale != None:
            self.plot.removeItem(self.scale)
        if self.scale_checkbox.isChecked():
            if self.control.tem_status["eos.GetFunctionMode"][0] == 4:
                detector_distance = self.control.tem_status["eos.GetMagValue"][2] ## with unit
                detector_distance = cfg_jf.lookup(cfg_jf.lut.distance, detector_distance, 'displayed', 'calibrated')
                radius_in_px = d2radius_in_px(d=l_draw, camlen=detector_distance)
                self.scale = QGraphicsEllipseItem(QRectF(xo-radius_in_px, yo-radius_in_px, radius_in_px*2, radius_in_px*2))
            else:
                magnification = self.control.tem_status["eos.GetMagValue"][2] ## with unit
                magnification = cfg_jf.lookup(cfg_jf.lut.magnification, magnification, 'displayed', 'calibrated')
                scale_in_px = l_draw * 1e-3 * magnification / pixel
                self.scale = QGraphicsLineItem(xo-scale_in_px/2, yo, xo+scale_in_px/2, yo)
            self.scale.setPen(pg.mkPen('w', width=2))
            self.plot.addItem(self.scale)            
        
#     def generate_h5_master(self, formatted_filename_original_h5):
#         logging.info("Generating HDF5 master file for XDS analysis...")
#         with h5py.File(formatted_filename_original_h5, 'r') as f:
#             data_shape = f['entry/data/data_000001'].shape

#         external_link = h5py.ExternalLink(
#             filename = formatted_filename_original_h5,
#             path = 'entry/data/data_000001'
#         )
#         # output = os.path.basename(args.path_input)[:-24] + '_master.h5'
#         output = formatted_filename_original_h5[:-24]  + '_master.h5'
#         with h5py.File(output, 'w') as f:
#             f['entry/data/data_000001'] = external_link
#             f.create_dataset('entry/instrument/detector/detectorSpecific/nimages', data = data_shape[0], dtype='uint64')
#             f.create_dataset('entry/instrument/detector/detectorSpecific/pixel_mask', data = np.zeros((data_shape[1], data_shape[2]), dtype='uint32')) ## 514, 1030, 512, 1024
#             f.create_dataset('entry/instrument/detector/detectorSpecific/x_pixels_in_detector', data = data_shape[1], dtype='uint64') # 512
#             f.create_dataset('entry/instrument/detector/detectorSpecific/y_pixels_in_detector', data = data_shape[2], dtype='uint64') # 1030

#         print('HDF5 Master file is ready at ', output)
        