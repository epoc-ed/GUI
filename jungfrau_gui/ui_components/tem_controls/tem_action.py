import pyqtgraph as pg
import numpy as np

from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsLineItem
from PySide6.QtCore import QRectF, QObject, QTimer, Qt, QMetaObject, Signal, Slot
from PySide6.QtGui import QFont, QTransform

from .toolbox.tool import *
from .toolbox import config as cfg_jf

from .task.task_manager import *

from epoc import ConfigurationClient, auth_token, redis_host

from .connectivity_inspector import TEM_Connector
from ..file_operations.processresult_updater import ProcessedDataReceiver
from .tem_status_updater import TemUpdateWorker

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
        self.gui_id_offset = self.tem_stagectrl.position_list.count()
        self.control.tem_status["gui_id"] = self.tem_stagectrl.position_list.count() - self.gui_id_offset
        
        # connect buttons with tem-functions
        self.tem_tasks.connecttem_button.clicked.connect(self.toggle_connectTEM)
        # self.tem_tasks.gettem_button.clicked.connect(self.callGetInfoTask)
        # self.tem_tasks.centering_button.clicked.connect(self.toggle_centering)
        self.tem_tasks.rotation_button.clicked.connect(self.toggle_rotation)
        if globals.dev:  
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

        self.tem_stagectrl.movex10ump.clicked.connect(lambda: self.control.trigger_movewithbacklash.emit(0,  10000, cfg_jf.others.backlash[0], True))
        self.tem_stagectrl.movex10umn.clicked.connect(lambda: self.control.trigger_movewithbacklash.emit(1, -10000, cfg_jf.others.backlash[0], True))
        self.tem_stagectrl.move10degp.clicked.connect(lambda: self.control.trigger_movewithbacklash.emit(6,  10, cfg_jf.others.backlash[3], False))
        self.tem_stagectrl.move10degn.clicked.connect(lambda: self.control.trigger_movewithbacklash.emit(7, -10, cfg_jf.others.backlash[3], False))

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
        '''Enable or disable TEM-related UI controls efficiently.'''
        # Create groups of controls to enable/disable together
        # This reduces the number of individual setEnabled calls
        
        # Only check beam_center once
        scale_checkbox_enabled = enables and self.cfg.beam_center != [1, 1]
        self.tem_detector.scale_checkbox.setEnabled(scale_checkbox_enabled)
        
        # Group button operations to reduce UI updates
        button_groups = [
            self.tem_stagectrl.rb_speeds.buttons(),
            self.tem_stagectrl.movestages.buttons(),
            self.tem_stagectrl.mag_modes.buttons()
        ]
        
        # Batch enable/disable for each group
        for group in button_groups:
            for button in group:
                button.setEnabled(enables)
        
        # Call speed toggle only if enabling
        if enables:
            # Use a separate thread for potentially slow operations
            QTimer.singleShot(0, self.toggle_rb_speeds)
        
        # Combined setting for task controls
        task_controls = [
            # self.tem_tasks.gettem_button,
            # self.tem_tasks.gettem_checkbox, # Not works correctly
            # self.tem_tasks.centering_button,
            self.tem_tasks.centering_checkbox,
            self.tem_tasks.btnGaussianFit,
            # self.tem_tasks.beamAutofocus,
            self.tem_tasks.rotation_button,
            self.tem_tasks.input_start_angle,
            self.tem_tasks.update_end_angle,
            self.tem_stagectrl.blanking_button,
            self.tem_stagectrl.position_list,
            self.tem_stagectrl.go_button,
            self.tem_stagectrl.addpos_button
        ]

        if globals.dev:
            task_controls.append(self.tem_tasks.beamAutofocus)
        
        # Batch enable/disable task controls
        for control in task_controls:
            control.setEnabled(enables)
        
        # Safe screen button enabling
        try:
            self.tem_stagectrl.screen_button.setEnabled(enables)
        except AttributeError:
            pass
        
        # Developer-specific controls
        if globals.dev and enables:
            self.tem_detector.calc_e_incoming_button.setEnabled(True)
            self.tem_stagectrl.mapsnapshot_button.setEnabled(True)

    def reset_rotation_button(self):
        '''Reset rotation button to initial state.'''
        self.tem_tasks.rotation_button.setText("Rotation")
        self.tem_tasks.rotation_button.started = False

    def toggle_connectTEM(self):
        """Toggle TEM connection with performance optimizations."""
        if not self.tem_tasks.connecttem_button.started:
            # Starting connection
            
            # Pre-cache button reference
            button = self.tem_tasks.connecttem_button
            
            # Try to set voltage value safely without multiple lookups
            try:
                ht_value = self.control.tem_status.get("ht.GetHtValue", 200000.0)
                self.tem_controls.voltage_spBx.setValue(ht_value/1e3)
            except TypeError:
                pass
            
            # Initialize connection
            self.control.init.emit()
            
            # Create thread and worker in one block
            self.connect_thread = QThread()
            self.connect_thread.setObjectName("TEM_Connector Thread")
            self.temConnector = TEM_Connector()
            
            # Track thread/worker pair
            self.parent.threadWorkerPairs.append((self.connect_thread, self.temConnector))
            
            # Initialize once
            self.initializeWorker(self.connect_thread, self.temConnector)
            
            # Start thread
            self.connect_thread.start()
            self.connectorWorkerReady = True
            logging.info("Starting tem-connecting process")
            
            # Update button state
            button.started = True
            
            # Start timer with polling frequency
            polling_ms = self.tem_tasks.polling_frequency.value()
            self.timer_tem_connexion.start(polling_ms)
            
            # Get initial TEM state (non-blocking)
            QTimer.singleShot(0, lambda: self.control.send_to_tem("#init", asynchronous=True))
            
            # Update overlays efficiently
            self._update_overlays()
        else:
            # Stopping connection
            button = self.tem_tasks.connecttem_button
            
            # Update button appearance
            button.setStyleSheet('background-color: rgb(53, 53, 53); color: white;')
            button.setText("Check TEM Connection")
            button.started = False
            
            # Stop timer first to prevent new tasks
            self.timer_tem_connexion.stop()
            
            # Stop worker and thread
            self.parent.stopWorker(self.connect_thread, self.temConnector)
            
            # Reset worker and thread
            self.temConnector, self.connect_thread = thread_manager.reset_worker_and_thread(
                self.temConnector, self.connect_thread
            )

    def _update_overlays(self):
        """Helper method to update overlays efficiently."""
        # Remove existing overlays
        if self.main_overlays[0] is not None:
            for overlay in self.main_overlays:
                self.parent.plot.removeItem(overlay)
        
        # Get voltage once
        voltage = self.parent.tem_controls.voltage_spBx.value() * 1e3
        
        # Get new overlays
        self.main_overlays = self.lut.overlays_for_ht(voltage)
        
        # Add new overlays
        for overlay in self.main_overlays:
            self.parent.plot.addItem(overlay)

    def initializeWorker(self, thread, worker):
        """Initialize worker with thread connections."""
        # Move worker to thread
        thread_manager.move_worker_to_thread(thread, worker)
        
        # Connect signals directly
        worker.finished.connect(self.updateTemControls)
        worker.finished.connect(self.getConnectorReady)

    def getConnectorReady(self):
        """Mark connector as ready."""
        # Simple flag setter, no performance issues
        self.connectorWorkerReady = True

    def checkTemConnexion(self):
        """Check TEM connection with performance optimizations."""
        # Short-circuit if worker isn't ready
        if not self.connectorWorkerReady:
            return
        
        # Mark as not ready before invoking
        self.connectorWorkerReady = False
        
        # Use invokeMethod to run in worker's thread
        QMetaObject.invokeMethod(self.temConnector, "run", Qt.QueuedConnection)

    def updateTemControls(self, tem_connected):
        """Update TEM controls based on connection status."""
        # Cache button reference
        button = self.tem_tasks.connecttem_button
        
        if tem_connected:
            # Connected state
            button.setStyleSheet('background-color: green; color: white;')
            button.setText("Connection OK")
        else:
            # Disconnected state
            button.setStyleSheet('background-color: red; color: white;')
            button.setText("Disconnected")
        
        # Enable/disable controls 
        QTimer.singleShot(0, lambda: self.enabling(tem_connected))
        
        # Get TEM info if connected, but in a separate thread
        if tem_connected:
            # Ensure we have a worker set up
            if not hasattr(self, 'tem_threads'):
                self.setup_tem_update_worker()
            
            # Use the worker to process TEM info
            QMetaObject.invokeMethod(self.update_worker, "process_tem_info", Qt.QueuedConnection)

    def setup_tem_update_worker(self):
        """Set up a worker thread for TEM updates."""
        # Create worker and thread
        self.update_thread = QThread()
        self.update_thread.setObjectName("UI_Updater Thread")
        self.update_worker = TemUpdateWorker(self.control)
        
        # Track thread/worker pair
        self.parent.threadWorkerPairs.append((self.update_thread, self.update_worker))

        # Move worker to thread
        self.update_worker.moveToThread(self.update_thread)
        logging.info(f"\033[1m{self.update_worker.task_name}\033[0m\033[34m is Ready!")

        # Connect signals
        self.update_worker.status_updated.connect(self.control.update_tem_status)
        self.update_worker.finished.connect(self.on_update_finished)
        
        # Start thread
        self.update_thread.start()
        
        # Store reference to keep thread alive
        self.tem_threads = {'update_thread': self.update_thread, 'update_worker': self.update_worker}

    def on_update_finished(self):
        """Function that does nothing, just catches the finished signal."""
        pass

    def callGetInfoTask(self):
        """Call get info task with optimizations."""
        # Initialize control
        self.control.init.emit()
        
        # Get checkbox state once
        get_tem_info = 'Y' if self.tem_tasks.gettem_checkbox.isChecked() else 'N'
        
        # Trigger info gathering
        self.control.trigger_getteminfo.emit(get_tem_info)

    """ @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@ """
    """ @@@@@@@@@@@ UI Update with TEM latest status @@@@@@@@@@ """
    """ @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@ """

    def on_tem_update(self):
        """Update GUI with TEM status in a non-blocking way."""
        logging.debug("Starting GUI update with latest TEM Status...")
        
        # Start the chunked update process
        QTimer.singleShot(0, self._update_tem_gui_step1)

    def _update_tem_gui_step1(self):
        """First step of GUI update process."""
        try:
            # Cache the tem_status reference
            tem_status = self.control.tem_status
            
            # Update voltage display
            ht_V = tem_status.get("ht.GetHtValue", 0)
            if ht_V is not None:
                self.parent.tem_controls.voltage_spBx.setValue(ht_V/1e3)
            
            # Update angle display
            pos_list = tem_status.get("stage.GetPos") or [None, None, None, None, None]
            angle_x = pos_list[3]  # guaranteed index
            if angle_x is not None:
                self.tem_tasks.input_start_angle.setValue(angle_x)
                if globals.dev:
                    if self.tem_tasks.mirror_angles_checkbox.isChecked():
                        end_angle = (np.abs(angle_x) - 2) * np.sign(angle_x) * -1 # '-2' for safe, could be updated depending on the absolute value
                        self.tem_tasks.update_end_angle.setValue(end_angle)
            
            # Store beam sigmas and angle
            self.control.beam_property_fitting = [
                self.tem_controls.sigma_x_spBx.value(), 
                self.tem_controls.sigma_y_spBx.value(),
                self.tem_controls.angle_spBx.value()
            ]
                                          
        except Exception as e:
            logging.error(f"Error in GUI update step 1: {e}")
        
        # Schedule next step
        QTimer.singleShot(0, self._update_tem_gui_step2)

    def _update_tem_gui_step2(self):
        """Second step of GUI update process."""
        try:
            # Cache references
            tem_status = self.control.tem_status
            
            # Get function mode
            Mag_idx_list = tem_status.get("eos.GetFunctionMode") or [None, None]
            Mag_idx = Mag_idx_list[0]
            # Get magnification value
            mag_value_list = tem_status.get("eos.GetMagValue") or [None, None, None]
            mag_value = mag_value_list[2]
            
            # Process mode-specific logic
            if Mag_idx is not None:
                if Mag_idx in [0, 1, 2]:
                    # MAG mode
                    self.tem_detector.input_magnification.setText(str(mag_value))
                elif Mag_idx == 4:
                    # DIFF mode
                    self.tem_detector.input_det_distance.setText(str(mag_value))
        except Exception as e:
            logging.error(f"Error in GUI update step 2: {e}")
        
        # Schedule next step
        QTimer.singleShot(0, self._update_tem_gui_step3)

    def _update_tem_gui_step3(self):
        """Third step of GUI update process."""
        try:
            # Cache references
            tem_status = self.control.tem_status
            client = self.control.client

            Mag_idx_list = tem_status.get("eos.GetFunctionMode") or [None, None]
            Mag_idx = Mag_idx_list[0]
            
            # Update scale overlay based on mode
            if Mag_idx is not None:
                if Mag_idx in [0, 1, 2]:
                    # MAG mode
                    img = self.parent.imageItem.image
                    if img is not None:
                        shape = img.shape
                        self.drawscale_overlay(xo=shape[1]*0.85, yo=shape[0]*0.1)
                elif Mag_idx == 4:
                    # DIFF mode
                    self.drawscale_overlay(xo=self.cfg.beam_center[0], yo=self.cfg.beam_center[1])
            
            # Get beam blank state
            beam_blank_state = client.GetBeamBlank()
            tem_status["defl.GetBeamBlank"] = beam_blank_state
        except Exception as e:
            logging.error(f"Error in GUI update step 3: {e}")
        
        # Schedule next step
        QTimer.singleShot(0, self._update_tem_gui_step4)

    def _update_tem_gui_step4(self):
        """Fourth step of GUI update process."""
        try:
            # Cache references
            tem_status = self.control.tem_status
            Mag_idx_list = tem_status.get("eos.GetFunctionMode") or [None, None]
            Mag_idx = Mag_idx_list[0]
            
            # Skip if we don't have valid mode information
            if Mag_idx is None:
                QTimer.singleShot(0, self._update_tem_gui_step5)
                
            # Check if mode changed
            mode_changed = Mag_idx != self.last_mag_mode
            if mode_changed:
                auto_contrast_btn = self.parent.autoContrastBtn
                gaussian_fit_btn = self.tem_tasks.btnGaussianFit
                
                # Split mode handling into substeps to reduce blocking
                if Mag_idx in [0, 1, 2]:
                    # Schedule MAG mode handling in a separate timer
                    QTimer.singleShot(0, lambda: self._handle_mag_mode(
                        Mag_idx, auto_contrast_btn, gaussian_fit_btn))
                elif Mag_idx == 4:
                    # Schedule DIFF mode handling in a separate timer
                    QTimer.singleShot(0, lambda: self._handle_diff_mode(
                        Mag_idx, auto_contrast_btn, gaussian_fit_btn))
                
                # Update last mode
                self.last_mag_mode = Mag_idx
        except Exception as e:
            logging.error(f"Error in GUI update step 4: {e}")
        
        # Schedule next step
        QTimer.singleShot(5, self._update_tem_gui_step5)

    def _handle_mag_mode(self, Mag_idx, auto_contrast_btn, gaussian_fit_btn):
        """Handle MAG mode UI updates."""
        try:
            # MAG mode handling
            if not auto_contrast_btn.started:
                auto_contrast_btn.clicked.emit()
                
            # Just pause the Gaussian Fit in MAG mode if it's currently ON
            if gaussian_fit_btn.started and not self.tem_controls._fit_paused:
                self.tem_controls.toggle_gaussianFit_beam(by_user=False, pause_only=True)
                
            # Update UI state
            if Mag_idx in mag_indices:
                self.tem_stagectrl.mag_modes.button(mag_indices[Mag_idx]).setChecked(True)
        except Exception as e:
            logging.error(f"Error handling MAG mode: {e}")

    def _handle_diff_mode(self, Mag_idx, auto_contrast_btn, gaussian_fit_btn):
        """Handle DIFF mode UI updates."""
        try:
            # DIFF mode handling
            if auto_contrast_btn.started:
                self.parent.resetContrastBtn.clicked.emit()
                
            # Resume or start Gaussian Fit in DIFF mode if it's not user-forced-off
            if not self.tem_controls.gaussian_user_forced_off:
                if gaussian_fit_btn.started:
                    # It's paused, so resume it
                    self.tem_controls.resume_gaussian_fit(gaussian_fit_btn, "Stop Fitting")
                else:
                    # It's not started, so start it
                    self.tem_controls.toggle_gaussianFit_beam(by_user=False)
                
            # Update UI state
            if Mag_idx in mag_indices:
                self.tem_stagectrl.mag_modes.button(mag_indices[Mag_idx]).setChecked(True)
        except Exception as e:
            logging.error(f"Error handling DIFF mode: {e}")

    def _update_tem_gui_step5(self):
        """Fifth step of GUI update process."""
        try:
            # Cache references
            tem_status = self.control.tem_status
            Mag_idx_list = tem_status.get("eos.GetFunctionMode") or [None, None]
            Mag_idx = Mag_idx_list[0]
            beam_blank_state = tem_status.get("defl.GetBeamBlank", 0)
            
            # Handle beam blank logic in a separate timer
            QTimer.singleShot(0, lambda: self._handle_beam_blank(Mag_idx, beam_blank_state))
            
            # Update rotation speed UI in a separate timer
            QTimer.singleShot(5, self._update_rotation_speed)
        except Exception as e:
            logging.error(f"Error in GUI update step 5: {e}")
        
        # Schedule final step
        QTimer.singleShot(10, self._update_tem_gui_final)

    def _handle_beam_blank(self, Mag_idx, beam_blank_state):
        """Handle beam blank state."""
        try:
            if beam_blank_state == 1:
                # Beam is blanked - turn off Gaussian Fit if running
                if self.tem_tasks.btnGaussianFit.started and not self.tem_controls._fit_paused:
                    # self.tem_controls.toggle_gaussianFit_beam(by_user=False)
                    self.tem_controls.toggle_gaussianFit_beam(by_user=False, pause_only=True)
            elif Mag_idx == 4 and not self.tem_controls.gaussian_user_forced_off:
                # Beam is unblanked and in DIFF mode - ensure Gaussian Fit is on
                if not self.tem_tasks.btnGaussianFit.started:
                    self.tem_controls.toggle_gaussianFit_beam(by_user=False)
                else:
                    self.tem_controls.resume_gaussian_fit(btn=self.tem_tasks.btnGaussianFit,
                                                          running_text="Stop Fitting")
        except Exception as e:
            logging.error(f"Error handling beam blank: {e}")

    def _update_rotation_speed(self):
        """Update rotation speed UI elements."""
        try:
            # Check if user recently changed this value
            user_override = False
            if hasattr(self, 'last_user_rotation_change'):
                # Only respect user changes for a certain time window (e.g., 3 seconds)
                time_since_change = time.time() - self.last_user_rotation_change['timestamp']
                if time_since_change < 1.0:  # 1 second override window
                    user_override = True
                    # Keep the UI matching what the user selected
                    idx = self.last_user_rotation_change['value']
                    self.tem_stagectrl.rb_speeds.button(idx).setChecked(True)
            
            # Only update from TEM status if no recent user override
            if not user_override:
                # Cache references
                tem_status = self.control.tem_status
                
                # Update rotation speed UI
                rotation_speed_index = tem_status.get("stage.Getf1OverRateTxNum")
                if rotation_speed_index in [0, 1, 2, 3]:
                    self.tem_stagectrl.rb_speeds.button(rotation_speed_index).setChecked(True)
        except Exception as e:
            logging.error(f"Error updating rotation speed: {e}")

    def _update_tem_gui_final(self):
        """Final step of GUI update process."""
        try:
            # Update position plot
            self.plot_currentposition()

            # Update rotation button text if needed
            rotation_button = self.tem_tasks.rotation_button
            if not rotation_button.started:
                rotation_button.setText(
                    "Rotation/Record" if self.tem_tasks.withwriter_checkbox.isChecked() else "Rotation"
                )
            
            logging.debug("GUI update with latest TEM Status completed")
        except Exception as e:
            logging.error(f"Error in GUI final update step: {e}")

    """ @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@ """

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
            # client.SetBeamBlank(1)
            threading.Thread(target=client.SetBeamBlank, args=(1,), daemon=True).start()
            blank_button.setText("Unblank beam")
            blank_button.setStyleSheet('background-color: orange; color: white;')
        else:
            # Unblank the beam
            # client.SetBeamBlank(0)
            threading.Thread(target=client.SetBeamBlank, args=(0,), daemon=True).start()
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
        
        try:
            # Execute command in a thread to avoid blocking
            threading.Thread(target=self.control.client.Setf1OverRateTxNum, args=(idx_rot_button,), daemon=True).start()
            
            # Update the local status to match what the user just selected
            self.control.tem_status["stage.Getf1OverRateTxNum"] = idx_rot_button
            
            # Set a "user override" flag with a timestamp
            self.last_user_rotation_change = {
                'value': idx_rot_button,
                'timestamp': time.time()
            }
            
            logging.info(f"Rotation velocity is set to {speed_values[idx_rot_button]} deg/s")
        except Exception as e:
            # Only get TEM status if command failed
            rotation_at_tem = self.control.execute_command("Getf1OverRateTxNum")
            if rotation_at_tem is not None:
                self.update_rotation_speed_idx_from_ui(rotation_at_tem)
            logging.error(f"Changes of rotation speed has failed!\nRotation at TEM is {speed_values[rotation_at_tem]} deg/s")

    def toggle_mag_modes(self):
        """Toggle magnification modes with error handling."""
        # Get checked button ID once
        idx_mag_button = self.tem_stagectrl.mag_modes.checkedId()
        
        # Early reset contrast if needed
        if idx_mag_button == 4:
            self.parent.resetContrastBtn.clicked.emit()
        
        try:
            # Send command once
            threading.Thread(target=self.control.client.SelectFunctionMode, args=(idx_mag_button,)).start()
            self.control.tem_status["eos.GetFunctionMode"] = idx_mag_button # TO_TEST: Live update
            logging.info(f"Function Mode switched to {idx_mag_button} (0=MAG, 2=Low MAG, 4=DIFF)")
        except Exception as e:
            logging.warning(f"Error occurred when relaying 'SelectFunctionMode({idx_mag_button})': {e}")
            
            # Only get function mode if there was an error
            idx_list = self.control.execute_command("GetFunctionMode")
            idx = idx_list[0]
            
            # Normalize function mode (treat MAG and MAG2 as same)
            if idx == 1:
                idx = 0

            logging.error(f"Changes of Function Mode has failed!\nActive mode at TEM is {idx_mag_button} (0=MAG, 2=Low MAG, 4=DIFF)")
            # Update UI to reflect actual state
            self.tem_stagectrl.mag_modes.button(idx).setChecked(True)

    def update_rotation_speed_idx_from_ui(self, idx_rot_button):
        self.cfg.rotation_speed_idx = idx_rot_button
        logging.debug(f"rotation_speed_idx updated to: {self.cfg.rotation_speed_idx} i.e. velocity is {[10.0, 2.0, 1.0, 0.5][self.cfg.rotation_speed_idx]} deg/s")

    def toggle_rotation(self):
        if not self.tem_tasks.rotation_button.started:
            self.control.init.emit()
            # self.control.send_to_tem("#info")
            QTimer.singleShot(0, lambda: self.control.send_to_tem("#info", asynchronous=True))
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
        if selected_item <= self.gui_id_offset:
            position_aim = np.array((cfg_jf.lut.positions[selected_item]['xyz']), dtype=float) *1e3
        else:
            xtalinfo_selected = next((d for d in self.xtallist if d.get("gui_id") == selected_item - self.gui_id_offset), None)        
            if xtalinfo_selected is None:
                logging.warning(f"Item ID {selected_item - self.gui_id_offset:3d} is missing...")
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
        new_id = self.tem_stagectrl.position_list.count() - self.gui_id_offset
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
        self.control.tem_status["gui_id"] = new_id

    @Slot(dict)
    def update_plotitem(self, info_d):
        if info_d is None:
            logging.error(f"Item is not updated by {info_d}")
            return

        prev_xtalid = next((i for i, item in enumerate(self.xtallist[1:]) if item['gui_id'] == info_d["gui_id"]), None)
        if prev_xtalid is not None:
            logging.info(f"Item {info_d['gui_id']} will be overwritten")
            if info_d["gui_id"] is None or info_d["gui_id"] == 999:
                info_d["gui_id"] = self.tem_stagectrl.position_list.count() - self.gui_id_offset
            self.tem_stagectrl.position_list.removeItem(self.xtallist[prev_xtalid+1]['gui_id'] + self.gui_id_offset)
            if 'gui_marker' in self.xtallist[prev_xtalid+1]:
                self.tem_stagectrl.gridarea.removeItem(self.xtallist[prev_xtalid+1]["gui_marker"])
                self.tem_stagectrl.gridarea.removeItem(self.xtallist[prev_xtalid+1]["gui_label"])
            del self.xtallist[prev_xtalid+1]
        else:
            for gui_key in ["gui_id", "position", "gui_marker", "gui_label"]:
                info_d[gui_key] = info_d.get(gui_key, self.xtallist[-1][gui_key])
        
        position = info_d["position"]
        # read unmeasured data
        if 'spots' not in info_d:
            logging.info(f"Item {info_d['gui_id']} is loaded")
            marker = pg.ScatterPlotItem(x=[position[0]*1e-3], y=[position[1]*1e-3], brush='red')
            self.tem_stagectrl.position_list.insertItem(info_d["gui_id"] + self.gui_id_offset, info_d["gui_text"])
            label = pg.TextItem(str(info_d["gui_id"]), anchor=(0, 1))
        else:
        # read measured/processed data
        # updated widget info
            spots = np.array(info_d["spots"], dtype=float)
            axes = np.array(info_d["cell axes"], dtype=float)
            color_map = pg.colormap.get('plasma') # ('jet'); requires matplotlib
            color = color_map.map(spots[0]/spots[1], mode='qcolor')
            text = f"{info_d['dataid']}: " + " ".join(map(lambda x: f"{float(x):.1f}", info_d["lattice"])) + f", {spots[0]/spots[1]*100:.1f}%, processed"
            marker = pg.ScatterPlotItem(x=[position[0]*1e-3], y=[position[1]*1e-3], brush=color, symbol='d')
            label = pg.TextItem(str(info_d["dataid"]), anchor=(0, 1))
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
            if spots[0]/spots[1] > 0.05: # assumes the lower spot-indexing rate as unsuccessful
                self.tem_stagectrl.gridarea.addItem(arrow_a)
                self.tem_stagectrl.gridarea.addItem(arrow_b)
                self.tem_stagectrl.gridarea.addItem(arrow_c)
            self.tem_stagectrl.position_list.insertItem(info_d["gui_id"] + self.gui_id_offset, text)
            logging.info(f"Item {info_d['gui_id']}:{info_d["dataid"]} is updated")
            info_d["status"] = 'processed'

        self.tem_stagectrl.gridarea.addItem(marker)
        label.setFont(QFont('Arial', 8))
        label.setPos(position[0]*1e-3, position[1]*1e-3)
        self.tem_stagectrl.gridarea.addItem(label)
        info_d["gui_marker"] = marker
        info_d["gui_label"] = label
        self.xtallist.append(info_d)
        logging.debug(self.xtallist)
        self.control.tem_status["gui_id"] = self.tem_stagectrl.position_list.count() - self.gui_id_offset
    
    def plot_listedposition(self, color='gray'):
        xy_list = [self.tem_stagectrl.position_list.itemText(i).split()[1:-2] for i in range(self.tem_stagectrl.position_list.count())]
        xy_list = np.array(xy_list).T
        self.tem_stagectrl.gridarea.addItem(pg.ScatterPlotItem(x=xy_list[0], y=xy_list[1], brush=color))

    def plot_currentposition(self, color='yellow'):
        if self.marker != None:
            self.tem_stagectrl.gridarea.removeItem(self.marker)
        position = self.control.tem_status.get("stage.GetPos", [0, 0, 0, 0, 0])
        if position is not None:
            self.marker = pg.ScatterPlotItem(x=[position[0]*1e-3], y=[position[1]*1e-3], brush=color)
            self.tem_stagectrl.gridarea.addItem(self.marker)
            view = self.tem_stagectrl.gridarea.getViewBox()
            width = view.viewRange()[0][1] - view.viewRange()[0][0]
            height = view.viewRange()[1][1] - view.viewRange()[1][0]
            x_range = position[0]*1e-3 - width/2, position[0]*1e-3 + width/2
            y_range = position[1]*1e-3 - height/2, position[1]*1e-3 + height/2
            view.setRange(xRange=x_range, yRange=y_range,padding=0)
            # Update position plot colored by spotcount
            if globals.dev:
                spotchart = self.tem_stagectrl.spotchartItem.image
                position_on_chart = np.array([(self.tem_stagectrl.radius2 + position[0]*1e-3) // self.tem_stagectrl.grid_resolution, (self.tem_stagectrl.radius2 + position[1]*1e-3) // self.tem_stagectrl.grid_resolution], dtype=int)
                spotchart[position_on_chart[1], position_on_chart[0]] = self.visualization_panel.spotcount
                self.tem_stagectrl.spotchartItem.setImage(spotchart)

    @Slot()
    def inquire_processed_data(self):
        if self.dataReceiverReady:
            self.process_receiver = ProcessedDataReceiver(self, host = "noether")            
            self.datareceiver_thread = QThread()
            self.datareceiver_thread.setObjectName("Data_Receiver Thread")
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
        # estimate the number of incoming electrons with the most frequent bin of the count-histogram.
        ht = self.parent.tem_controls.voltage_spBx.value()
        cutoff = cutoff / 200 * ht
        pixel = cfg_jf.others.pixelsize
        Mag_idx = self.control.tem_status["eos.GetFunctionMode"][0] = self.control.client.GetFunctionMode()[0]
        if Mag_idx == 4:
            logging.warning("Brightness should be calculated in imaging mode")
            return
        frame = self.visualization_panel.jfjoch_client._lots_of_images / 3600 # usually 20, with 100 frame-sum
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

    def take_snapshot(self, max_list=50):
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
        snapshot_image.setZValue(-3) # bottom layer
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
            self.control.trigger_movewithbacklash.emit(0, dx, cfg_jf.others.backlash[0], False)
        else:
            self.control.trigger_movewithbacklash.emit(1, dx, cfg_jf.others.backlash[0], False)
        time.sleep(np.abs(dx)/5e4) # assumes speed of movement as > 50 um/s
        if dy >= 0:
            self.control.trigger_movewithbacklash.emit(2, dy, cfg_jf.others.backlash[1], False)
        else:
            self.control.trigger_movewithbacklash.emit(3, dy, cfg_jf.others.backlash[1], False)

        logging.info(f'Move X: {dx/1e3:.1f} um,  Y: {dy/1e3:.1f} um')

    def synchronize_xtallist(self):
        if not self.dataReceiverReady:
            logging.warning("Other inquiry runnng")
            return
        # load mode
        if self.tem_stagectrl.position_list.count() == self.gui_id_offset + 1:
            self.process_receiver = ProcessedDataReceiver(self, host = "noether", mode=1)
            logging.info("Start session-metadata loading")
            self.control.tem_status["gui_id"] = self.tem_stagectrl.position_list.count() - self.gui_id_offset
        # save mode
        elif len(self.xtallist) != 1:
            self.process_receiver = ProcessedDataReceiver(self, host = "noether", mode=2)
            logging.info("Start session-metadata saving")
        else:
            logging.warning("No data available")
            return

        self.datareceiver_thread = QThread()
        self.datareceiver_thread.setObjectName("Data_Receiver Thread")
        self.parent.threadWorkerPairs.append((self.datareceiver_thread, self.process_receiver))
        thread_manager.move_worker_to_thread(self.datareceiver_thread, self.process_receiver)
        self.datareceiver_thread.start()
        self.dataReceiverReady = False
        self.process_receiver.finished.connect(self.getdataReceiverReady)