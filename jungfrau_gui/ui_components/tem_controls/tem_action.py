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
        p.translate(-self.boundingRect().center()*2)
        pg.ArrowItem.paint(self, p, *args)

class TEMAction(QObject):
    """
    The 'TEMAction' object integrates the information from the detector/viewer and the TEM to be communicated each other.
    """    
    trigger_additem = Signal(str, str, list)
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
        self.lut = cfg_jf.lut()
        for shape in self.cfg.overlays:
            if shape['type'] == 'rectangle':
                self.lowmag_jump = shape['xy'][0]+shape['width']//2, shape['xy'][1]+shape['height']//2
                break

        self.scale = None
        self.marker = None
        self.snapshot_images = []
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
            self.tem_detector.calc_e_incoming_button.clicked.connect(lambda: self.update_ecount())
            self.tem_stagectrl.mapsnapshot_button.clicked.connect(lambda: self.take_snapshot())
            self.tem_stagectrl.loadsave_button.clicked.connect(self.synchronize_xtallist)
        
        self.control.updated.connect(self.on_tem_update)

        self.tem_stagectrl.movex10ump.clicked.connect(lambda: self.control.trigger_movewithbacklash.emit(0,  10000, cfg_jf.others.backlash[0]))
        self.tem_stagectrl.movex10umn.clicked.connect(lambda: self.control.trigger_movewithbacklash.emit(1, -10000, cfg_jf.others.backlash[0]))
        self.tem_stagectrl.move10degp.clicked.connect(lambda: self.control.trigger_movewithbacklash.emit(6,  10, cfg_jf.others.backlash[3]))
        self.tem_stagectrl.move10degn.clicked.connect(lambda: self.control.trigger_movewithbacklash.emit(7, -10, cfg_jf.others.backlash[3]))

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
        self.tem_stagectrl.addpos_button.clicked.connect(lambda: self.add_listedposition())
        self.trigger_additem.connect(self.add_listedposition)
        self.trigger_processed_receiver.connect(self.inquire_processed_data)
        self.plot_listedposition()
        # self.trigger_getbeamintensity.connect(self.update_ecount)
        self.trigger_updateitem.connect(self.update_plotitem)
        self.main_overlays = [None, None, None] 

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
            if self.main_overlays[0] != None:
                [self.parent.plot.removeItem(i) for i in self.main_overlays]
            self.main_overlays = self.lut.overlays_for_ht(self.parent.tem_controls.voltage_spBx.value()*1e3)
            [self.parent.plot.addItem(i) for i in self.main_overlays]
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
            # Cache the tem_status reference to avoid repeated dictionary lookups
            tem_status = self.control.tem_status
            
            # Update voltage display
            self.parent.tem_controls.voltage_spBx.setValue(tem_status["ht.GetHtValue"]/1e3)  # keV 
        except TypeError:
            pass
        
        # Update angle display (only when needed)
        angle_x = tem_status.get("stage.GetPos", [None, None, None, None, None])[3]
        if angle_x is not None:
            self.tem_tasks.input_start_angle.setValue(angle_x)
        
        # Store beam sigma values
        self.control.beam_sigmaxy = [
            self.tem_controls.sigma_x_spBx.value(), 
            self.tem_controls.sigma_y_spBx.value()
        ]
        
        # Get current function mode (fix assignment operator bug)
        client = self.control.client
        Mag_idx = client.GetFunctionMode()[0]
        tem_status["eos.GetFunctionMode"] = [Mag_idx]
        
        # Cache magnification values to avoid repeated lookups
        mag_value = tem_status.get("eos.GetMagValue", [None, None, None])[2]
        
        # Process mode-specific logic
        if Mag_idx in [0, 1, 2]:
            # MAG mode
            self.tem_detector.input_magnification.setText(str(mag_value))
            # Get image dimensions once
            img = self.parent.imageItem.image
            if img is not None:
                shape = img.shape
                self.drawscale_overlay(xo=shape[1]*0.85, yo=shape[0]*0.1)
        elif Mag_idx == 4:
            # DIFF mode
            self.tem_detector.input_det_distance.setText(str(mag_value))
            self.drawscale_overlay(xo=self.cfg.beam_center[0], yo=self.cfg.beam_center[1])
        
        # Get beam blank state
        beam_blank_state = client.GetBeamBlank()
        tem_status["defl.GetBeamBlank"] = beam_blank_state
        
        # Check if mode changed
        mode_changed = Mag_idx != self.last_mag_mode
        if mode_changed:
            # Cache references to frequently accessed properties
            auto_contrast_btn = self.parent.autoContrastBtn
            gaussian_fit_btn = self.tem_tasks.btnGaussianFit
            
            if Mag_idx in [0, 1, 2]:
                # MAG mode handling
                if not auto_contrast_btn.started:
                    auto_contrast_btn.clicked.emit()

                # Turn OFF Gaussian Fit in MAG mode if it's currently ON
                if gaussian_fit_btn.started:
                    self.tem_controls.toggle_gaussianFit_beam(by_user=False)
                    
                # Update UI state
                self.tem_stagectrl.mag_modes.button(mag_indices[Mag_idx]).setChecked(True)
            elif Mag_idx == 4:
                # DIFF mode handling
                if auto_contrast_btn.started:
                    self.parent.resetContrastBtn.clicked.emit()

                # Turn ON Gaussian Fit in DIFF mode if it's not user-forced-off
                if (not gaussian_fit_btn.started) and (not self.tem_controls.gaussian_user_forced_off):
                    self.tem_controls.toggle_gaussianFit_beam(by_user=False)
                    
                # Update UI state
                self.tem_stagectrl.mag_modes.button(mag_indices[Mag_idx]).setChecked(True)
            else:
                logging.error(f"Magnification index {Mag_idx} is invalid.")

            # Update last mode
            self.last_mag_mode = Mag_idx

        # Handle beam blank logic on every poll
        if beam_blank_state == 1:
            # Beam is blanked - turn off Gaussian Fit if running
            if self.tem_tasks.btnGaussianFit.started:
                self.tem_controls.toggle_gaussianFit_beam(by_user=False)
        elif Mag_idx == 4 and not self.tem_controls.gaussian_user_forced_off:
            # Beam is unblanked and in DIFF mode - ensure Gaussian Fit is on
            if not self.tem_tasks.btnGaussianFit.started:
                self.tem_controls.toggle_gaussianFit_beam(by_user=False)

        # Update rotation speed UI
        rotation_speed_index = tem_status.get("stage.Getf1OverRateTxNum")
        if rotation_speed_index in [0, 1, 2, 3]:
            self.tem_stagectrl.rb_speeds.button(rotation_speed_index).setChecked(True)
        
        # Update position plot
        self.plot_currentposition()

        # Update rotation button text if needed
        rotation_button = self.tem_tasks.rotation_button
        if not rotation_button.started:
            rotation_button.setText(
                "Rotation/Record" if self.tem_tasks.withwriter_checkbox.isChecked() else "Rotation"
            )

        logging.debug("GUI updated with lastest TEM Status")

    # def on_tem_update(self):
    #     logging.debug("Updating GUI with last TEM Status...")
    #     try:
    #         self.parent.tem_controls.voltage_spBx.setValue(self.control.tem_status["ht.GetHtValue"]/1e3) # keV 
    #     except TypeError:
    #         pass
    #     angle_x = self.control.tem_status["stage.GetPos"][3]
    #     if angle_x is not None: self.tem_tasks.input_start_angle.setValue(angle_x)
    #     self.control.beam_sigmaxy = [self.tem_controls.sigma_x_spBx.value(), self.tem_controls.sigma_y_spBx.value()]
        
    #     # 1) Live query on both the current mode and the beam blank state
    #     Mag_idx = self.control.tem_status["eos.GetFunctionMode"][0] = self.control.client.GetFunctionMode()[0]

    #     if Mag_idx in [0, 1, 2]:
    #         magnification = self.control.tem_status["eos.GetMagValue"][2]
    #         self.tem_detector.input_magnification.setText(magnification)
    #         self.drawscale_overlay(xo=self.parent.imageItem.image.shape[1]*0.85, yo=self.parent.imageItem.image.shape[0]*0.1)
    #     elif Mag_idx == 4:            
    #         detector_distance = self.control.tem_status["eos.GetMagValue"][2]
    #         self.tem_detector.input_det_distance.setText(detector_distance)
    #         self.drawscale_overlay(xo=self.cfg.beam_center[0], yo=self.cfg.beam_center[1])
            
    #     beam_blank_state = self.control.tem_status["defl.GetBeamBlank"] = self.control.client.GetBeamBlank()

    #     # 2) Only do something if the mode *changed*
    #     if Mag_idx != self.last_mag_mode:
    #         if Mag_idx in [0, 1, 2]:
    #             if not self.parent.autoContrastBtn.started:
    #                 self.parent.autoContrastBtn.clicked.emit()

    #             # In MAG mode, we generally *want* Gaussian Fit OFF
    #             # so if it's currently ON, turn it OFF programmatically
    #             if self.tem_tasks.btnGaussianFit.started:
    #                 self.tem_controls.toggle_gaussianFit_beam(by_user=False)
                
    #             self.tem_stagectrl.mag_modes.button(mag_indices[Mag_idx]).setChecked(True)
    #         elif Mag_idx == 4:
    #             if self.parent.autoContrastBtn.started:
    #                 self.parent.resetContrastBtn.clicked.emit()

    #             # In DIFF mode, we generally *want* Gaussian Fit ON (unless user forced it off).
    #             # So if it's currently OFF and not user-forced-off, turn it on programmatically.
    #             if (not self.tem_tasks.btnGaussianFit.started) and (not self.tem_controls.gaussian_user_forced_off):
    #                 self.tem_controls.toggle_gaussianFit_beam(by_user=False)
                
    #             self.tem_stagectrl.mag_modes.button(mag_indices[Mag_idx]).setChecked(True)
    #         else:
    #             logging.error(f"Magnification index is invalid. Possible error when relaying 'eos.GetMagValue' to TEM")

    #         self.last_mag_mode = Mag_idx

    #     # 3) Handle beam blank logic on *every* poll (even if mode hasn't changed)
    #     if beam_blank_state == 1:
    #         # If the beam is blanked, forcibly turn off Gaussian Fit (if it’s currently running)
    #         if self.tem_tasks.btnGaussianFit.started:
    #             self.tem_controls.toggle_gaussianFit_beam(by_user=False)
    #     else:
    #         # If the beam is unblanked (0) and we are in DIFF mode (4), 
    #         # and not user-forced-off, ensure it's on
    #         if Mag_idx == 4 and not self.tem_controls.gaussian_user_forced_off:
    #             if not self.tem_tasks.btnGaussianFit.started:
    #                 self.tem_controls.toggle_gaussianFit_beam(by_user=False)

    #     # Update rotation_speed radio button in GUI to refelct status of TEM
    #     rotation_speed_index = self.control.tem_status["stage.Getf1OverRateTxNum"] # = self.control.client.Getf1OverRateTxNum()
    #     logging.debug(f"Rotation speed index: {rotation_speed_index}")
    #     if rotation_speed_index in [0,1,2,3]: self.tem_stagectrl.rb_speeds.button(rotation_speed_index).setChecked(True)
        
    #     self.plot_currentposition()

    #     if not self.tem_tasks.rotation_button.started:
    #         if self.tem_tasks.withwriter_checkbox.isChecked():
    #             self.tem_tasks.rotation_button.setText("Rotation/Record")
    #         else:
    #             self.tem_tasks.rotation_button.setText("Rotation")

    #     logging.debug("GUI updated with lastest TEM Status")

    def drawscale_overlay(self, xo=0, yo=0, l_draw=1):
        """Draw scale overlay on the image with caching optimizations."""
        # Early exit if scale checkbox is unchecked
        if not self.tem_detector.scale_checkbox.isChecked():
            if self.scale is not None:
                self.parent.plot.removeItem(self.scale)
                self.scale = None
            return
            
        # Cache frequently accessed values
        pixel = cfg_jf.others.pixelsize
        ht = self.parent.tem_controls.voltage_spBx.value()
        
        # Remove previous scale item
        if self.scale is not None:
            self.parent.plot.removeItem(self.scale)
        
        # Cache tem_status to avoid repeated lookups
        tem_status = self.control.tem_status
        function_mode = tem_status["eos.GetFunctionMode"][0]
        mag_value = tem_status["eos.GetMagValue"][2]
        
        # Create scale based on function mode
        if function_mode == 4:
            # Use cached or memoized interpolation when possible
            detector_distance = self.lut.interpolated_distance(mag_value, ht)
            radius_in_px = d2radius_in_px(d=l_draw, camlen=detector_distance, ht=ht)
            self.scale = QGraphicsEllipseItem(QRectF(xo-radius_in_px, yo-radius_in_px, radius_in_px*2, radius_in_px*2))
        else:
            # Use cached or memoized calibration when possible
            magnification = self.lut.calibrated_magnification(mag_value)
            scale_in_px = l_draw * 1e-3 * magnification / pixel
            self.scale = QGraphicsLineItem(xo-scale_in_px/2, yo, xo+scale_in_px/2, yo)
        
        # Set pen only once and add to plot
        self.scale.setPen(pg.mkPen('w', width=2))
        self.parent.plot.addItem(self.scale)

    def toggle_blank(self):
        """Toggle beam blank state with state caching."""
        # Cache client reference
        client = self.control.client
        
        # Cache button reference
        blank_button = self.tem_stagectrl.blanking_button
        
        # Check current blank state
        is_blanked = self.control.tem_status["defl.GetBeamBlank"] == 1
        
        if not is_blanked:
            # Blank the beam
            client.SetBeamBlank(1)
            blank_button.setText("Unblank beam")
            blank_button.setStyleSheet('background-color: orange; color: white;')
        else:
            # Unblank the beam
            client.SetBeamBlank(0)
            blank_button.setText("Blank beam")
            blank_button.setStyleSheet('background-color: rgb(53, 53, 53); color: white;')

    def toggle_screen(self):
        """Toggle screen position with error handling."""
        # Cache client reference
        client = self.control.client
        screen_button = self.tem_stagectrl.screen_button
        
        try:
            # Get screen status only once
            screen_status = client._send_message("GetScreen")
            
            # Set new screen state based on current state
            new_state = 0 if screen_status != 0 else 2
            new_text = "Screen Down" if new_state == 0 else "Screen Up"
            
            # Send command once
            client._send_message("SetScreen", new_state)
            
            # Use a single sleep call
            time.sleep(2)
            
            # Update button text once
            screen_button.setText(new_text)
        except RuntimeError:
            logging.warning('To move screen, use specific version of tem_server.py!')

    def toggle_rb_speeds(self):
        """Toggle rotation speed with performance optimizations."""
        # Get checked button ID once
        idx_rot_button = self.tem_stagectrl.rb_speeds.checkedId()
        
        # Only proceed if speed has changed
        if self.cfg.rotation_speed_idx == idx_rot_button:
            return
            
        # Update UI configuration first
        self.update_rotation_speed_idx_from_ui(idx_rot_button)
        
        # Cache rotation speed mappings
        speed_values = [10.0, 2.0, 1.0, 0.5]
        
        # Execute command once
        result = self.control.execute_command(f"Setf1OverRateTxNum({idx_rot_button})")
        
        if result is not None:
            logging.info(f"Rotation velocity is set to {speed_values[idx_rot_button]} deg/s")
        else:
            # Only get TEM status if command failed
            rotation_at_tem = self.control.client.Getf1OverRateTxNum()
            logging.error(f"Changes of rotation speed has failed!\nRotation at TEM is {speed_values[rotation_at_tem]} deg/s")

    def toggle_mag_modes(self):
        """Toggle magnification modes with error handling."""
        # Get checked button ID once
        idx_mag_button = self.tem_stagectrl.mag_modes.checkedId()
        
        # Early reset contrast if needed
        if idx_mag_button == 4:
            self.parent.resetContrastBtn.clicked.emit()
        
        # Cache client reference
        client = self.control.client
        
        try:
            # Send command once
            client.SelectFunctionMode(idx_mag_button)
            
            # Get function mode only once
            function_mode = client.GetFunctionMode()[0]
            logging.info(f"Function Mode switched to {function_mode} (0=MAG, 2=Low MAG, 4=DIFF)")
        except Exception as e:
            logging.warning(f"Error occurred when relaying 'SelectFunctionMode({idx_mag_button})': {e}")
            
            # Only get function mode if there was an error
            idx = client.GetFunctionMode()[0]
            
            # Normalize function mode (treat MAG and MAG2 as same)
            if idx == 1:
                idx = 0
                
            # Update UI to reflect actual state
            self.tem_stagectrl.mag_modes.button(idx).setChecked(True)

    # def drawscale_overlay(self, xo=0, yo=0, l_draw=1):
    #     pixel = cfg_jf.others.pixelsize
    #     ht = self.parent.tem_controls.voltage_spBx.value()
    #     if self.scale != None:
    #         self.parent.plot.removeItem(self.scale)
    #     if self.tem_detector.scale_checkbox.isChecked():
    #         if self.control.tem_status["eos.GetFunctionMode"][0] == 4:
    #             detector_distance = self.control.tem_status["eos.GetMagValue"][2] ## with unit
    #             detector_distance = self.lut.interpolated_distance(detector_distance, self.parent.tem_controls.voltage_spBx.value())
    #             radius_in_px = d2radius_in_px(d=l_draw, camlen=detector_distance, ht=ht)
    #             self.scale = QGraphicsEllipseItem(QRectF(xo-radius_in_px, yo-radius_in_px, radius_in_px*2, radius_in_px*2))
    #         else:
    #             magnification = self.control.tem_status["eos.GetMagValue"][2] ## with unit
    #             magnification = self.lut.calibrated_magnification(magnification)
    #             scale_in_px = l_draw * 1e-3 * magnification / pixel
    #             self.scale = QGraphicsLineItem(xo-scale_in_px/2, yo, xo+scale_in_px/2, yo)
    #         self.scale.setPen(pg.mkPen('w', width=2))
    #         self.parent.plot.addItem(self.scale)        

    # def toggle_blank(self):
    #     if self.control.tem_status["defl.GetBeamBlank"] == 0:
    #         self.control.client.SetBeamBlank(1)
    #         self.tem_stagectrl.blanking_button.setText("Unblank beam")
    #         self.tem_stagectrl.blanking_button.setStyleSheet('background-color: orange; color: white;')
    #     else:
    #         self.control.client.SetBeamBlank(0)
    #         self.tem_stagectrl.blanking_button.setText("Blank beam")
    #         self.tem_stagectrl.blanking_button.setStyleSheet('background-color: rgb(53, 53, 53); color: white;')

    # def toggle_screen(self):
    #     try:
    #         screen_status = self.control.client._send_message("GetScreen")
    #         if screen_status == 0:
    #             self.control.client._send_message("SetScreen", 2)
    #             time.sleep(2)
    #             self.tem_stagectrl.screen_button.setText("Screen Up")
    #         else:
    #             self.control.client._send_message("SetScreen", 0)
    #             time.sleep(2)
    #             self.tem_stagectrl.screen_button.setText("Screen Down")
    #     except RuntimeError:
    #         logging.warning('To move screen, use specific version of tem_server.py!')

    # def toggle_rb_speeds(self):
    #     idx_rot_button = self.tem_stagectrl.rb_speeds.checkedId()
    #     if self.cfg.rotation_speed_idx != idx_rot_button:
    #         self.update_rotation_speed_idx_from_ui(idx_rot_button)
    #         result = self.control.execute_command("Setf1OverRateTxNum("+ str(idx_rot_button) +")")
    #         if result is not None:
    #             logging.info(f"Rotation velocity is set to {[10.0, 2.0, 1.0, 0.5][idx_rot_button]} deg/s")
    #         else:
    #             rotation_at_tem = self.control.client.Getf1OverRateTxNum()
    #             logging.error(f"Changes of rotation speed has failed!\nRotation at TEM is {[10.0, 2.0, 1.0, 0.5][rotation_at_tem]} deg/s")
    #             # TODO ? Make sure the right (eq to TEM status) button is checked
    
    # def toggle_mag_modes(self):
    #     idx_mag_button = self.tem_stagectrl.mag_modes.checkedId()
    #     if idx_mag_button == 4:
    #         self.parent.resetContrastBtn.clicked.emit()
    #     try:
    #         self.control.client.SelectFunctionMode(idx_mag_button)
    #         logging.info(f"Function Mode switched to {self.control.client.GetFunctionMode()[0]} (0=MAG, 2=Low MAG, 4=DIFF)")
    #     except Exception as e:
    #         logging.warning(f"Error occured when relaying 'SelectFunctionMode({idx_mag_button}': {e}")
    #         idx = self.control.client.GetFunctionMode()[0]
    #         if idx == 1: idx=0 # 0=MAG, 1=MAG2 -> Treat them as same
    #         self.tem_stagectrl.mag_modes.button(idx).setChecked(True)

    # def update_rotation_speed_idx_from_ui(self, idx_rot_button):
    #     self.cfg.rotation_speed_idx = idx_rot_button
    #     logging.debug(f"rotation_speed_idx updated to: {self.cfg.rotation_speed_idx} i.e. velocity is {[10.0, 2.0, 1.0, 0.5][self.cfg.rotation_speed_idx]} deg/s")

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
        pos = event.pos()
        ppos = self.parent.imageItem.mapToParent(pos)
        x, y = ppos.x(), ppos.y()
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
        # try:
        #     position = send_with_retries(self.control.client.GetStagePosition)
        # except Exception as e:
        #     logging.error(f"Error: {e}")
        #     return
        position = self.control.tem_status["stage.GetPos"] # in nm
        selected_item = self.tem_stagectrl.position_list.currentIndex()
        if selected_item < 5:
            position_aim = np.array((cfg_jf.lut.positions[selected_item]['xyz']), dtype=float) *1e3
        else:
            xtalinfo_selected = next((d for d in self.xtallist if d.get("gui_id") == selected_item - 4), None)        
            if xtalinfo_selected is None:
                logging.warning(f"Item ID {selected_item - 4:3d} is missing...")
                logging.warning(self.xtallist)
                return
            position_aim = xtalinfo_selected['position']
        dif_pos = [position_aim[0] - position[0], position_aim[1] - position[1]]
        distance = np.linalg.norm(np.array(dif_pos))
        if distance > 1e6:
            logging.warning(f"Vector too large! {distance/1e3:.1f} um")
            return
        try:
            self.control.client._send_message("SetStagePosition", dif_pos[0], dif_pos[1])
            # time.sleep(distance/1e5) # assumes speed of movement as > 100 um/s, should be updated with referring stage status!!
            logging.info(f"Moved from x:{position[0]*1e-3:6.2f} um, y:{position[1]*1e-3:6.2f} um") # debug
            logging.info(f"Moved by x:{dif_pos[0]*1e-3:6.2f} um, y:{dif_pos[1]*1e-3:6.2f} um")
            logging.info(f"Aimed position was x:{position_aim[0]*1e-3:3.2f} um, y:{position_aim[1]*1e-3:3.2f} um") # debug
        except RuntimeError:
            logging.warning('To set position, use specific version of tem_server.py!')
            self.tem_stagectrl.go_button.setEnabled(False)

    @Slot(str, str, list)
    def add_listedposition(self, color='red', status='new', position=None):
        if position is None:
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
                              "gui_label": label, "position": position, "status": status})
        logging.info(f"{new_id}: {position} is added to the list")

    @Slot(dict)
    def update_plotitem(self, info_d):
        # read unmeasured data
        if not 'spots' in info_d:
            logging.info(f"Item {info_d['gui_id']} is loaded")
            position = info_d["position"]
            marker = pg.ScatterPlotItem(x=[position[0]*1e-3], y=[position[1]*1e-3], brush='red')
            self.tem_stagectrl.position_list.addItem(info_d["gui_text"])
            self.tem_stagectrl.gridarea.addItem(marker)
            return
       
        # read measured/processed data
        if not "gui_id" in info_d:
            for gui_key in ["gui_id", "position", "gui_marker", "gui_label"]:
                info_d[gui_key] = info_d.get(gui_key, self.xtallist[-1][gui_key])
        if info_d["gui_id"] in [d.get('gui_id') for d in self.xtallist[1:]]:
            self.tem_stagectrl.position_list.removeItem(info_d["gui_id"] + 4)
            self.tem_stagectrl.gridarea.removeItem(info_d["gui_marker"])
            self.tem_stagectrl.gridarea.removeItem(info_d["gui_label"])
        elif info_d["gui_id"] is None or info_d["gui_id"] == 999:
            info_d["gui_id"] = self.tem_stagectrl.position_list.count() - 4

        # updated widget info
        position = info_d["position"]
        spots = np.array(info_d["spots"], dtype=float)
        axes = np.array(info_d["cell axes"], dtype=float)
        color_map = pg.colormap.get('plasma') # ('jet'); requires matplotlib
        color = color_map.map(spots[0]/spots[1], mode='qcolor')
        text = f"{info_d['dataid']}: " + " ".join(map(lambda x: f"{float(x):.1f}", info_d["lattice"])) + f", {spots[0]/spots[1]*100:.1f}%, processed"
        label = pg.TextItem(str(info_d["dataid"]), anchor=(0, 1))
        label.setFont(QFont('Arial', 8))
        label.setPos(position[0]*1e-3, position[1]*1e-3)
        marker = pg.ScatterPlotItem(x=[position[0]*1e-3], y=[position[1]*1e-3], brush=color, symbol='d')
        # represent orientation with cell-a axis, usually shortest
        angle = np.degrees(np.arctan2(axes[1], axes[0])) + 180
        length = np.linalg.norm(axes[:2]) / np.linalg.norm(axes[:3])
        arrow_a = CenterArrowItem(pos=(position[0]*1e-3, position[1]*1e-3), angle=angle,
                             headLen=10*length, tailLen=10*length, tailWidth=4*length, brush=color)
        # represent orientation with cell-b axis
        angle = np.degrees(np.arctan2(axes[4], axes[3])) + 180
        length = np.linalg.norm(axes[3:5]) / np.linalg.norm(axes[3:6])
        arrow_b = CenterArrowItem(pos=(position[0]*1e-3, position[1]*1e-3), angle=angle,
                             headLen=10*length, tailLen=10*length, tailWidth=4*length, brush=color)
        # represent orientation with cell-c axis
        angle = np.degrees(np.arctan2(axes[7], axes[6])) + 180
        length = np.linalg.norm(axes[6:8]) / np.linalg.norm(axes[6:9])
        arrow_c = CenterArrowItem(pos=(position[0]*1e-3, position[1]*1e-3), angle=angle,
                             headLen=10*length, tailLen=10*length, tailWidth=4*length, brush=color)
        # add updated items
        self.tem_stagectrl.gridarea.addItem(arrow_a)
        self.tem_stagectrl.gridarea.addItem(arrow_b)
        self.tem_stagectrl.gridarea.addItem(arrow_c)
        self.tem_stagectrl.position_list.addItem(text)
        self.tem_stagectrl.gridarea.addItem(marker)
        self.tem_stagectrl.gridarea.addItem(label)
        logging.info(f"Item {info_d['gui_id']} is updated")
        info_d["status"] = 'processed'
        self.xtallist.append(info_d)
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

    def update_ecount(self, cutoff=400, bins_set=20):
        ht = self.parent.tem_controls.voltage_spBx.value()
        cutoff = cutoff / 200 * ht
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
        data_sampled = image_deloverflow[np.where((image_deloverflow < high_thresh)&(image_deloverflow > cutoff))]
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
            magnification = self.lut.calibrated_magnification(magnification)
            self.control.beam_intensity["e_per_A2_sample"] = e_per_A2 * magnification**2
            self.tem_detector.e_incoming_display.setText(f'{self.control.beam_intensity["pa_per_cm2"]:.2f} pA/cm2/s, {self.control.beam_intensity["e_per_A2_sample"]:.2f} e/A2/s')
            logging.info(f'{self.control.beam_intensity["pa_per_cm2"]:.4f} pA/cm2/s, {self.control.beam_intensity["e_per_A2_sample"]:.4f} e/A2/s')
        except ValueError as e:
            self.tem_detector.e_incoming_display.setText(f'N/A')
            logging.warning(e)

    def take_snapshot(self, max_list=10):
        if self.control.tem_status["eos.GetFunctionMode"][0] == 4:
            logging.warning(f'Snaphot does not support Diff-mode at the moment!')
            return
        if len(self.snapshot_images) > max_list:
            self.tem_stagectrl.gridarea.removeItem(self.snapshot_images[0])
            self.snapshot_images.pop(0)
            logging.info(f'Oldest snapshot item was removed.')
            
        magnification = self.control.tem_status["eos.GetMagValue"] ## with unit
        calibrated_mag = self.lut.calibrated_magnification(magnification[2])
        position = self.control.client.GetStagePosition()
        beam_blank_state = self.control.client.GetBeamBlank()

        # if beam_blank_state == 1: # limited illumination mode; not ready
        #     image = np.copy(self.parent.imageItem.image)
        #     self.control.client.SetBeamBlank(0)
        #     self.control.tem_status["defl.GetBeamBlank"] = 0
        #     QTimer.singleShot(500, self.toggle_blank)
        #     while self.control.tem_status["defl.GetBeamBlank"] == 0:
        #         image += np.copy(self.parent.imageItem.image)
        # else:
        #     image = np.copy(self.parent.imageItem.image)
        image = np.copy(self.parent.imageItem.image)

        image_deloverflow = image[np.where(image < np.iinfo('int32').max-1)]
        low_thresh, high_thresh = np.percentile(image_deloverflow, (1, 99.999))

        # enhanced contrast
        margin = 0.4
        data_sampled = image_deloverflow[np.where((image_deloverflow < high_thresh)&(image_deloverflow > low_thresh))]
        uniqs, counts = np.unique(data_sampled//10, return_counts=True)
        approximate_average_count = uniqs[np.argmax(counts)].max() * 10
        low_thresh, high_thresh = approximate_average_count*(1-margin), approximate_average_count*(1+margin)
        logging.info(f"Snapshot displayed in enhanced contrast ({low_thresh}-{high_thresh})")
        # downsizing
        snapshot_image = pg.ImageItem(np.clip((np.nan_to_num(image) - low_thresh) / (high_thresh - low_thresh) * 255, 0, 255).astype(np.uint8))
        
        tr = QTransform()
        scale = cfg_jf.others.pixelsize*1e3/calibrated_mag
        tr.scale(scale, scale)
        tr.rotate(180 + self.lut.rotaxis_for_ht_degree(self.control.tem_status["ht.GetHtValue"], magnification=magnification[0]))
        if int(magnification[0]) >= 1500 : # Mag
            # tr.rotate(180+cfg_jf.others.rotation_axis_theta)
            tr.translate(-image.shape[0]/2, -image.shape[1]/2)
        else:
            # tr.rotate(180+cfg_jf.others.rotation_axis_theta_lm1200x)
            tr.translate(-self.lowmag_jump[0], -self.lowmag_jump[1])
        snapshot_image.setTransform(tr)
        self.tem_stagectrl.gridarea.addItem(snapshot_image)
        snapshot_image.setPos(position[0]*1e-3, position[1]*1e-3)
        snapshot_image.setZValue(-2)
        view = self.tem_stagectrl.gridarea.getViewBox()
        aspect_ratio = view.size().width()/view.size().height()
        y_range = position[1]*1e-3 - scale*image.shape[1]/2, position[1]*1e-3 + scale*image.shape[1]/2
        x_range = position[0]*1e-3 - scale*image.shape[1]/2*aspect_ratio, position[0]*1e-3 + scale*image.shape[1]/2*aspect_ratio
        view.setRange(xRange=x_range, yRange=y_range)
        self.snapshot_images.append(snapshot_image)
        # if globals.dev:
        #     self.snapshot_images[-1].mouseClickEvent = self.subimageMouseClickEvent
        # self.add_listedposition(color='red', status='new', position=position)
        # self.xtallist[-1]["snapshot"] = self.snapshot_image # copy will not work!!
        # self.xtallist[-1]["magnification"] = calibrated_mag
        logging.info(f'Snapshots were updated.')

    def subimageMouseClickEvent(self, event):
        if event.buttons() != Qt.LeftButton:
            logging.warning('Snapshot is not ready.')
            return
        if event.buttons() != Qt.LeftButton or not self.tem_tasks.centering_checkbox.isChecked():
            logging.warning('Centring is not ready.')
            return
        if self.control.tem_status["eos.GetFunctionMode"][0] == 4:
            logging.info('Centring should not be performed in Diff-MAG mode.')
            return
        position = self.control.tem_status["stage.GetPos"]
        if np.abs(position[4]) > 1:
            logging.info('Click-on-move for tilted-stage is not ready.')
            return
        pos = event.pos()
        ppos = self.snapshot_images[-1].mapToParent(pos)
        x, y = ppos.x(), ppos.y()
        logging.debug(f"{x:0.1f}, {y:0.1f}") # identical to the TEM-stage-position in um
        dx, dy = x*1e3 - position[0], y*1e3 - position[1]
        if np.abs(dx) > 3e5 or np.abs(dy) > 3e5:
            logging.info("Large movement (> 300 um) is not yet permitted for safety.")
            return

        if dx >= 0:
            self.control.trigger_movewithbacklash.emit(0, dx, cfg_jf.others.backlash[0])
        else:
            self.control.trigger_movewithbacklash.emit(1, dx, cfg_jf.others.backlash[0])
        time.sleep(np.abs(dx)/5e4) # assumes speed of movement as > 50 um/s
        if dy >= 0:
            self.control.trigger_movewithbacklash.emit(2, dy, cfg_jf.others.backlash[1])
        else:
            self.control.trigger_movewithbacklash.emit(3, dy, cfg_jf.others.backlash[1])

        logging.info(f'Move X: {dx/1e3:.1f} um,  Y: {dy/1e3:.1f} um')

    def synchronize_xtallist(self):
        if not self.dataReceiverReady:
            logging.warning("Other inquiry runnng")
            return
        # load mode
        if self.tem_stagectrl.position_list.count() == 5:
            self.process_receiver = ProcessedDataReceiver(self, host = "noether", mode=1)
            logging.info("Start session-metadata loading")
        # save mode
        elif len(self.xtallist) != 1:
            self.process_receiver = ProcessedDataReceiver(self, host = "noether", mode=2)
            logging.info("Start session-metadata saving")
        else:
            logging.warning("No data available")
            return

        self.datareceiver_thread = QThread()
        self.parent.threadWorkerPairs.append((self.datareceiver_thread, self.process_receiver))
        thread_manager.move_worker_to_thread(self.datareceiver_thread, self.process_receiver)
        self.datareceiver_thread.start()
        self.dataReceiverReady = False
        self.process_receiver.finished.connect(self.getdataReceiverReady)