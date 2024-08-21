import time
import h5py
import numpy as np
from datetime import datetime as dt
from ....ui_components.tem_controls.task.task_test import Task
import subprocess
import logging
# from PySide6.QtWidgets import QRadioButton
import os
# import ui_components.tem_controls.task.dectris2xds import XDSparams

from simple_tem import TEMClient
from epoc import ConfigurationClient, auth_token, redis_host

class RecordTask(Task):
    def __init__(self, control_worker, end_angle = 60, log_suffix = 'RotEDlog_test', writer_event=None):
        super().__init__(control_worker, "Record")
        self.phi_dot = 0 # 10 deg/s
        self.control = control_worker
        self.tem_action = self.control.tem_action
        self.writer = writer_event
        self.end_angle = end_angle
        self.rotations_angles = []
        self.log_suffix = log_suffix
        print("RecordTask initialized")
        self.client = TEMClient("localhost", 3535)
        self.cfg = ConfigurationClient(redis_host(), token=auth_token())

    def run(self):
        print("RecordTask::run()")
        phi0 = self.client.GetTiltXAngle()
        phi1 = self.end_angle


        stage_rates = [10.0, 2.0, 1.0, 0.5]
        phi_dot_idx = self.client.Getf1OverRateTxNum()


        self.phi_dot = stage_rates[phi_dot_idx]
        self.cfg.data_dir.mkdir(parents=True, exist_ok=True) #TODO! when do we create the data_dir?

        # if os.access(os.path.dirname(self.log_suffix), os.W_OK):
        print("\n\n\n---------OPEN LOG-----------------\n\n\n")
        # self.control.send_to_tem("#more")
        logfile = open(self.log_suffix + '.log', 'w')
        logfile.write("# TEM Record\n")
        logfile.write("# TIMESTAMP: " + time.strftime("%Y/%m/%d %H:%M:%S", time.localtime()) + "\n")
        logfile.write(f"# Initial Angle:           {phi0:6.3f} deg\n")
        logfile.write(f"# Final Angle (scheduled): {phi1:6.3f} deg\n")
        logfile.write(f"# angular Speed:           {self.phi_dot:6.2f} deg/s\n")
        logfile.write(f"# magnification:           {self.control.tem_status['eos.GetMagValue_MAG'][0]:<6d} x\n")
        logfile.write(f"# detector distance:       {self.control.tem_status['eos.GetMagValue_DIFF'][0]:<6d} mm\n")
        # BEAM
        logfile.write(f"# spot_size:               {self.client.GetSpotSize()}\n")
        logfile.write(f"# alpha_angle:             {self.client.GetAlpha()}\n")
    #     # APERTURE
        logfile.write(f"# CL#:                     {self.client.GetAperatureSize(1)}\n") # should refer look-up table
        logfile.write(f"# SA#:                     {self.client.GetAperatureSize(4)}\n") # should refer look-up table
    #     # LENS
        logfile.write(f"# brightness:              {self.client.GetCL3()}\n")
        logfile.write(f"# diff_focus:              {self.client.GetIL1()}\n")
        logfile.write(f"# IL_focus:                {self.client.GetILs()}\n")
        logfile.write(f"# PL_align:                {self.client.GetPLA()}\n")
    #     # STAGE
        logfile.write(f"# stage_position:          {self.client.GetStagePosition()}\n")
        

        self.client.Setf1OverRateTxNum(phi_dot_idx)
        time.sleep(1) 
        self.client.SetBeamBlank(0)
        time.sleep(0.5)

        self.client.SetTiltXAngle(phi1, True, False)

        #Wait enough to make the rotation start (can also use other logic)
        time.sleep(0.5) 

        #If enabled we start writing files 
        if self.writer: 
            """ self.writer() """
            self.tem_action.file_operations.start_H5_recording.emit() 
        
        t0 = time.time()
        while self.client.stage_is_rotating:
            pos = self.client.GetStagePosition()
            t = time.time()
            logfile.write(f"{t - t0:20.6f}  {pos[3]:8.3f} deg\n")
            time.sleep(0.1) #TODO! Find a better value

        
        # Stop the file writing
        if self.writer and self.tem_action.file_operations.streamWriterButton.started:
            print(" *********************** Stopping the Writer **********************")
            """ self.writer() """
            self.tem_action.file_operations.stop_H5_recording.emit()
        
        self.client.SetBeamBlank(1)
        phi1 = self.client.GetTiltXAngle()
        if os.access(os.path.dirname(self.log_suffix), os.W_OK):            
            logfile.write(f"# Final Angle (measured):   {phi1:.3f} deg\n")
            logfile.close()
        logging.info(f"Stage rotation end at {phi1:.1f} deg.")

        #TODO! Enable auto reset of tilt
        if self.tem_action.tem_tasks.autoreset_checkbox.isChecked(): 
            logging.info("Return the stage tilt to zero.")
            self.client.SetTiltXAngle(0, True, True)
            time.sleep(1)
            
        # Waiting for the rotation to end
        while self.client.stage_is_rotating:
            time.sleep(0.1)

        # logging.info("Recording task stopped.")
        
        if self.writer:
            self.control.send_to_tem("#more")
            self.tem_action.temtools.trigger_addinfo_to_hdf5.emit()
            os.rename(self.log_suffix + '.log', (self.cfg.data_dir/self.cfg.fname).with_suffix('.log'))
            self.cfg.after_write()


        self.tem_action.tem_tasks.rotation_button.setText("Rotation")
        self.tem_action.tem_tasks.rotation_button.started = False
        self.tem_action.file_operations.streamWriterButton.setEnabled(True)

        print("------REACHED END OF TASK----------")

        # self.make_xds_file(master_filepath,
        #                    os.path.join(sample_filepath, "INPUT.XDS"), # why not XDS.INP?
        #                    self.tem_action.xds_template_filepath)
                
    def on_tem_receive(self):
        self.rotations_angles.append(
            (self.control.tem_update_times['stage.GetPos'][0],
            self.control.tem_status['stage.GetPos'][3],
            self.control.tem_update_times['stage.GetPos'][1])
        )

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
                org_x, org_y = self.tem_action.beamcenter[0], \
                               self.tem_action.beamcenter[1]
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
                    
