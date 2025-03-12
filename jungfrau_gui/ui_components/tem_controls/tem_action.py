import pyqtgraph as pg
import numpy as np
#import random

from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsLineItem
from PySide6.QtCore import QRectF, QObject, QTimer, Qt, QMetaObject, Signal, Slot
from PySide6.QtGui import QFont, QTransform

from .toolbox.tool import *
from .toolbox import config as cfg_jf

from .task.task_manager import *

from epoc import ConfigurationClient, auth_token, redis_host

from .connectivity_inspector import TEM_Connector
from ..file_operations.processresult_updater import ProcessedDataReceiver

import jungfrau_gui.ui_threading_helpers as thread_manager
import time

from jungfrau_gui import globals

class CenterArrowItem(pg.ArrowItem):
    def paint(self, p, *args):
        p.translate(-self.boundingRect().center())
        pg.ArrowItem.paint(self, p, *args)

class TEMAction(QObject):
    """
    The 'TEMAction' object integrates the information from the detector/viewer and the TEM to be communicated each other.
    """    
    trigger_additem = Signal(str, str)
    trigger_getbeamintensity = Signal()
    trigger_updateitem = Signal(dict)
    trigger_processed_receiver = Signal()
    def __init__(self, parent, grandparent):
        super().__init__()
        self.parent = grandparent # ApplicationWindow in ui_main_window
        self.tem_controls = parent
        self.visualization_panel = self.parent.visualization_panel
        self.file_operations = self.parent.file_operations
        self.dataReceiverReady = True
        self.tem_detector = self.visualization_panel.tem_detector
        self.tem_stagectrl = self.tem_controls.tem_stagectrl
        self.tem_tasks = self.tem_controls.tem_tasks
        self.xtallist = self.file_operations.tem_xtalinfo.xtallist
        # self.temtools = TEMTools(self)
        self.control = ControlWorker(self)
        self.version =  self.parent.version
        self.last_mag_mode = None

        self.temConnector = None
        self.timer_tem_connexion = QTimer()
        self.timer_tem_connexion.timeout.connect(self.checkTemConnexion)
        
        # Initialization
        self.cfg = ConfigurationClient(redis_host(), token=auth_token())
        for shape in self.cfg.overlays:
            if shape['type'] == 'rectangle':
                self.lowmag_jump = shape['xy'][0]+shape['width']//2, shape['xy'][1]+shape['height']//2
                break

        self.scale = None
        self.marker = None
        self.snapshot_image = None
        self.cfg.beam_center = [1, 1] # Flag for non-updated metadata
        self.tem_stagectrl.position_list.addItems(cfg_jf.pos2textlist())
        
        # connect buttons with tem-functions
        self.tem_tasks.connecttem_button.clicked.connect(self.toggle_connectTEM)
        # self.tem_tasks.gettem_button.clicked.connect(self.callGetInfoTask)
        # self.tem_tasks.centering_button.clicked.connect(self.toggle_centering)
        self.tem_tasks.rotation_button.clicked.connect(self.toggle_rotation)    
        self.tem_tasks.beamAutofocus.clicked.connect(self.toggle_beamAutofocus)
        self.tem_tasks.btnGaussianFit.clicked.connect(lambda: self.tem_controls.toggle_gaussianFit_beam(by_user=True))
        self.tem_stagectrl.rb_speeds.buttonClicked.connect(self.toggle_rb_speeds)
        self.tem_stagectrl.mag_modes.buttonClicked.connect(self.toggle_mag_modes)
        self.tem_stagectrl.blanking_button.clicked.connect(self.toggle_blank)
        try:
            self.tem_stagectrl.screen_button.clicked.connect(self.toggle_screen)
        except AttributeError:
            pass
        if globals.dev:
            self.tem_detector.calc_e_incoming_button.clicked.connect(self.update_ecount)
            self.tem_stagectrl.mapsnapshot_button.clicked.connect(self.take_snaphot)
        
        self.control.updated.connect(self.on_tem_update)

        self.tem_stagectrl.movex10ump.clicked.connect(lambda: self.control.trigger_movewithbacklash.emit(0,  10000, cfg_jf.others.backlash[0]))
        self.tem_stagectrl.movex10umn.clicked.connect(lambda: self.control.trigger_movewithbacklash.emit(1, -10000, cfg_jf.others.backlash[0]))
        self.tem_stagectrl.move10degp.clicked.connect(lambda: self.control.trigger_movewithbacklash.emit(6,  10, cfg_jf.others.backlash[3]))
        self.tem_stagectrl.move10degp.clicked.connect(lambda: self.control.trigger_movewithbacklash.emit(7, -10, cfg_jf.others.backlash[3]))

        # Move X positive 10 micrometers
        #self.tem_stagectrl.movex10ump.clicked.connect(
        #    lambda: threading.Thread(target=self.control.client.SetXRel, args=(10000,)).start())
        
        # Move X negative 10 micrometers
        #self.tem_stagectrl.movex10umn.clicked.connect(
        #    lambda: threading.Thread(target=self.control.client.SetXRel, args=(-10000,)).start())

        # Move TX positive 10 degrees
        #self.tem_stagectrl.move10degp.clicked.connect(
        #    lambda: threading.Thread(target=self.control.client.SetTXRel, args=(10,)).start())

        # Move TX negative 10 degrees    
        #self.tem_stagectrl.move10degn.clicked.connect(
        #    lambda: threading.Thread(target=self.control.client.SetTXRel, args=(-10,)).start())

        # Set Tilt X Angle to 0 degrees
        self.tem_stagectrl.move0deg.clicked.connect(
            lambda: threading.Thread(target=self.control.client.SetTiltXAngle, args=(0,)).start())
        self.tem_stagectrl.go_button.clicked.connect(self.go_listedposition)
        self.tem_stagectrl.addpos_button.clicked.connect(self.add_listedposition)
        self.trigger_additem.connect(self.add_listedposition)
        self.trigger_processed_receiver.connect(self.inquire_processed_data)
        self.plot_listedposition()
        # self.trigger_getbeamintensity.connect(self.update_ecount)
        self.trigger_updateitem.connect(self.update_plotitem)
        ## for debug
        # self.tem_stagectrl.addpos_button.clicked.connect(lambda: self.update_plotitem())

    @Slot()
    def reconnectGaussianFit(self):
        self.tem_tasks.btnGaussianFit.clicked.connect(lambda: self.tem_controls.toggle_gaussianFit_beam(by_user=True))

    def set_configuration(self):
        self.file_operations.outPath_input.setText(self.cfg.data_dir.as_posix())

    def enabling(self, enables=True):
        if self.cfg.beam_center != [1,1]:
            self.tem_detector.scale_checkbox.setEnabled(enables)
        for i in self.tem_stagectrl.rb_speeds.buttons():
            i.setEnabled(enables)
        if enables:
            self.toggle_rb_speeds()
        for i in self.tem_stagectrl.movestages.buttons():
            i.setEnabled(enables)
        for i in self.tem_stagectrl.mag_modes.buttons():
            i.setEnabled(enables)
        # self.tem_tasks.gettem_button.setEnabled(enables)
        # self.tem_tasks.gettem_checkbox.setEnabled(False) # Not works correctly
        # self.tem_tasks.centering_button.setEnabled(enables)
        self.tem_tasks.centering_checkbox.setEnabled(enables)
        self.tem_tasks.btnGaussianFit.setEnabled(enables)
        self.tem_tasks.beamAutofocus.setEnabled(enables)
        self.tem_tasks.rotation_button.setEnabled(enables)
        self.tem_tasks.input_start_angle.setEnabled(enables)
        self.tem_tasks.update_end_angle.setEnabled(enables)
        self.tem_stagectrl.blanking_button.setEnabled(enables)
        try:
            self.tem_stagectrl.screen_button.setEnabled(enables)
        except AttributeError:
            pass 
        self.tem_stagectrl.position_list.setEnabled(enables)
        self.tem_stagectrl.go_button.setEnabled(enables)
        self.tem_stagectrl.addpos_button.setEnabled(enables)
        if globals.dev:
            self.tem_detector.calc_e_incoming_button.setEnabled(enables)
            self.tem_stagectrl.mapsnapshot_button.setEnabled(enables)

    def reset_rotation_button(self):
        self.tem_tasks.rotation_button.setText("Rotation")
        self.tem_tasks.rotation_button.started = False

    def toggle_connectTEM(self):
        if not self.tem_tasks.connecttem_button.started:
            try:
                self.tem_controls.voltage_spBx.setValue(self.control.tem_status["ht.GetHtValue"]/1e3)
            except TypeError:
                pass
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
            self.control.send_to_tem("#init", asynchronous=False)
        else:
            self.tem_tasks.connecttem_button.setStyleSheet('background-color: rgb(53, 53, 53); color: white;')
            self.tem_tasks.connecttem_button.setText("Check TEM Connection")
            self.tem_tasks.connecttem_button.started = False
            self.timer_tem_connexion.stop()
            self.parent.stopWorker(self.connect_thread, self.temConnector)
            self.temConnector, self.connect_thread = thread_manager.reset_worker_and_thread(self.temConnector, self.connect_thread)

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
        try:
            self.parent.tem_controls.voltage_spBx.setValue(self.control.tem_status["ht.GetHtValue"]/1e3) # keV 
        except TypeError:
            pass
        angle_x = self.control.tem_status["stage.GetPos"][3]
        if angle_x is not None: self.tem_tasks.input_start_angle.setValue(angle_x)
        
        # 1) Live query on both the current mode and the beam blank state
        Mag_idx = self.control.tem_status["eos.GetFunctionMode"][0] = self.control.client.GetFunctionMode()[0]

        if Mag_idx in [0, 1, 2]:
            magnification = self.control.tem_status["eos.GetMagValue"][2]
            self.tem_detector.input_magnification.setText(magnification)
            self.drawscale_overlay(xo=self.parent.imageItem.image.shape[1]*0.85, yo=self.parent.imageItem.image.shape[0]*0.1)
        elif Mag_idx == 4:            
            detector_distance = self.control.tem_status["eos.GetMagValue"][2]
            self.tem_detector.input_det_distance.setText(detector_distance)
            self.drawscale_overlay(xo=self.cfg.beam_center[0], yo=self.cfg.beam_center[1])
            
        beam_blank_state = self.control.tem_status["defl.GetBeamBlank"] = self.control.client.GetBeamBlank()

        # 2) Only do something if the mode *changed*
        if Mag_idx != self.last_mag_mode:
            if Mag_idx in [0, 1, 2]:
                if not self.parent.autoContrastBtn.started:
                    self.parent.autoContrastBtn.clicked.emit()

                # In MAG mode, we generally *want* Gaussian Fit OFF
                # so if it's currently ON, turn it OFF programmatically
                if self.tem_tasks.btnGaussianFit.started:
                    self.tem_controls.toggle_gaussianFit_beam(by_user=False)
                
                self.tem_stagectrl.mag_modes.button(mag_indices[Mag_idx]).setChecked(True)
            elif Mag_idx == 4:
                if self.parent.autoContrastBtn.started:
                    self.parent.resetContrastBtn.clicked.emit()

                # In DIFF mode, we generally *want* Gaussian Fit ON (unless user forced it off).
                # So if it's currently OFF and not user-forced-off, turn it on programmatically.
                if (not self.tem_tasks.btnGaussianFit.started) and (not self.tem_controls.gaussian_user_forced_off):
                    self.tem_controls.toggle_gaussianFit_beam(by_user=False)
                
                self.tem_stagectrl.mag_modes.button(mag_indices[Mag_idx]).setChecked(True)
            else:
                logging.error(f"Magnification index is invalid. Possible error when relaying 'eos.GetMagValue' to TEM")

            self.last_mag_mode = Mag_idx

        # 3) Handle beam blank logic on *every* poll (even if mode hasn't changed)
        if beam_blank_state == 1:
            # If the beam is blanked, forcibly turn off Gaussian Fit (if it’s currently running)
            if self.tem_tasks.btnGaussianFit.started:
                self.tem_controls.toggle_gaussianFit_beam(by_user=False)
        else:
            # If the beam is unblanked (0) and we are in DIFF mode (4), 
            # and not user-forced-off, ensure it's on
            if Mag_idx == 4 and not self.tem_controls.gaussian_user_forced_off:
                if not self.tem_tasks.btnGaussianFit.started:
                    self.tem_controls.toggle_gaussianFit_beam(by_user=False)

        # Update rotation_speed radio button in GUI to refelct status of TEM
        rotation_speed_index = self.control.tem_status["stage.Getf1OverRateTxNum"] # = self.control.client.Getf1OverRateTxNum()
        logging.debug(f"Rotation speed index: {rotation_speed_index}")
        if rotation_speed_index in [0,1,2,3]: self.tem_stagectrl.rb_speeds.button(rotation_speed_index).setChecked(True)
        
        self.plot_currentposition()

        if not self.tem_tasks.rotation_button.started:
            if self.tem_tasks.withwriter_checkbox.isChecked():
                self.tem_tasks.rotation_button.setText("Rotation/Record")
            else:
                self.tem_tasks.rotation_button.setText("Rotation")

        logging.debug("GUI updated with lastest TEM Status")

    def drawscale_overlay(self, xo=0, yo=0, l_draw=1):
        pixel = cfg_jf.others.pixelsize
        ht = self.parent.tem_controls.voltage_spBx.value()
        if self.scale != None:
            self.parent.plot.removeItem(self.scale)
        if self.tem_detector.scale_checkbox.isChecked():
            if self.control.tem_status["eos.GetFunctionMode"][0] == 4:
                detector_distance = self.control.tem_status["eos.GetMagValue"][2] ## with unit
                detector_distance = cfg_jf.lookup(cfg_jf.lut.distance, detector_distance, 'displayed', 'calibrated')
                radius_in_px = d2radius_in_px(d=l_draw, camlen=detector_distance, ht=ht)
                self.scale = QGraphicsEllipseItem(QRectF(xo-radius_in_px, yo-radius_in_px, radius_in_px*2, radius_in_px*2))
            else:
                magnification = self.control.tem_status["eos.GetMagValue"][2] ## with unit
                magnification = cfg_jf.lookup(cfg_jf.lut.magnification, magnification, 'displayed', 'calibrated')
                scale_in_px = l_draw * 1e-3 * magnification / pixel
                self.scale = QGraphicsLineItem(xo-scale_in_px/2, yo, xo+scale_in_px/2, yo)
            self.scale.setPen(pg.mkPen('w', width=2))
            self.parent.plot.addItem(self.scale)        

    def toggle_blank(self):
        if self.control.tem_status["defl.GetBeamBlank"] == 0:
            self.control.client.SetBeamBlank(1)
            self.tem_stagectrl.blanking_button.setText("Unblank beam")
            self.tem_stagectrl.blanking_button.setStyleSheet('background-color: orange; color: white;')
        else:
            self.control.client.SetBeamBlank(0)
            self.tem_stagectrl.blanking_button.setText("Blank beam")
            self.tem_stagectrl.blanking_button.setStyleSheet('background-color: rgb(53, 53, 53); color: white;')

    def toggle_screen(self):
        try:
            screen_status = self.control.client._send_message("GetScreen")
            if screen_status == 0:
                self.control.client._send_message("SetScreen", 2)
                time.sleep(2)
                self.tem_stagectrl.screen_button.setText("Screen Up")
            else:
                self.control.client._send_message("SetScreen", 0)
                time.sleep(2)
                self.tem_stagectrl.screen_button.setText("Screen Down")
        except RuntimeError:
            logging.warning('To move screen, use specific version of tem_server.py!')

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
            self.parent.resetContrastBtn.clicked.emit()
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
            self.control.send_to_tem("#info")
            self.control.trigger_record.emit()
            self.tem_tasks.rotation_button.setText("Stop")
            self.tem_tasks.rotation_button.started = True
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
    #     if not self.tem_tasks.centering_button.started:
    #         self.tem_tasks.centering_button.setText("Deactivate centering")
    #         self.tem_tasks.centering_button.started = True
    #     else:
    #         self.tem_tasks.centering_button.setText("Click-on-Centering")
    #         self.tem_tasks.centering_button.started = False
            
    def imageMouseClickEvent(self, event):
        # if event.buttons() != Qt.LeftButton or not self.tem_tasks.centering_button.started:
        if event.buttons() != Qt.LeftButton or not self.tem_tasks.centering_checkbox.isChecked():       
            logging.debug('Centering is not ready.')
            return
        if self.control.tem_status["eos.GetFunctionMode"][0] == 4:
            logging.warning('Centering should not be performed in Diff-MAG mode.')
            return
        im = self.parent.imageItem.image
        pos = event.pos()
        i, j = pos.y(), pos.x()
        i = int(np.clip(i, 0, im.shape[0] - 1))
        j = int(np.clip(j, 0, im.shape[1] - 1))
        val = im[i, j]
        ppos = self.parent.imageItem.mapToParent(pos)
        x, y = ppos.x(), ppos.y()
        # if self.tem_action.tem_tasks.centering_checkbox.isChecked():
        #     self.plot.removeItem(self.roi)
        # else:
        #     self.plot.addItem(self.roi)
        logging.debug(f"{x:0.1f}, {y:0.1f}")
        self.control.trigger_centering.emit(True, f"{x:0.1f}, {y:0.1f}")
            
    def toggle_beamAutofocus(self):
        if not self.tem_tasks.beamAutofocus.started:
            self.control.init.emit()
            # self.control.send_to_tem("#more")
            self.control.actionFit_Beam.emit()
            self.tem_tasks.beamAutofocus.setText("Stop Autofocus")
            self.tem_tasks.beamAutofocus.started = True
            # Pop-up Window
            if self.tem_tasks.popup_checkbox.isChecked():
                self.tem_tasks.parent.showPlotDialog()
        else:
            # Interrupt autofocus but end task gracefully
            self.control.set_sweeper_to_off_state()

    def go_listedposition(self):
        try:
            # position = self.control.client.GetStagePosition() # in nm
            position = send_with_retries(self.control.client.GetStagePosition)
        except Exception as e:
            logging.error(f"Error: {e}")
            return
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
        try:
            # position = self.control.client.GetStagePosition()
            position = send_with_retries(self.control.client.GetStagePosition)
        except Exception as e:
            logging.error(f"Error: {e}")
            return
        new_id = self.tem_stagectrl.position_list.count() - 4
        text = f"{new_id:3d}:{position[0]*1e-3:7.1f}{position[1]*1e-3:7.1f}{position[2]*1e-3:7.1f}, {status}"
        marker = pg.ScatterPlotItem(x=[position[0]*1e-3], y=[position[1]*1e-3], brush=color)
        label = pg.TextItem(str(new_id), anchor=(0, 1))
        label.setFont(QFont('Arial', 8))
        label.setPos(position[0]*1e-3, position[1]*1e-3)
        self.tem_stagectrl.position_list.addItem(text)
        self.tem_stagectrl.gridarea.addItem(marker)
        self.tem_stagectrl.gridarea.addItem(label)
        self.xtallist.append({"gui_id": new_id, "gui_text": text, "gui_marker": marker,
                              "gui_label": label, "position": position})
        logging.info(f"{new_id}: {position} is added to the list")

    @Slot(dict)
    def update_plotitem(self, info_d):
        if not "gui_id" in info_d:
            for gui_key in ["gui_id", "position", "gui_marker", "gui_label"]:
                info_d[gui_key] = info_d.get(gui_key, self.xtallist[-1][gui_key])
        if info_d["gui_id"] in [d.get('gui_id') for d in self.xtallist]:
            self.tem_stagectrl.position_list.removeItem(info_d["gui_id"] + 4)
            self.tem_stagectrl.gridarea.removeItem(info_d["gui_marker"])
            self.tem_stagectrl.gridarea.removeItem(info_d["gui_label"])
        elif info_d["gui_id"] is None:
            info_d["gui_id"] = self.tem_stagectrl.position_list.count() - 4

        # updated widget info
        position = info_d["position"]
        spots = np.array(info_d["spots"], dtype=float)
        axes = np.array(info_d["cell axes"], dtype=float)
        color_map = pg.colormap.get('plasma') # ('jet'); requires matplotlib
        color = color_map.map(spots[0]/spots[1], mode='qcolor')
        text = f"{info_d["dataid"]}:" + " ".join(map(str, info_d["lattice"])) + ", updated"
        label = pg.TextItem(str(info_d["dataid"]), anchor=(0, 1))
        label.setFont(QFont('Arial', 8))
        label.setPos(position[0]*1e-3, position[1]*1e-3)
        marker = pg.ScatterPlotItem(x=[position[0]*1e-3], y=[position[1]*1e-3], brush=color, symbol='d')
        # represent orientation with cell-a axis, usually shortest
        angle = np.degrees(np.arctan2(axes[1], axes[0])) + 180
        length = np.linalg.norm(axes[:2]) / np.linalg.norm(axes[:3])        
        arrow = CenterArrowItem(pos=(position[0]*1e-3, position[1]*1e-3), angle=angle,
                             headLen=20*length, tailLen=20*length, tailWidth=4*length, brush=color)
        # add updated items
        self.tem_stagectrl.position_list.addItem(text)
        self.tem_stagectrl.gridarea.addItem(marker)
        self.tem_stagectrl.gridarea.addItem(arrow)
        self.tem_stagectrl.gridarea.addItem(label)
        
        logging.info(f"Item {info_d["gui_id"]} is updated")
        logging.debug(self.xtallist)
    
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

    @Slot()
    def inquire_processed_data(self):
        if self.dataReceiverReady:
            self.process_receiver = ProcessedDataReceiver(self, host = "noether")            
            self.datareceiver_thread = QThread()
            self.parent.threadWorkerPairs.append((self.datareceiver_thread, self.process_receiver))
            thread_manager.move_worker_to_thread(self.datareceiver_thread, self.process_receiver)
            self.datareceiver_thread.start()
            self.dataReceiverReady = False
            self.process_receiver.finished.connect(self.getdataReceiverReady)
            logging.info("Starting processed-data inquiring")
        else:
            logging.warning("Previous inquiry continues runnng")

    def getdataReceiverReady(self):
        thread_manager.terminate_thread(self.datareceiver_thread)
        thread_manager.remove_worker_thread_pair(self.parent.threadWorkerPairs, self.datareceiver_thread)
        thread_manager.reset_worker_and_thread(self.process_receiver, self.datareceiver_thread)
        self.dataReceiverReady = True

    def update_ecount(self, threshold=500, bins_set=20):
        ht = self.parent.tem_controls.voltage_spBx.value()
        pixel = cfg_jf.others.pixelsize
        Mag_idx = self.control.tem_status["eos.GetFunctionMode"][0] = self.control.client.GetFunctionMode()[0]
        if Mag_idx == 4:
            logging.warning("Brightness should be calculated in imaging mode")
            return
        frame = self.parent.timer.interval()
        image = self.parent.imageItem.image
        data_flat = image.flatten()
        image_deloverflow = image[np.where(image < np.iinfo('int32').max-1)]
        low_thresh, high_thresh = np.percentile(image_deloverflow, (1, 99.999))
        data_sampled = image_deloverflow[np.where((image_deloverflow < high_thresh)&(image_deloverflow > threshold))]
        logging.info(f"No. of significant pixel for calculation: {len(data_sampled)} in {frame} frames")
        if len(data_sampled) < 1e4:
            self.tem_detector.e_incoming_display.setText(f'N/A')
            logging.warning('Number of sampling pixels is less than 1% (<1e4 pixels)!')
            return
        try:
            hist, bins = np.histogram(data_sampled, density=True, bins=bins_set)
            delta = (bins[1]-bins[0])/2
            xr = np.linspace(np.min(bins[1:])+delta,np.max(bins[1:])-delta,len(bins[1:])-1)
            approximate_average_count = xr[np.argmax(hist[1:])]
            logging.info(f'Approximate average: {approximate_average_count:.1f} count per pixel')
            e_per_A2 = approximate_average_count / ht * frame / ((pixel*1e7)**2) # per sec
            self.control.beam_intensity["pa_per_cm2"] = 1/6.241*e_per_A2*1e10 # per sec
            magnification = self.control.tem_status["eos.GetMagValue"][2] ## with unit
            magnification = cfg_jf.lookup(cfg_jf.lut.magnification, magnification, 'displayed', 'calibrated')
            self.control.beam_intensity["e_per_A2_sample"] = e_per_A2 * magnification**2
            self.tem_detector.e_incoming_display.setText(f'{self.control.beam_intensity["pa_per_cm2"]:.2f} pA/cm2/s, {self.control.beam_intensity["e_per_A2_sample"]:.2f} e/A2/s')
            logging.info(f'{self.control.beam_intensity["pa_per_cm2"]:.4f} pA/cm2/s, {self.control.beam_intensity["e_per_A2_sample"]:.4f} e/A2/s')
        except ValueError as e:
            self.tem_detector.e_incoming_display.setText(f'N/A')
            logging.warning(e)

    def take_snaphot(self):
        if self.control.tem_status["eos.GetFunctionMode"][0] == 4:
            logging.warning(f'Snaphot does not support Diff-mode at the moment!')
            return
        if self.snapshot_image is not None:
            self.tem_stagectrl.gridarea.removeItem(self.snapshot_image)
        magnification = self.control.tem_status["eos.GetMagValue"] ## with unit
        calibrated_mag = cfg_jf.lookup(cfg_jf.lut.magnification, magnification[2], 'displayed', 'calibrated')
        position = self.control.client.GetStagePosition()

        image = np.copy(self.parent.imageItem.image)

        image_deloverflow = image[np.where(image < np.iinfo('int32').max-1)]
        low_thresh, high_thresh = np.percentile(image_deloverflow, (1, 99.999))
#        self.snapshot_image = pg.ImageItem(np.clip(image, low_thresh, high_thresh)*0+1000*random.random())
        self.snapshot_image = pg.ImageItem(np.clip(image, low_thresh, high_thresh))
        
        tr = QTransform()
        tr.scale(cfg_jf.others.pixelsize*1e3/calibrated_mag, cfg_jf.others.pixelsize*1e3/calibrated_mag)
        if int(magnification[0]) >= 1500 : # Mag
            tr.rotate(180+cfg_jf.others.rotation_axis_theta)
            tr.translate(-image.shape[0]/2, -image.shape[1]/2)
        else:
            tr.rotate(180+cfg_jf.others.rotation_axis_theta_lm1200x)
            tr.translate(-self.lowmag_jump[0], -self.lowmag_jump[1])
        self.snapshot_image.setTransform(tr)
        self.tem_stagectrl.gridarea.addItem(self.snapshot_image)
        self.snapshot_image.setPos(position[0]*1e-3, position[1]*1e-3)
        self.snapshot_image.setZValue(-2)
        # self.snapshot_image.mouseClickEvent = self.subimageMouseClickEvent
        logging.info(f'Snapshot was updated.')