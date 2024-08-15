from PySide6.QtWidgets import (QGroupBox, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QButtonGroup, 
                               QRadioButton, QSpinBox, QPushButton, QCheckBox,
                               QDoubleSpinBox, QGraphicsEllipseItem, QGraphicsLineItem)
from PySide6.QtCore import QRectF, QObject
from PySide6.QtNetwork import QAbstractSocket # QTcpSocket, 
import pyqtgraph as pg
# from ui_components.toggle_button import ToggleButton
from ...ui_components.tem_controls.toolbox.tool import *
from ...ui_components.tem_controls.toolbox import config as cfg_jf
from ...ui_components.tem_controls.task.control_worker import *
# from reuss import config as cfg
from epoc import ConfigurationClient, auth_token, redis_host
import json
import os

from .plot_dialog_bis import PlotDialog

class TEMAction(QObject):
    """
    The 'TEMAction' object integrates the information from the detector/viewer and the TEM to be communicated each other.
    """    
    def __init__(self, parent, grandparent):
        super().__init__()
        self.parent = grandparent # ApplicationWindow in ui_main_window
        self.tem_controls = parent
        self.visualization_panel = self.parent.visualization_panel
        self.file_operations = self.parent.file_operations
        self.tem_detector = self.visualization_panel.tem_detector
        self.tem_stagectrl = self.tem_controls.tem_stagectrl
        self.tem_tasks = self.tem_controls.tem_tasks
        self.temtools = TEMTools(self)
        self.control = ControlWorker(self)
        self.version =  self.parent.version #self.parent.version

        # self.tem_tasks.beamAutofocus.setEnabled(True)
        
        # initialization
        self.scale = None
        self.formatted_filename = ''
        cfg = ConfigurationClient(redis_host(), token=auth_token())
        self.beamcenter = cfg.beam_center
        self.xds_template_filepath = cfg_jf.path.xds
        self.datasaving_filepath = str(cfg_jf.path.data)
        
        # connect buttons with tem-functions
        self.tem_tasks.connecttem_button.clicked.connect(self.toggle_connectTEM)
        self.control.tem_socket_status.connect(self.on_sockstatus_change)
        self.control.updated.connect(self.on_tem_update)
        self.tem_tasks.gettem_button.clicked.connect(self.callGetInfoTask)
        # self.tem_tasks.centering_button.clicked.connect(self.toggle_centering)
        self.tem_tasks.rotation_button.clicked.connect(self.toggle_rotation)    

        self.tem_tasks.beamAutofocus.clicked.connect(self.toggle_beamAutofocus)

        self.tem_stagectrl.rb_speeds.buttonClicked.connect(self.toggle_rb_speeds)
        self.tem_stagectrl.movex10ump.clicked.connect(lambda: self.control.send.emit("stage.SetXRel(10000)"))
        self.tem_stagectrl.movex10umn.clicked.connect(lambda: self.control.send.emit("stage.SetXRel(-10000)"))
        self.tem_stagectrl.move10degp.clicked.connect(
                    lambda: self.control.send.emit(self.control.with_max_speed("stage.SetTXRel(10)")))
        self.tem_stagectrl.move10degn.clicked.connect(
                    lambda: self.control.send.emit(self.control.with_max_speed("stage.SetTXRel(-10)")))
        self.tem_stagectrl.move0deg.clicked.connect(
                    lambda: self.control.send.emit(self.control.with_max_speed("stage.SetTiltXAngle(0)")))

    def set_configuration(self):
        self.file_operations.outPath_input.setText(self.datasaving_filepath)
        self.file_operations.h5_folder_name = self.datasaving_filepath
        self.file_operations.fname_input.setText(self.datasaving_filepath + '/file')

    def enabling(self, enables=True):
        self.tem_detector.scale_checkbox.setEnabled(enables)
        for i in self.tem_stagectrl.rb_speeds.buttons():
            i.setEnabled(enables)
        for i in self.tem_stagectrl.movestages.buttons():
            i.setEnabled(enables)
        self.tem_tasks.gettem_button.setEnabled(enables)
        self.tem_tasks.gettem_checkbox.setEnabled(enables)
        self.tem_tasks.centering_button.setEnabled(False) #enables)
        self.tem_tasks.update_end_angle.setEnabled(enables)
        self.tem_tasks.rotation_button.setEnabled(enables)
        self.tem_tasks.input_start_angle.setEnabled(enables)
        self.tem_tasks.update_end_angle.setEnabled(enables)
        
        """ self.tem_tasks.beamAutofocus.setEnabled(enables) """

    def toggle_connectTEM(self):
        if not self.tem_tasks.connecttem_button.started:
            self.control.init.emit()
            self.tem_tasks.connecttem_button.setText("Disconnect")
            self.tem_tasks.connecttem_button.started = True
            self.control.trigger_getteminfo.emit('N')
        else:
            self.control.trigger_shutdown.emit()
            self.tem_tasks.connecttem_button.setText("Connect to TEM")
            self.tem_tasks.connecttem_button.started = False
        self.enabling(self.tem_tasks.connecttem_button.started)
        # self.enabling(True)
        
    def callGetInfoTask(self):
        if self.tem_tasks.gettem_checkbox.isChecked():
            if not os.access(self.file_operations.outPath_input.text(), os.W_OK):
                self.tem_tasks.gettem_checkbox.setChecked(False)
                logging.error(f'Writing in {self.file_operations.outPath_input.text()} is not permitted!')
            else:
                try:
                    self.formatted_filename = self.file_operations.formatted_filename
                except NameError:
                    logging.error('Filename is not defined.')
                    self.tem_tasks.gettem_checkbox.setChecked(False)
        if self.tem_tasks.gettem_checkbox.isChecked():
            self.control.trigger_getteminfo.emit('Y')
            if os.path.isfile(self.formatted_filename):
                logging.info(f'Trying to add TEMinfor to {self.formatted_filename}')
                self.temtools.addinfo_to_hdf()
        else:
            self.control.trigger_getteminfo.emit('N')

    # @Slot(int, str)
    def on_sockstatus_change(self, state, error_msg):
        if state == QAbstractSocket.SocketState.ConnectedState:
            message, color = "Connected!", "green"
            self.tem_tasks.connecttem_button.started = True
        elif state == QAbstractSocket.SocketState.ConnectingState:
            message, color = "Connecting", "orange"
            self.tem_tasks.connecttem_button.started = True
        elif error_msg:
            message = "Error (" + error_msg + ")"
            color = "red"
            self.tem_tasks.connecttem_button.started = False
        else:
            message, color = "Disconnected", "red"
            self.tem_tasks.connecttem_button.started = False
        self.tem_tasks.connecttem_button.setText(message)
        self.enabling(self.tem_tasks.connecttem_button.started)
        print(message, color) # '*can be ignored'
        # return message, color

    def on_tem_update(self):
        # self.beamcenter = float(fit_result_best_values['xo']), float(fit_result_best_values['yo'])
        angle_x = self.control.tem_status["stage.GetPos"][3]
        self.tem_tasks.input_start_angle.setValue(angle_x)
        
        if self.control.tem_status["eos.GetFunctionMode"][0] in [0, 1, 2]:
            magnification = self.control.tem_status["eos.GetMagValue"][2]
            self.tem_detector.input_magnification.setText(magnification)
            self.drawscale_overlay(xo=self.parent.imageItem.image.shape[1]*0.85, yo=self.parent.imageItem.image.shape[0]*0.1)
        if self.control.tem_status["eos.GetFunctionMode"][0] == 4:
            detector_distance = self.control.tem_status["eos.GetMagValue"][2]
            self.tem_detector.input_det_distance.setText(detector_distance)
            self.drawscale_overlay(xo=self.beamcenter[0], yo=self.beamcenter[1])

        rotation_speed_index = self.control.tem_status["stage.Getf1OverRateTxNum"]
        self.tem_stagectrl.rb_speeds.button(rotation_speed_index).setChecked(True)
        if not self.tem_tasks.rotation_button.started:
            if self.tem_tasks.withwriter_checkbox.isChecked():
                self.tem_tasks.rotation_button.setText("Rotation/Record")
            else:
                self.tem_tasks.rotation_button.setText("Rotation")

    def drawscale_overlay(self, xo=0, yo=0, l_draw=1, pixel=0.075):
        if self.scale != None:
            self.parent.plot.removeItem(self.scale)
        if self.tem_detector.scale_checkbox.isChecked():
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
            self.parent.plot.addItem(self.scale)        
            
    def toggle_rb_speeds(self):
        if self.tem_tasks.connecttem_button.started:
            self.control.send.emit("stage.Setf1OverRateTxNum("+ str(self.tem_stagectrl.rb_speeds.checkedId()) +")")

    def toggle_rotation(self):
        if not self.tem_tasks.rotation_button.started:
            self.tem_tasks.rotation_button.setText("Stop")
            self.tem_tasks.rotation_button.started = True
            if self.tem_tasks.withwriter_checkbox.isChecked():
                self.file_operations.streamWriterButton.setEnabled(False)
            self.control.trigger_record.emit()
        else:
            self.tem_tasks.rotation_button.setText("Rotation")
            self.tem_tasks.rotation_button.started = False
            if self.file_operations.streamWriterButton.started:
                self.file_operations.toggle_hdf5Writer()
            if self.tem_tasks.withwriter_checkbox.isChecked():
                self.file_operations.streamWriterButton.setEnabled(True)
            self.control.stop()
            
    # def toggle_centering(self):
    #     if not self.centering_button.started:
    #         self.centering_button.setText("Deactivate centering")
    #         self.centering_button.started = True
    #     else:
    #         self.centering_button.setText("Click-on-Centering")
    #         self.centering_button.started = False
            
    def toggle_beamAutofocus(self):
        if not self.tem_tasks.beamAutofocus.started:
            self.control.init.emit()
            self.control.actionFit_Beam.emit()
            self.tem_tasks.beamAutofocus.setText("Stop Autofocus")
            self.tem_tasks.beamAutofocus.started = True
            # Pop-up Window
            if self.tem_tasks.popup_checkbox.isChecked():
                self.tem_tasks.parent.showPlotDialog()  
        else:
            self.tem_tasks.beamAutofocus.setText("Start Beam Autofocus")
            self.tem_tasks.beamAutofocus.started = False
            # Close Pop-up Window
            if self.tem_tasks.parent.plotDialog != None:
                self.tem_tasks.parent.plotDialog.close()
            self.control.stop_task()
            # self.control.stop()

