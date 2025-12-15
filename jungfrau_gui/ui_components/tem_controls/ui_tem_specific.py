from PySide6.QtWidgets import (QGroupBox, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QButtonGroup, 
                               QRadioButton, QPushButton, QCheckBox, QDoubleSpinBox, QSizePolicy, QComboBox,
                               QSpinBox, QWidget, QGridLayout)
from PySide6.QtGui import QFont, QTransform
from PySide6.QtCore import QTimer, Qt
from ..toggle_button import ToggleButton
from ..utils import create_horizontal_line_with_margin

from epoc import ConfigurationClient, auth_token, redis_host

from ... import globals
import pyqtgraph as pg
import numpy as np
from jungfrau_gui.ui_components.tem_controls.toolbox import tool
from jungfrau_gui.ui_components.tem_controls.toolbox import config as cfg_jf
import logging

try:
    from vispy import scene, app
    from vispy.color import get_colormap
    vispy = True
except ModuleNotFoundError:
    vispy = False
    pass

font_big = QFont("Arial", 11)
font_big.setBold(True)
font_small = QFont("Arial", 8)

class TEMDetector(QGroupBox):
    def __init__(self, parent):
        super().__init__() # "Detector"
        self.initUI()
        self.parent = parent

    def initUI(self):
        detector_section = QVBoxLayout()
        
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
        if globals.dev:
            self.calib_det_distance = QDoubleSpinBox(self)
            self.calib_det_distance.setReadOnly(True)
            self.calib_det_distance.setSuffix(' mm')
            self.calib_det_distance.setMaximum(2500)
            self.calib_det_distance.setDecimals(1)
            self.calib_det_distance.setValue(999)
            self.hbox_mag.addWidget(self.calib_det_distance, 1)
        self.hbox_mag.addWidget(self.scale_checkbox, 1)

        detector_section.addLayout(self.hbox_mag)

        if globals.dev:
            self.hbox_e_incoming = QHBoxLayout()
            self.calc_e_incoming_button = QPushButton("Calc Brightness on Detector/Sample", self)
            self.e_incoming_display = QLineEdit(self)
            self.e_incoming_display.setReadOnly(True)
            self.calc_e_incoming_button.setEnabled(False)
            self.hbox_e_incoming.addWidget(self.calc_e_incoming_button, 1)
            self.hbox_e_incoming.addWidget(self.e_incoming_display, 2)
            detector_section.addLayout(self.hbox_e_incoming)

        self.setLayout(detector_section)


class TEMStageCtrl(QGroupBox):
    def __init__(self):
        super().__init__() # "Stage Status / Quick Moves"
        if globals.dev and vispy:
            self.setTitle("Spot scatter plot")
        else:
            self.setTitle("X/Y stage plot")
        self.setCheckable(True)
        self.setChecked(False) #True)
        # Connect QGroupBox toggled signal to a custom slot
        self.toggled.connect(self.on_collapsed)
        self.images_kept = {}
        self.initUI()

    def initUI(self):
        cfg = ConfigurationClient(redis_host(), token=auth_token())

        stage_ctrl_section = QVBoxLayout()
        stage_ctrl_label = QLabel("Stage Control", self)
        stage_ctrl_label.setFont(font_big)
        stage_ctrl_section.addWidget(stage_ctrl_label)

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
        self.rb_speeds.button(cfg.rotation_speed_idx).setChecked(True)
        self.hbox_rot.addWidget(rot_label, 1)
        stage_ctrl_section.addSpacing(10)
        stage_ctrl_section.addLayout(self.hbox_rot)
        
        self.hbox_move = QHBoxLayout()
        move_label = QLabel("Fast movement:", self)
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
        if globals.dev:
            self.move55degn = QPushButton('-55 deg', self)
            self.movestages.addButton(self.move55degn, -5)
        self.hbox_move.addWidget(move_label, 1)
        stage_ctrl_section.addLayout(self.hbox_move)

        for i in self.rb_speeds.buttons():
            self.hbox_rot.addWidget(i, 1)
            i.setEnabled(False)

        for i in self.movestages.buttons():
            if globals.dev: i.setMaximumWidth(60)
            self.hbox_move.addWidget(i, 1)
            i.setEnabled(False)

        self.hbox_magmode = QHBoxLayout()
        mode_label = QLabel("Magnification Mode:", self)
        self.mag_modes = QButtonGroup()
        self.mode_lowmag = QRadioButton('Low MAG', self)
        self.mode_mag =    QRadioButton('MAG', self)
        self.mode_difmag = QRadioButton('Diff MAG', self)
        #self.contrast_checkbox = QCheckBox("fixed contrast", self)
        #self.contrast_checkbox.setChecked(False)
        self.mag_modes.addButton(self.mode_lowmag, 2)
        self.mag_modes.addButton(self.mode_mag, 0)
        self.mag_modes.addButton(self.mode_difmag, 4)
        self.mag_modes.button(0).setChecked(True)
        self.hbox_magmode.addWidget(mode_label, 1)
        stage_ctrl_section.addLayout(self.hbox_magmode)

        for i in self.mag_modes.buttons():
            self.hbox_magmode.addWidget(i, 1)
        #self.hbox_magmode.addWidget(self.contrast_checkbox, 1)

        self.hbox_extras = QHBoxLayout()
        self.blanking_button = ToggleButton("Blank beam", self)
        self.blanking_button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.blanking_button.setEnabled(False)
        self.hbox_extras.addWidget(self.blanking_button, 3)
        if globals.dev:
            self.screen_button = ToggleButton("Move Screen", self)
            self.screen_button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            self.screen_button.setEnabled(False)
            self.hbox_extras.addWidget(self.screen_button, 3)
            self.mapsnapshot_button = QPushButton("Snapshot", self)
            self.mapsnapshot_button.setEnabled(False)
            self.hbox_extras.addWidget(self.mapsnapshot_button, 3)
            self.spotchart_checkbox = QCheckBox("diff", self)
            self.spotchart_checkbox.setFont(font_small)
            self.hbox_extras.addWidget(self.spotchart_checkbox, 2)
            self.spotchart_checkbox.checkStateChanged.connect(self.toggle_spotchart)
            self.tilted_view_checkbox = QCheckBox("tilt", self)
            self.tilted_view_checkbox.setFont(font_small)
            self.tilted_view_checkbox.checkStateChanged.connect(self.toggle_tiltview)
            self.hbox_extras.addWidget(self.tilted_view_checkbox, 2)

            # self.image_kept_checkbox = QCheckBox("buffered", self)
            # self.image_kept_checkbox.setFont(font_small)
            # self.image_kept_checkbox.setEnabled(False)
            # self.image_kept_checkbox.checkStateChanged.connect(self.toggle_imagekept)
            # self.hbox_extras.addWidget(self.image_kept_checkbox, 2)

        stage_ctrl_section.addLayout(self.hbox_extras)
        
        self.hbox_gotopos = QHBoxLayout()
        gotopos_label = QLabel("Positions:", self)
        self.position_list = QComboBox(self)
        self.position_list.setEditable(False)
        self.addpos_button = QPushButton("Add", self)
        self.addpos_button.setEnabled(False)
        self.go_button = QPushButton("Go", self)
        self.go_button.setEnabled(False)
        # self.goxyz_button = QPushButton("Go XYZ", self)
        self.hbox_gotopos.addWidget(gotopos_label, 1)
        if globals.dev:
            # self.loadsave_button = QPushButton("Load/Save", self)
            # self.loadsave_button.setEnabled(False)
            self.hbox_gotopos.addWidget(self.position_list, 6)
            self.hbox_gotopos.addWidget(self.addpos_button, 1)
            self.hbox_gotopos.addWidget(self.go_button, 1)
            # self.hbox_gotopos.addWidget(self.loadsave_button, 1)
        else:
            self.hbox_gotopos.addWidget(self.position_list, 7)
            self.hbox_gotopos.addWidget(self.addpos_button, 1)
            self.hbox_gotopos.addWidget(self.go_button, 1)
        stage_ctrl_section.addLayout(self.hbox_gotopos)

        # 1) Create a container widget to hold the plot
        self.plot_container = QWidget()
        self.plot_layout = QVBoxLayout(self.plot_container)

        # 2) Create the PlotWidget
        self.grid_plot = pg.PlotWidget()
        self.grid_plot.getViewBox().invertX(True)
        self.grid_plot.getViewBox().invertY(True)
        self.plot_layout.addWidget(self.grid_plot)

        # 3) Access the plotItem if needed
        self.gridarea = self.grid_plot.plotItem

        radius1 = globals.grid_circle_radius['outer']
        x = radius1 * np.cos(np.linspace(0, 2*np.pi, 100))
        y = radius1 * np.sin(np.linspace(0, 2*np.pi, 100))
        self.gridarea.addItem(pg.PlotCurveItem(x=x, y=y, pen=pg.mkPen('darkGray')))

        self.radius2 = globals.grid_circle_radius['inner']
        x = self.radius2 * np.cos(np.linspace(0, 2*np.pi, 100))
        y = self.radius2 * np.sin(np.linspace(0, 2*np.pi, 100))
        self.gridarea.addItem(pg.PlotCurveItem(x=x, y=y, pen=pg.mkPen('yellow')))

        # SetZValue = 
        # undef: arrows, points, labels
        # -1: Snapshots
        # -2: Diff-map with tilt
        # -3: low-mag map with tilt
        # -4: Diff-map
        # -5: low-mag map

        # lowmag-map
        tr = QTransform()
        tr.scale(globals.grid_lowmag_scale, globals.grid_lowmag_scale)

        self.mapatlasItem = pg.ImageItem()
        self.gridarea.addItem(self.mapatlasItem)
        self.mapatlasItem.setTransform(tr)
        self.mapatlasItem.setZValue(-5) # bottom layer
        self.lowmagimage = np.zeros((int(self.radius2*2//globals.grid_lowmag_scale), int(self.radius2*2//globals.grid_lowmag_scale)))
        self.mapatlasItem.setImage(self.lowmagimage)

        # # lowmag-map with tilt
        self.mapatlasItem_tilted = pg.ImageItem()
        self.gridarea.addItem(self.mapatlasItem_tilted)
        self.mapatlasItem_tilted.setTransform(tr)
        self.mapatlasItem_tilted.setZValue(-3)
        self.lowmagimage_tilted = np.zeros_like(self.lowmagimage)
        self.mapatlasItem_tilted.setImage(self.lowmagimage_tilted)

        # diff-map
        tr = QTransform()
        tr.scale(globals.grid_resolution, globals.grid_resolution)

        self.spotchartItem = pg.ImageItem()
        self.gridarea.addItem(self.spotchartItem)
        self.spotchartItem.setColorMap('inferno')
        self.spotchartItem.setTransform(tr)
        self.spotchartItem.setPos(-self.radius2, -self.radius2)
        self.spotchartItem.setZValue(-4) # 2nd bottom layer
        self.grayimage = np.zeros((self.radius2*2//globals.grid_resolution, self.radius2*2//globals.grid_resolution))
        self.spotchartItem.hide()

        # # diff-map with tilt
        self.spotchartItem_tilted = pg.ImageItem()
        self.gridarea.addItem(self.spotchartItem_tilted)
        self.spotchartItem_tilted.setColorMap('inferno')
        self.spotchartItem_tilted.setTransform(tr)
        self.spotchartItem_tilted.setPos(-self.radius2, -self.radius2)
        self.spotchartItem_tilted.setZValue(-2)
        self.grayimage_tilted = np.zeros_like(self.grayimage)
        self.spotchartItem_tilted.setImage(self.grayimage_tilted)
        self.spotchartItem_tilted.hide()        

        self.grid_plot.setAspectLocked()
        self.grid_plot.showGrid(x=True, y=True)

        # Add the plot_container (with its layout/plot) to the GroupBox layout
        stage_ctrl_section.addWidget(self.plot_container)

        if vispy: 
            self.plot3d_container = QWidget()
            self.plot3d_container.setWindowTitle("3d plotter")
            self.plot3d_container.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
            self.plot3d_layout = QVBoxLayout(self.plot3d_container)
            # "export QT_XCB_GL_INTEGRATION=xcb_egl" is necessary to avoid an error!
            self.canvas = scene.SceneCanvas(size=(500, 500), show=True) # keys='interactive',

            self.view = self.canvas.central_widget.add_view()
            self.view.camera = 'turntable'
            self.view.camera.fov = 45
            self.view.camera.distance = 2 # 500

            self.scatter = scene.visuals.Markers(parent=self.view.scene)
            self.scatter.set_gl_state('translucent', depth_test=True)

            xyz = np.random.normal(0, 0.005, size=(10, 3)) # origin
            self.scatter.set_data(xyz, edge_color=None, size=10)
            self.plot3d_layout.addWidget(self.canvas.native)

        self.setLayout(stage_ctrl_section)

    def on_collapsed(self, checked: bool):
        """
        Called whenever the QGroupBox is toggled.
        If 'checked' is False, collapse (hide) the plot container.
        If 'checked' is True, show it again.
        """
        if vispy and globals.dev:
            self.plot3d_container.setVisible(checked)
        else:
            self.plot_container.setVisible(checked)

    def toggle_spotchart(self):
        if self.spotchartItem.isVisible():
            self.spotchartItem.hide()
        else:
            self.spotchartItem.show()
        if self.spotchartItem_tilted.isVisible():
            self.spotchartItem_tilted.hide()
        else:
            self.spotchartItem_tilted.show()

    def toggle_tiltview(self):
        if self.mapatlasItem_tilted.isVisible():
            self.mapatlasItem_tilted.hide()
            self.mapatlasItem.show()
        else:
            self.mapatlasItem_tilted.show()
            self.mapatlasItem.hide()
        if self.spotchartItem_tilted.isVisible():
            self.spotchartItem_tilted.hide()
            self.spotchartItem.show()
        else:
            self.spotchartItem_tilted.show()
            self.spotchartItem.hide()

class TEMTasks(QGroupBox):
    def __init__(self, parent):
        super().__init__("")
        self.parent = parent
        self.initUI()

    def initUI(self):
        tasks_section = QVBoxLayout()
        
        CTN_group = QVBoxLayout()
        CTN_section = QHBoxLayout()
        CTN_label = QLabel("Connection to TEM", self)
        CTN_label.setFont(font_big)
        self.connecttem_button = ToggleButton('Check TEM Connection', self)
        self.connecttem_button.setEnabled(True)
        self.polling_frequency = QSpinBox(self)
        self.polling_frequency.setMinimum(globals.min_polling_frequency)
        self.polling_frequency.setMaximum(globals.max_polling_frequency)
        self.polling_frequency.setValue(globals.default_polling_frequency)
        self.polling_frequency.setSingleStep(100)
        self.polling_frequency.setPrefix("Polling Freq: ")
        self.polling_frequency.setSuffix("ms")
        self.connecttem_button.setEnabled(True)
        self.centering_checkbox = QCheckBox("Click-on-Centering", self)
        self.centering_checkbox.setChecked(False)
        
        BEAM_group = QVBoxLayout()
        BEAM_label = QLabel("Beam Sweep & Focus", self)
        BEAM_label.setFont(font_big)
        self.btnGaussianFit = ToggleButton("Gaussian Fit", self)
        self.btnGaussianFit.setEnabled(False)
        if globals.dev:
            self.beamAutofocus = ToggleButton('Autofocus', self)
            self.beamAutofocus.setEnabled(False)
            self.fast_autofocus_checkbox = QCheckBox("fast", self)
            self.fast_autofocus_checkbox.setChecked(True)

        self.popup_checkbox = self.parent.checkbox
        self.plotDialog = self.parent.plotDialog

        ROT_group = QVBoxLayout()
        ROT_label = QLabel("Rotation/Record", self)
        ROT_label.setFont(font_big)

        ROT_section_1= QHBoxLayout()

        self.rotation_button  = ToggleButton("Rotation", self) # Rotation/Record
        self.withwriter_checkbox = QCheckBox("with Writer", self)
        self.withwriter_checkbox.setChecked(True)
        
        self.autoreset_checkbox = QCheckBox("Auto reset", self)
        self.autoreset_checkbox.setChecked(False)

        ROT_section_2= QHBoxLayout()

        INPUT_layout = QHBoxLayout()
        input_start_angle_lb = QLabel("Start angle:", self) # current value
        self.input_start_angle = QDoubleSpinBox(self)
        self.input_start_angle.setMaximum(globals.max_stage_tilt)
        self.input_start_angle.setMinimum(-globals.max_stage_tilt)
        self.input_start_angle.setSuffix('°')
        self.input_start_angle.setDecimals(1)
        # self.input_start_angle.setValue("")
        self.input_start_angle.setReadOnly(True)

        INPUT_layout.addSpacing(10)
        INPUT_layout.addWidget(input_start_angle_lb)
        INPUT_layout.addWidget(self.input_start_angle)

        END_layout = QHBoxLayout()
        end_angle = QLabel("Target angle:", self)
        self.update_end_angle = QDoubleSpinBox(self)
        self.update_end_angle.setMaximum(globals.max_stage_tilt)
        self.update_end_angle.setMinimum(-globals.max_stage_tilt)
        self.update_end_angle.setSuffix('°')
        self.update_end_angle.setDecimals(1)
        self.update_end_angle.setValue(globals.default_roation_end)
        if globals.dev:
            self.mirror_angles_checkbox = QCheckBox("mirror", self)
            self.mirror_angles_checkbox.setChecked(False)

        END_layout.addWidget(end_angle)
        END_layout.addWidget(self.update_end_angle)

        CTN_group.addWidget(CTN_label)
        CTN_section.addWidget(self.connecttem_button)
        CTN_section.addWidget(self.polling_frequency)
        CTN_section.addWidget(self.centering_checkbox)
        CTN_group.addLayout(CTN_section)
        tasks_section.addLayout(CTN_group)

        tasks_section.addWidget(create_horizontal_line_with_margin(20))

        Voltage_layout = QHBoxLayout()
        Voltage_layout.addWidget(self.parent.label_voltage, 2)  
        Voltage_layout.addWidget(self.parent.voltage_spBx,  2)

        BEAM_group.addWidget(BEAM_label)
        BEAM_group.addLayout(Voltage_layout)
        BEAM_group.addSpacing(10)
        layout_Beam_buttons = QGridLayout()
        if globals.dev:
            layout_Beam_buttons.addWidget(self.btnGaussianFit           ,0,0,1,4)
            layout_Beam_buttons.addWidget(self.beamAutofocus            ,0,4,1,4)
            layout_Beam_buttons.addWidget(self.fast_autofocus_checkbox  ,0,8,1,1)
        else:
            layout_Beam_buttons.addWidget(self.btnGaussianFit           ,0,0)


        BEAM_group.addLayout(layout_Beam_buttons)
        BEAM_group.addWidget(self.popup_checkbox)
        
        BeamFocus_layout = QGridLayout()

        BeamFocus_layout.addWidget(self.parent.label_Xo          ,0,0)
        BeamFocus_layout.addWidget(self.parent.beam_center_x,     0,1)
        BeamFocus_layout.addWidget(self.parent.label_Yo          ,0,2)
        BeamFocus_layout.addWidget(self.parent.beam_center_y,     0,3)
        """
        BeamFocus_layout.addWidget(self.parent.label_gauss_height,1,0)  
        BeamFocus_layout.addWidget(self.parent.gauss_height_spBx, 1,1)
        BeamFocus_layout.addWidget(self.parent.label_rot_angle,   1,2)  
        BeamFocus_layout.addWidget(self.parent.angle_spBx,        1,3)

        BeamFocus_layout.addWidget(self.parent.label_sigma_x,     2,0)  
        BeamFocus_layout.addWidget(self.parent.sigma_x_spBx,      2,1)         
        BeamFocus_layout.addWidget(self.parent.label_sigma_y,     2,2)  
        BeamFocus_layout.addWidget(self.parent.sigma_y_spBx,      2,3)         
        """
        BeamFocus_layout.addWidget(self.parent.label_sigma_x,     1,0)  
        BeamFocus_layout.addWidget(self.parent.sigma_x_spBx,      1,1)         
        BeamFocus_layout.addWidget(self.parent.label_sigma_y,     1,2)  
        BeamFocus_layout.addWidget(self.parent.sigma_y_spBx,      1,3)
        
        BEAM_group.addLayout(BeamFocus_layout)

        tasks_section.addLayout(BEAM_group)

        tasks_section.addWidget(create_horizontal_line_with_margin(20))

        ROT_group.addWidget(ROT_label)
        ROT_section_1.addWidget(self.rotation_button,     2)
        ROT_section_1.addWidget(self.withwriter_checkbox, 1)

        ROT_section_1.addWidget(self.autoreset_checkbox,  1)
        ROT_group.addSpacing(10)
        ROT_group.addLayout(ROT_section_1)
        ROT_section_2.addLayout(INPUT_layout)
        if globals.dev:
            END_layout.addWidget(self.mirror_angles_checkbox)
        else:
            ROT_section_2.addSpacing(30)
        ROT_section_2.addLayout(END_layout)
        ROT_group.addLayout(ROT_section_2)
        tasks_section.addLayout(ROT_group)
        
        self.setLayout(tasks_section)
