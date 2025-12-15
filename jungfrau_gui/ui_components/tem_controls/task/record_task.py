import os
import time
import h5py
import logging
import numpy as np
from .task import Task
from PySide6.QtWidgets import QMessageBox
from PySide6.QtCore import Signal, Qt, QMetaObject
from simple_tem import TEMClient
from epoc import ConfigurationClient, auth_token, redis_host
from ..toolbox.tool import send_with_retries

from ....metadata_uploader.metadata_update_client import MetadataNotifier

from .... import globals

class RecordTask(Task):
    reset_rotation_signal = Signal()

    def __init__(self, control_worker, end_angle = 60, writer_event=None):
        super().__init__(control_worker, "Record")
        self.phi_dot = 0 # 10 deg/s
        self.control = control_worker
        self.tem_action = self.control.tem_action
        self.file_operations = self.tem_action.file_operations
        self.writer = writer_event
        self.end_angle = end_angle
        self.rotations_angles = []
        logging.info("RecordTask initialized")
        self.client = TEMClient(globals.tem_host, globals.tem_port, verbose=True)
        self.cfg = ConfigurationClient(redis_host(), token=auth_token())
        self.metadata_notifier = MetadataNotifier(host = globals.dataserver_host, port = globals.dataserver_port, verbose = False)

        self.reset_rotation_signal.connect(self.tem_action.reset_rotation_button)

    def run(self):
        logging.debug("RecordTask::run()")

        try:
            phi0 = self.client.GetTiltXAngle()
            phi1 = self.end_angle

            stage_rates = [10.0, 2.0, 1.0, 0.5]
            phi_dot_idx = self.client.Getf1OverRateTxNum()

            self.phi_dot = stage_rates[phi_dot_idx]
            
            self.client.Setf1OverRateTxNum(phi_dot_idx)
            time.sleep(1) 
            self.client.SetBeamBlank(0)
            time.sleep(0.5)

            # Send SetTiltXAngle with retry mechanism
            try:
                self.client.SetTiltXAngle(phi1)
            except Exception as e:
                logging.error(f"Unexpected error while sending SetTiltXAngle: {e}")
                self.client.SetBeamBlank(1)
                logging.warning(f"Beam blanked to protect sample!")
                if not self.client.is_rotating:
                    # If you can verify the stage is indeed not rotating, then bail out
                    return
                else:
                    logging.warning("Stage appears to be rotating despite the error.")
                    self.client.SetBeamBlank(0)
                    logging.warning("Unblanked the beam and ready to proceed...")
                    time.sleep(0.1)
            
            try:
                # Attempt to wait for the rotation to start
                logging.info("Waiting for stage rotation to start...")
                self.client.wait_until_rotate_starts()
                logging.info("Stage has initiated rotation")
            except Exception as rotation_error:
                logging.error(f"Stage rotation failed to start: {rotation_error}")
                return 

            #If enabled we start writing files 
            if self.writer is not None:
                self.writer[0]()
                logging.info("\033[1mAsynchronous writing of files is starting now...")

            t0 = time.time()
            try:
                while self.client.is_rotating:
                    try:
                        if self.control.interruptRotation:
                            logging.warning("*Interruption request*: Stopping the rotation...")
                            send_with_retries(self.client.StopStage)
                        pos = self.client.GetStagePosition()
                        t = time.time()
                        # difference in timers of TEM and GUI might cause small error and should be evaluated.
                        logging.info(f"{t - t0:10.6f}  {pos[3]:8.3f} deg")
                        self.rotations_angles.append([f'{t-t0:10.6f}', f'{pos[3]:8.3f}'])
                        time.sleep(0.1)
                    except Exception as e:
                        logging.error(f"Error getting stage position, skipping iteration: {e}")
                        continue
            except TimeoutError as te:
                logging.error(f"TimeoutError during rotation: {te}")
            except Exception as e:
                logging.error(f"Unexpected error caught for TEMClient::is_rotating(): {e}")                

            # Stop the file writing
            if self.writer is not None:
                logging.info(" ********************  Stopping Data Collection...")
                self.writer[1]()
            
            time.sleep(0.01)
            self.client.SetBeamBlank(1)

            try:
                phi1 = self.client.GetTiltXAngle()
            except Exception as e:
                logging.error(f"Failed to get final tilt angle: {e}")   

            logging.info(f"Stage rotation end at {phi1:.1f} deg.")
            
            # GUI updates; should be done before Auto-Reset, which modifies the stage status
            try:
                self.control.send_to_tem("#more", asynchronous = False)  # Update tem_status map and GUI
                logging.info('TEM-status received.')
            except Exception as e:
                logging.error("Error updating TEM status: {e}")
            
            # Add H5 info and file finalization; can be launched before stage-resetting
            if self.writer is not None:
                time.sleep(0.1)
                logging.info(" ******************** Adding Info to H5 over Server...")
                try:
                    beam_property = {
                        "beamcenter" : self.cfg.beam_center, 
                        "sigma_width" : self.control.beam_property_fitting[:2],
                        "angle" : self.control.beam_property_fitting[2],
                        "illumination" : self.control.beam_intensity,
                    }
                    send_with_retries(self.metadata_notifier.notify_metadata_update, 
                                      self.tem_action.visualization_panel.get_full_fname_str(), 
                                      self.control.tem_status, 
                                      beam_property,
                                      self.rotations_angles,
                                      self.cfg.threshold,
                                      retries=globals.max_retries_tagging, 
                                      delay=globals.inquiry_delay)

                except Exception as e:
                    logging.error(f"Metadata Update Error: {e}")

            # Enable auto reset of tilt
            if self.tem_action.tem_tasks.autoreset_checkbox.isChecked(): 
                logging.info("Return the stage tilt to zero.")
                try:
                    self.client.Setf1OverRateTxNum(0)
                    time.sleep(0.1) # Wait for the command to go through
                    self.tem_action.tem_stagectrl.move0deg.clicked.emit()
                    time.sleep(0.5) # Wait for the command to go through before checking rotation state
                except Exception as e:
                    logging.error(f"Unexpected error @ client.SetTiltXAngle(0): {e}") 
                    pass              
                
            # Waiting for the rotation to end
            try:
                while self.client.is_rotating:
                    time.sleep(0.2) # 0.01, but only supressing (reducing) output is necessary
            except Exception as e:
                logging.error(f'Error during "Auto-Reset" rotation: {e}')

            if self.writer is None:
                self.reset_rotation_signal.emit()
            else:
                self.tem_action.trigger_additem.emit('green', 'recorded', pos)
            time.sleep(0.5)
            print("------REACHED END OF TASK----------")

            # Restarting TEM polling
            if not self.tem_action.tem_tasks.connecttem_button.started:
                QMetaObject.invokeMethod(self.tem_action.tem_tasks.connecttem_button, "click", Qt.QueuedConnection)

            while not self.tem_action.tem_tasks.connecttem_button.started:
                time.sleep(0.1)

            logging.warning('Polling of TEM-info restarted.')

        except TimeoutError as e:
            # Log the timeout error and exit early to avoid writing files
            logging.error(f"Stage failed to start rotation: {e}")
            return

        except Exception as e:
            logging.error(f"Unexpected error while waiting for rotation to start: {e}")
        finally:
            self.client.SetBeamBlank(1)
            time.sleep(0.01)
            # Give back control to the TEM inspector for automatic updates of the UI
            self.tem_action.tem_controls.gaussian_user_forced_off = False

            self.reset_rotation_signal.emit()
