import os
import time
import h5py
import logging
import numpy as np
from .task import Task
from .dectris2xds import XDSparams
from PySide6.QtWidgets import QMessageBox, QProgressDialog, QApplication
from PySide6.QtCore import Signal, Qt, QMetaObject

from simple_tem import TEMClient
from epoc import ConfigurationClient, auth_token, redis_host
from ..toolbox.tool import send_with_retries

from ....metadata_uploader.metadata_update_client import MetadataNotifier

from .... import globals

class RecordTask(Task):
    reset_rotation_signal = Signal()

    # def __init__(self, control_worker, end_angle = 60, log_suffix = 'RotEDlog_test', writer_event=None, standard_h5_recording=False):
    def __init__(self, control_worker, end_angle = 60, log_suffix = 'RotEDlog_test', writer_event=None):
        super().__init__(control_worker, "Record")
        self.phi_dot = 0 # 10 deg/s
        self.control = control_worker
        self.tem_action = self.control.tem_action
        self.file_operations = self.tem_action.file_operations
        self.writer = writer_event
        self.end_angle = end_angle
        self.rotations_angles = []
        self.log_suffix = log_suffix
        logging.info("RecordTask initialized")
        self.client = TEMClient(globals.tem_host, 3535,  verbose=True)
        self.cfg = ConfigurationClient(redis_host(), token=auth_token())
        self.metadata_notifier = MetadataNotifier(host = "noether", port = 3463, verbose = False)
        # self.standard_h5_recording = standard_h5_recording

        self.reset_rotation_signal.connect(self.tem_action.reset_rotation_button)

    def run(self):
        logging.debug("RecordTask::run()")

        if self.writer is not None:
            try:
                self.cfg.data_dir.mkdir(parents=True, exist_ok=True) #TODO! when do we create the data_dir?
            except Exception as e:
                # Handle any unexpected errors
                error_message = f"An unexpected error occurred: {e}"
                QMessageBox.critical(self, "Error", error_message)

        try:
            logfile = None  # Initialize logfile to None
            
            phi0 = self.client.GetTiltXAngle()
            phi1 = self.end_angle

            stage_rates = [10.0, 2.0, 1.0, 0.5]
            phi_dot_idx = self.client.Getf1OverRateTxNum()

            self.phi_dot = stage_rates[phi_dot_idx]

            # Interrupting TEM Polling
            if self.tem_action.tem_tasks.connecttem_button.started:
                QMetaObject.invokeMethod(self.tem_action.tem_tasks.connecttem_button, "click", Qt.QueuedConnection)

            while self.tem_action.tem_tasks.connecttem_button.started:
                time.sleep(0.1)

            logging.warning("TEM Connect button is OFF now.\nPolling is interrupted during data collection!")

            # Disable the Gaussian Fitting
            QMetaObject.invokeMethod(self.tem_action.tem_controls, 
                                    "disableGaussianFitButton", 
                                    Qt.QueuedConnection
            )
            logging.warning("Gaussian Fitting is disabled during rotation/record task!")
            
            # Attempt to open the logfile and catch potential issues
            try:
                logfile = open(self.log_suffix + '.log', 'w')
                logging.info("\n\n\n---------OPEN LOG-----------------\n\n\n")
            
                logfile.write("# TEM Record\n")
                logfile.write("# TIMESTAMP: " + time.strftime("%Y/%m/%d %H:%M:%S", time.localtime()) + "\n")
                logfile.write(f"# Initial Angle:           {phi0:6.3f} deg\n")
                logfile.write(f"# Final Angle (scheduled): {phi1:6.3f} deg\n")
                logfile.write(f"# angular Speed:           {self.phi_dot:6.2f} deg/s\n")
                logfile.write(f"# magnification:           {self.control.tem_status['eos.GetMagValue_MAG'][0]:<6d} x\n")
                logfile.write(f"# detector distance:       {self.control.tem_status['eos.GetMagValue_DIFF'][0]:<6d} mm\n")
                # Beam parameters
                try:
                    logfile.write(f"# spot_size:               {self.client.GetSpotSize()}\n")
                    logfile.write(f"# alpha_angle:             {self.client.GetAlpha()}\n")
                except Exception as e:
                    logging.error(f"Error retrieving beam parameters: {e}")
                # Aperture sizes
                try:
                    logfile.write(f"# CL#:                     {self.client.GetAperatureSize(1)}\n")
                    logfile.write(f"# SA#:                     {self.client.GetAperatureSize(4)}\n")
                except Exception as e:
                    logging.error(f"Error retrieving aperture sizes: {e}")
                # Lens parameters
                try:
                    logfile.write(f"# brightness:              {self.client.GetCL3()}\n")
                    logfile.write(f"# diff_focus:              {self.client.GetIL1()}\n")
                    logfile.write(f"# IL_focus:                {self.client.GetILs()}\n")
                    logfile.write(f"# PL_align:                {self.client.GetPLA()}\n")
                except Exception as e:
                    logging.error(f"Error retrieving lens parameters: {e}")
                # Stage position
                try:
                    logfile.write(f"# stage_position:          {self.client.GetStagePosition()}\n")
                except Exception as e:
                    logging.error(f"Error retrieving stage position: {e}")
            except FileNotFoundError as fnf_error:
                logging.error(f"FileNotFoundError: Directory does not exist for logfile: {fnf_error}")
                return
            except PermissionError as perm_error:
                logging.error(f"PermissionError: No write access to logfile: {perm_error}")
                # return
            except Exception as e:
                logging.error(f"Unexpected error while opening logfile: {e}")
                return

            self.file_operations.update_xtalinfo_signal.emit('Measuring', 'XDS')
            # self.file_operations.update_xtalinfo_signal.emit('Measuring', 'DIALS')

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
                        if os.access(os.path.dirname(self.log_suffix), os.W_OK):
                            logfile.write(f"{t - t0:10.6f}  {pos[3]:8.3f} deg\n")
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
                if os.access(os.path.dirname(self.log_suffix), os.W_OK):
                    logfile.write(f"# Final Angle (measured):   {phi1:.3f} deg\n")
            except Exception as e:
                logging.error(f"Failed to get final tilt angle: {e}")   

            if os.access(os.path.dirname(self.log_suffix), os.W_OK): logfile.close()
            logging.info(f"Stage rotation end at {phi1:.1f} deg.")
            
            # GUI updates; should be done before Auto-Reset, which modifies the stage status
            try:
                self.control.send_to_tem("#more", asynchronous = False)  # Update tem_status map and GUI
                logging.info('TEM-status received.')
            except Exception as e:
                logging.error("Error updating TEM status: {e}")
            
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
                    time.sleep(0.01)
            except Exception as e:
                logging.error(f'Error during "Auto-Reset" rotation: {e}')

            # Add H5 info and file finalization
            if self.writer is not None:
                time.sleep(0.1)
                logging.info(" ******************** Adding Info to H5 over Server...")
                try:
                    beam_property = {
                        "beamcenter" : self.cfg.beam_center, 
                        "sigma_width" : self.control.beam_sigmaxy,
                        "illumination" : self.control.beam_intensity,
                    }
                    send_with_retries(self.metadata_notifier.notify_metadata_update, 
                                        self.tem_action.visualization_panel.formatted_filename, 
                                        self.control.tem_status, 
                                        beam_property,
                                        self.rotations_angles,
                                        self.cfg.threshold,
                                        retries=3, 
                                        delay=0.1) 
                    
                    self.file_operations.update_xtalinfo_signal.emit('Processing', 'XDS')
                    # self.file_operations.update_xtalinfo_signal.emit('Processing', 'DIALS')
                except Exception as e:
                    logging.error(f"Metadata Update Error: {e}")
                    self.file_operations.update_xtalinfo_signal.emit('Metadata error', 'XDS')

            if self.writer is None:
                self.reset_rotation_signal.emit()
                
            self.tem_action.trigger_additem.emit('green', 'recorded', pos)
            self.tem_action.trigger_processed_receiver.emit()
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
            if logfile is not None:
                logfile.close()  # Ensure the logfile is closed in case of any errors
            self.client.SetBeamBlank(1)
            time.sleep(0.01)
            QMetaObject.invokeMethod(self.tem_action,
                                    "reconnectGaussianFit",
                                    Qt.QueuedConnection
            )
            self.reset_rotation_signal.emit()
        
        # self.make_xds_file(master_filepath,
        #                    os.path.join(sample_filepath, "INPUT.XDS"), # why not XDS.INP?
        #                    self.tem_action.xds_template_filepath)
         
    # def on_tem_receive(self):
    #     self.rotations_angles.append(
    #         (self.control.tem_update_times['stage.GetPos'][0],
    #         self.control.tem_status['stage.GetPos'][3],
    #         self.control.tem_update_times['stage.GetPos'][1])
    #     )

    def make_xds_file(self, master_filepath, xds_filepath, xds_template_filepath):
        master_file = h5py.File(master_filepath, 'r')
        template_filepath = master_filepath[:-9] + "??????.h5" # master_filepath.replace('master', '??????')
        frame_time = master_file['entry/instrument/detector/frame_time'][()]
        oscillation_range = 0.05 # frame_time * self.phi_dot
        logging.info(f" OSCILLATION_RANGE= {oscillation_range} ! frame time {frame_time}")
        logging.info(f" NAME_TEMPLATE_OF_DATA_FRAMES= {template_filepath}")

        for dset in master_file["entry/data"]:
            nimages_dset = master_file["entry/instrument/detector/detectorSpecific/nimages"]
            logging.info(f" DATA_RANGE= 1 {nimages_dset}")
            logging.info(f" BACKGROUND_RANGE= 1 {nimages_dset}")
            logging.info(f" SPOT_RANGE= 1 {nimages_dset}")
            h = master_file['entry/data/data_000001'].shape[2]
            w = master_file['entry/data/data_000001'].shape[1]
            for i in range(1):
                image = master_file['entry/data/data_000001'][i]
                logging.info(f"   !Image dimensions: {image.shape}, 1st value: {image[0]}")
                org_x, org_y = self.cfg.beam_center[0], self.cfg.beam_center[1]
                # org_x, org_y = self.tem_action.beamcenter[0], \
                #                self.tem_action.beamcenter[1]
            break

        # myxds = XDSparams(xdstempl=xds_template_filepath)
        # myxds.update(org_x, org_y, template_filepath, nimages_dset, oscillation_range,
        #              self.control.tem_status['eos.GetMagValue'][0]*10)
        # myxds.xdswrite(filepath=xds_filepath)
        
        # def do_xds(self):
        #     make_xds_file()
        #     subprocess.run(cmd_xds, cwd=self.'workingdirectory')
        #     if os.path.isfile(** + '/IDXREF.LP'):
        #         with open(** + '/IDXREF.LP', 'r') as f:
        #             [extract cell parameters and indexing rate]
        #     [report to the GUI or control_worker]
                    
