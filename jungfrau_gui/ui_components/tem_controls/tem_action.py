import pyqtgraph as pg

from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsLineItem
from PySide6.QtCore import QRectF, QObject, QTimer, Qt, QMetaObject, Signal, Slot
from PySide6.QtGui import QFont

from .toolbox.tool import *
from .toolbox import config as cfg_jf

from .task.task_manager import *

from epoc import ConfigurationClient, auth_token, redis_host

from .connectivity_inspector import TEM_Connector

import jungfrau_gui.ui_threading_helpers as thread_manager

class TEMAction(QObject):
    """
    The 'TEMAction' object integrates the information from the detector/viewer and the TEM to be communicated each other.
    """    
    trigger_additem = Signal(str, str)
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
        self.version =  self.parent.version

        self.timer_tem_connexion = QTimer()
        self.timer_tem_connexion.timeout.connect(self.checkTemConnexion)
        
        # Initialization
        self.cfg = ConfigurationClient(redis_host(), token=auth_token())

        self.scale = None
        self.marker = None
        # self.formatted_filename = '' # TODO DELETE? See use in 'callGetInfoTask' below 
        self.beamcenter = self.cfg.beam_center # TODO! read the value when needed!
        # self.xds_template_filepath = self.cfg.XDS_template
        self.tem_stagectrl.position_list.addItems(cfg_jf.pos2textlist())
        
        # connect buttons with tem-functions
        self.tem_tasks.connecttem_button.clicked.connect(self.toggle_connectTEM)
        self.tem_tasks.gettem_button.clicked.connect(self.callGetInfoTask)
        # self.tem_tasks.centering_button.clicked.connect(self.toggle_centering)
        self.tem_tasks.rotation_button.clicked.connect(self.toggle_rotation)    
        self.tem_tasks.beamAutofocus.clicked.connect(self.toggle_beamAutofocus)
        self.tem_stagectrl.rb_speeds.buttonClicked.connect(self.toggle_rb_speeds)
        self.tem_stagectrl.mag_modes.buttonClicked.connect(self.toggle_mag_modes)
        
        # self.control.tem_socket_status.connect(self.on_sockstatus_change)
        self.control.updated.connect(self.on_tem_update)
        
        # Move X positive 10 micrometers
        # self.tem_stagectrl.movex10ump.clicked.connect(lambda: self.control.client.SetXRel(10000))
        self.tem_stagectrl.movex10ump.clicked.connect(
            lambda: threading.Thread(target=self.control.client.SetXRel, args=(10000,)).start())
        
        # Move X negative 10 micrometers
        # self.tem_stagectrl.movex10umn.clicked.connect(lambda: self.control.client.SetXRel(-10000))
        self.tem_stagectrl.movex10umn.clicked.connect(
            lambda: threading.Thread(target=self.control.client.SetXRel, args=(-10000,)).start())

        # Move TX positive 10 degrees
        # self.tem_stagectrl.move10degp.clicked.connect(
        #             lambda: self.control.client.SetTXRel(10))
        self.tem_stagectrl.move10degp.clicked.connect(
            lambda: threading.Thread(target=self.control.client.SetTXRel, args=(10,)).start())

        # Move TX negative 10 degrees
        # self.tem_stagectrl.move10degn.clicked.connect(
        #             lambda: self.control.client.SetTXRel(-10))        
        self.tem_stagectrl.move10degn.clicked.connect(
            lambda: threading.Thread(target=self.control.client.SetTXRel, args=(-10,)).start())

        # Set Tilt X Angle to 0 degrees
        # self.tem_stagectrl.move0deg.clicked.connect(
        #             lambda: self.control.client.SetTiltXAngle(0))
        self.tem_stagectrl.move0deg.clicked.connect(
            lambda: threading.Thread(target=self.control.client.SetTiltXAngle, args=(0,)).start())
        self.tem_stagectrl.go_button.clicked.connect(self.go_listedposition)
        self.tem_stagectrl.addpos_button.clicked.connect(lambda: self.add_listedposition())
        self.trigger_additem.connect(self.add_listedposition)
        self.plot_listedposition()

    def set_configuration(self):
        self.file_operations.outPath_input.setText(self.cfg.data_dir.as_posix())
        self.file_operations.tiff_path.setText(self.cfg.data_dir.as_posix() + '/')

    def enabling(self, enables=True):
        self.tem_detector.scale_checkbox.setEnabled(enables)
        for i in self.tem_stagectrl.rb_speeds.buttons():
            i.setEnabled(enables)
        if enables:
            self.toggle_rb_speeds()
        for i in self.tem_stagectrl.movestages.buttons():
            i.setEnabled(enables)
        for i in self.tem_stagectrl.mag_modes.buttons():
            i.setEnabled(enables)
        self.tem_tasks.gettem_button.setEnabled(enables)
        self.tem_tasks.gettem_checkbox.setEnabled(False) # Not works correctly
        self.tem_tasks.centering_button.setEnabled(False) # Not functional yet
        self.tem_tasks.beamAutofocus.setEnabled(False) # Not functional yet
        self.tem_tasks.rotation_button.setEnabled(enables)
        self.tem_tasks.input_start_angle.setEnabled(enables)
        self.tem_tasks.update_end_angle.setEnabled(enables)
        self.tem_stagectrl.go_button.setEnabled(enables)
        self.tem_stagectrl.addpos_button.setEnabled(enables)

    def toggle_connectTEM(self):
        if not self.tem_tasks.connecttem_button.started:
            self.control.init.emit()
            self.connect_thread = QThread()
            self.temConnector = TEM_Connector()
            self.parent.threadWorkerPairs.append((self.connect_thread, self.temConnector))
            self.initializeWorker(self.connect_thread, self.temConnector)
            self.connect_thread.start()
            self.connectorWorkerReady = True
            logging.info("Starting tem-connecting process")
            self.tem_tasks.connecttem_button.started = True
            self.timer_tem_connexion.start(self.tem_tasks.polling_frequency.value()) # 0.5 seconds between pings
        else:
            self.tem_tasks.connecttem_button.setStyleSheet('background-color: rgb(53, 53, 53); color: white;')
            self.tem_tasks.connecttem_button.setText("Check TEM Connection")
            self.tem_tasks.connecttem_button.started = False
            self.timer_tem_connexion.stop()
            self.parent.stopWorker(self.connect_thread, self.temConnector)

    def initializeWorker(self, thread, worker):
        thread_manager.move_worker_to_thread(thread, worker)
        worker.finished.connect(self.updateTemControls)
        worker.finished.connect(self.getConnectorReady)

    def getConnectorReady(self):
        self.connectorWorkerReady = True

    def checkTemConnexion(self):
        if self.connectorWorkerReady:
            self.connectorWorkerReady = False
            QMetaObject.invokeMethod(self.temConnector, "run", Qt.QueuedConnection)

    def updateTemControls(self, tem_connected):
        if tem_connected:
            self.tem_tasks.connecttem_button.setStyleSheet('background-color: green; color: white;')
            self.tem_tasks.connecttem_button.setText("Connection OK")
            # self.control.trigger_getteminfo.emit('N')
        else:
            self.tem_tasks.connecttem_button.setStyleSheet('background-color: red; color: white;')
            self.tem_tasks.connecttem_button.setText("Disconnected")
        self.enabling(tem_connected) #also disables buttons if tem-gui connection is cut
        if tem_connected:
            self.control.send_to_tem("#info")
        
    def callGetInfoTask(self):
        self.control.init.emit()
        if self.tem_tasks.gettem_checkbox.isChecked():
            self.control.trigger_getteminfo.emit('Y')
            # if os.path.isfile(self.formatted_filename):
            #     logging.info(f'Trying to add TEM information to {self.formatted_filename}')
            #     self.temtools.addinfo_to_hdf()
        else:
            self.control.trigger_getteminfo.emit('N')

    def on_tem_update(self):
        logging.debug("Updating GUI with last TEM Status...")
        # self.beamcenter = float(fit_result_best_values['xo']), float(fit_result_best_values['yo'])
        angle_x = self.control.tem_status["stage.GetPos"][3]
        self.tem_tasks.input_start_angle.setValue(angle_x)
        
        # Update Magnification radio button in GUI to refelct status of TEM
        Mag_idx = self.control.tem_status["eos.GetFunctionMode"][0]

        if Mag_idx in [0, 1, 2]:
            self.tem_stagectrl.mag_modes.button(mag_indices[Mag_idx]).setChecked(True)
            magnification = self.control.tem_status["eos.GetMagValue"][2]
            self.tem_detector.input_magnification.setText(magnification)
            self.drawscale_overlay(xo=self.parent.imageItem.image.shape[1]*0.85, yo=self.parent.imageItem.image.shape[0]*0.1)
        elif Mag_idx == 4:
            self.tem_stagectrl.mag_modes.button(mag_indices[Mag_idx]).setChecked(True)
            detector_distance = self.control.tem_status["eos.GetMagValue"][2]
            self.tem_detector.input_det_distance.setText(detector_distance)
            self.drawscale_overlay(xo=self.beamcenter[0], yo=self.beamcenter[1])
        else:
            logging.error(f"Magnification index is invalid. Possible error when relaying 'eos.GetMagValue' to TEM")
        
        # Update rotation_speed radio button in GUI to refelct status of TEM
        rotation_speed_index = self.control.tem_status["stage.Getf1OverRateTxNum"]
        self.tem_stagectrl.rb_speeds.button(rotation_speed_index).setChecked(True)
        
        self.plot_currentposition()

        if not self.tem_tasks.rotation_button.started:
            if self.tem_tasks.withwriter_checkbox.isChecked():
                self.tem_tasks.rotation_button.setText("Rotation/Record")
            else:
                self.tem_tasks.rotation_button.setText("Rotation")

        logging.debug("GUI updated with lastest TEM Status")

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
        idx_rot_button = self.tem_stagectrl.rb_speeds.checkedId()
        if self.cfg.rotation_speed_idx != idx_rot_button:
            self.update_rotation_speed_idx_from_ui(idx_rot_button)
            result = self.control.execute_command("Setf1OverRateTxNum("+ str(idx_rot_button) +")")
            if result is not None:
                logging.info(f"Rotation velocity is set to {[10.0, 2.0, 1.0, 0.5][idx_rot_button]} deg/s")
            else:
                rotation_at_tem = self.control.client.Getf1OverRateTxNum()
                logging.error(f"Changes of rotation speed has failed!\nRotation at TEM is {[10.0, 2.0, 1.0, 0.5][rotation_at_tem]} deg/s")
                # TODO ? Make sure the right (eq to TEM status) button is checked
    
    def toggle_mag_modes(self):
        idx_mag_button = self.tem_stagectrl.mag_modes.checkedId()
        if idx_mag_button == 4:
            self.visualization_panel.resetContrastBtn.clicked.emit()
        try:
            self.control.client.SelectFunctionMode(idx_mag_button)
            logging.info(f"Function Mode switched to {self.control.client.GetFunctionMode()[0]} (0=MAG, 2=Low MAG, 4=DIFF)")
        except Exception as e:
            logging.warning(f"Error occured when relaying 'SelectFunctionMode({idx_mag_button}': {e}")
            idx = self.control.client.GetFunctionMode()[0]
            if idx == 1: idx=0 # 0=MAG, 1=MAG2 -> Treat them as same
            self.tem_stagectrl.mag_modes.button(idx).setChecked(True)

    def update_rotation_speed_idx_from_ui(self, idx_rot_button):
        self.cfg.rotation_speed_idx = idx_rot_button
        logging.debug(f"rotation_speed_idx updated to: {self.cfg.rotation_speed_idx} i.e. velocity is {[10.0, 2.0, 1.0, 0.5][self.cfg.rotation_speed_idx]} deg/s")

    def toggle_rotation(self):
        if not self.tem_tasks.rotation_button.started:
            self.control.init.emit()
            self.control.send_to_tem("#more")
            self.control.trigger_record.emit()
            self.tem_tasks.rotation_button.setText("Stop")
            self.tem_tasks.rotation_button.started = True
            if self.tem_tasks.withwriter_checkbox.isChecked():
                self.file_operations.streamWriterButton.setEnabled(False)
        else:
            # In case of unwarranted interruption, to avoid button stuck in "Stop"
            if self.control.interruptRotation: 
                self.tem_tasks.rotation_button.setText("Rotation")
                self.tem_tasks.rotation_button.started= False
                self.control.interruptRotation = False
                return    
            # Interrupt rotation but end task gracefully
            self.control.interruptRotation = True
            
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
            self.control.send_to_tem("#more")
            self.control.actionFit_Beam.emit()
            self.tem_tasks.beamAutofocus.setText("Stop Autofocus")
            self.tem_tasks.beamAutofocus.started = True
            # Pop-up Window
            if self.tem_tasks.popup_checkbox.isChecked():
                self.tem_tasks.parent.showPlotDialog()  
        else:
            """ 
            To correct/adapt the interruption case
            as in the 'toggle_rotation' above 
            """
            logging.warning(f"Interrupting Task - {self.control.task.task_name} -")
            self.control.task.finished.disconnect()

            self.tem_tasks.beamAutofocus.setText("Start Beam Autofocus")
            self.tem_tasks.beamAutofocus.started = False
            # Close Pop-up Window
            if self.tem_tasks.parent.plotDialog != None:
                self.tem_tasks.parent.plotDialog.close_window()
            self.control.actionFit_Beam.emit()
            # self.control.stop_task()

    def go_listedposition(self):
        position = self.control.client.GetStagePosition() # in nm
        position_aim = np.array(self.tem_stagectrl.position_list.currentText().split()[1:-2], dtype=float) # in um
        dif_pos = position_aim[0]*1e3 - position[0], position_aim[1]*1e3 - position[1]
        try:
            self.control.client._send_message("SetStagePosition", dif_pos[0], dif_pos[1]) # lambda: threading.Thread(target=self.control.client.SetXRel, args=(-10000,)).start())
            time.sleep(2) # should be updated with referring stage status!!
            logging.info(f"Moved by x:{dif_pos[0]*1e-3:6.2f} um, y:{dif_pos[1]*1e-3:6.2f} um")
            logging.info(f"Aim position was x:{position_aim[0]:3.2f} um, y:{position_aim[1]:3.2f} um")
        except RuntimeError:
            logging.warning('To set position, use specific version of tem_server.py!')
            self.tem_stagectrl.go_button.setEnabled(False)

    @Slot(str, str)
    def add_listedposition(self, color='red', status='new'):
        position = self.control.client.GetStagePosition()
        new_id = self.tem_stagectrl.position_list.count() - 4
        self.tem_stagectrl.position_list.addItems([f"{new_id:3d}:{position[0]*1e-3:7.1f}{position[1]*1e-3:7.1f}{position[2]*1e-3:7.1f}, {status}"])
        self.tem_stagectrl.gridarea.addItem(pg.ScatterPlotItem(x=[position[0]*1e-3], y=[position[1]*1e-3], brush=color))
        label = pg.TextItem(str(new_id), anchor=(0, 1))
        label.setFont(QFont('Arial', 8))
        label.setPos(position[0]*1e-3, position[1]*1e-3)
        self.tem_stagectrl.gridarea.addItem(label)
        logging.info(f"{new_id}: {position} is added to the list")

    def plot_listedposition(self, color='gray'):
        xy_list = [self.tem_stagectrl.position_list.itemText(i).split()[1:-2] for i in range(self.tem_stagectrl.position_list.count())]
        xy_list = np.array(xy_list).T
        self.tem_stagectrl.gridarea.addItem(pg.ScatterPlotItem(x=xy_list[0], y=xy_list[1], brush=color))

    def plot_currentposition(self, color='yellow'):
        if self.marker != None:
            self.tem_stagectrl.gridarea.removeItem(self.marker)
        position = self.control.tem_status["stage.GetPos"]
        self.marker = pg.ScatterPlotItem(x=[position[0]*1e-3], y=[position[1]*1e-3], brush=color)
        self.tem_stagectrl.gridarea.addItem(self.marker)