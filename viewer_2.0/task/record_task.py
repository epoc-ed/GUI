import time
import numpy as np
from datetime import datetime as dt
from task.task import Task
import subprocess
import logging

import os

class RecordTask(Task):
    def __init__(self, control_worker, end_angle = 60, log_suffix = 'RotEDlog_test', writer_event=None):
        super().__init__(control_worker, "Record")
        self.phi_dot = 0 # 10 deg/s
        self.conrol = control_worker
        self.writer = writer_event
        self.end_angle = end_angle
        self.rotations_angles = []
        self.log_suffix = log_suffix

    def run(self):
        # ft = self.control.detector.get_config("frame_time", "detector")
        phi0 = float(self.control.tem_status['stage.GetPos'][3])
        phi1 = self.end_angle
        stage_rates = [10.0, 2.0, 1.0, 0.5]
        if not os.name == 'nt': phi_dot_idx = self.control.tem_status['stage.Getf1OverRateTxNum'] # requires ED package
        phi_dot_idx = 2 # 1 deg/s
        return_speed_idx = 0 # 10 deg/s
        log_duration = 1.5 # 0.5

        self.phi_dot = stage_rates[phi_dot_idx] * np.sign(phi1 - phi0)
        # # calculate number of images, take delay into account
        # n_imgs = (abs(phi1 - phi0) / abs(self.phi_dot) - self.control.triggerdelay_ms * 0.001) / ft
        # n_imgs = round(n_imgs)
        # logging.info(f"phidot: {self.phi_dot} deg/s, Delta Phi:{abs(phi1 - phi0)} deg, {n_imgs} images")
        self.estimated_duration_s = abs(phi1 - phi0) / abs(self.phi_dot)
        if self.estimated_duration_s < 5:
            logging.info(f"Estimated duration time is too short (<5 s)!!: {self.estimated_duration_s}")
            self.control.window.rotation_button.setText("Rotation")
            self.control.window.rotation_button.started = False
            return
        logging.info(f'{self.estimated_duration_s:8.3f} sec expected.')

        if os.access(os.getcwd(), os.W_OK):
            logfile = open(self.log_suffix + '.log', 'w')
            logging.info(f'Start logging: {self.log_suffix}.log')
            # log file description #
            logfile.write("# TEM Record\n")
            logfile.write("# TIMESTAMP: " + time.strftime("%Y/%m/%d %H:%M:%S", time.gmtime()) + "\n")
            logfile.write(f"# Initial Angle:           {phi0:6.3f} deg\n")
            logfile.write(f"# Final Angle (scheduled): {phi1:6.3f} deg\n")
            logfile.write(f"# angular Speed:           {self.phi_dot:6.2f} deg/s\n")
            if self.control.tem_status['eos.GetFunctionMode'][0] == 0:
                logfile.write(f"# magnification:           {self.control.tem_status['eos.GetMagValue'][0]:6d} x\n")
            elif self.control.tem_status['eos.GetFunctionMode'][0] == 4:
                logfile.write(f"#d etector distance:       {self.control.tem_status['eos.GetMagValue'][0]*10} mm\n")
            self.tem_moreinfo() #self.control.send_to_tem("#more")
            # BEAM
            logfile.write(f"# spot_size:               {self.control.tem_status['eos.GetSpotSize']}\n")
            logfile.write(f"# alpha_angle:             {self.control.tem_status['eos.GetAlpha']}\n")
            # APERTURE
            logfile.write(f"# CL#:                     {self.control.tem_status['apt.GetSize(1)']}\n") # should refer look-up table
            logfile.write(f"# SA#:                     {self.control.tem_status['apt.GetSize(4)']}\n") # should refer look-up table
            # LENS
            logfile.write(f"# brightness:              {self.control.tem_status['lens.GetCL3']}\n")
            logfile.write(f"# diff_focus:              {self.control.tem_status['lens.GetIL1']}\n")
            logfile.write(f"# IL_focus:                {self.control.tem_status['defl.GetILs']}\n")
            logfile.write(f"# PL_align:                {self.control.tem_status['defl.GetPLA']}\n")
            # STAGE
            logfile.write(f"# stage_position:          {self.control.tem_status['stage.GetPos']}\n")
        # logfile.write(f"#Images: {n_imgs}\n")
        
        # if not os.name == 'nt': subprocess.run(['writer']) <---- this will not work. should use threading or something.
            
        if not os.name == 'nt':
            self.tem_command("stage", "Setf1OverRateTxNum", [phi_dot_idx])
            time.sleep(1)
        self.tem_command("defl", "SetBeamBlank", [0]) # beam blanking OFF
        
        if not os.name == 'nt':
            time.sleep(0.5)
            self.tem_command("stage", "SetTiltXAngle", [phi1])
            
        if self.writer: self.writer() #logging.info('Writer Pushed')
        
        time.sleep(log_duration)
        t0 = time.time()
        self.rotations_angles = []
        # while True:
        stage_moving = False
        while self.control.tem_status['stage.GetPos'][3] < phi1:
            if os.name == 'nt':
                self.tem_command("stage", "SetTXRel", [self.phi_dot])
            time.sleep(0.5)
            self.estimated_duration_s -= 0.5
            self.tem_info() #self.control.send_to_tem("#info")
            logging.info(f"{self.control.tem_update_times['stage.GetPos'][0] - t0:20.6f}  {self.control.tem_status['stage.GetPos'][3]:8.3f} deg")
            if os.access(os.getcwd(), os.W_OK):
                logfile.write(f"{self.control.tem_update_times['stage.GetPos'][0] - t0:20.6f}  {self.control.tem_status['stage.GetPos'][3]:8.3f} deg\n")
            # if self.writer and not self.streamWriterButton.started:
            #     logging.info('Writer was stopped.')
            #     break
            if int(self.control.tem_status['stage.GetStatus'][3]) == 1: stage_moving=True
            if int(self.control.tem_status['stage.GetStatus'][3]) != 1 and stage_moving:
                logging.info('Rotation was end or interrupted.')
                if self.writer and self.control.window.streamWriterButton.started:
                    self.writer()
                break
            if self.estimated_duration_s < 0:
                logging.info('Duration timeout')
                if self.writer and self.control.window.streamWriterButton.started:
                    self.writer()
                break
                
        time.sleep(0.5)
        self.tem_command("defl", "SetBeamBlank", [1]) # beam blanking ON
        self.tem_moreinfo() #self.control.send_to_tem("#more")
        time.sleep(0.5)
        logging.info(self.control.tem_status)
        if int(self.control.tem_status['defl.GetBeamBlank']) == 1:
            logging.info('Beam is now blanking.')
        phi1 = float(self.control.tem_status['stage.GetPos'][3])
        if os.access(os.getcwd(), os.W_OK):
            logfile.write(f"# Final Angle (measured):   {phi1:.3f} deg\n")
            logfile.close()
        logging.info(f"Stage rotation end at {phi1:.1f} deg. Return to zero-tilt.")
        time.sleep(1)
        if not os.name == 'nt': self.tem_command("stage", "Setf1OverRateTxNum", [return_speed_idx]) # requires ED package
        self.tem_command("stage", "SetTiltXAngle", [0])
        logging.info("Recording task stopped.")
        
        if self.writer and os.path.isfile(self.control.window.formatted_filename):
            self.control.window.temtools.addinfo_to_hdf()
        
        while True:
            time.sleep(0.25)
            # self.control.send_to_tem("#info")
            if int(self.control.tem_status['stage.GetStatus'][3]) != 1:
                logging.info('Now stage is ready.')
                break
                
        self.control.window.rotation_button.setText("Rotation")
        self.control.window.rotation_button.started = False

                
    def on_tem_receive(self):
        self.rotations_angles.append(
            (self.control.tem_update_times['stage.GetPos'][0],
            self.control.tem_status['stage.GetPos'][3],
            self.control.tem_update_times['stage.GetPos'][1])
        )

#     def make_xds_file(self, master_filepath, xds_filepath, xds_template_filepath):
#         master_file = h5py.File(master_filepath, 'r')
#         template_filepath = master_filepath.replace('master', '??????')
#         frame_time = master_file['entry/instrument/detector/frame_time'][()]
#         oscillation_range = frame_time * self.phi_dot
#         logging.info(f" OSCILLATION_RANGE= {oscillation_range} ! frame time {frame_time}")
#         logging.info(f" NAME_TEMPLATE_OF_DATA_FRAMES= {template_filepath}")

#         for dset in master_file["entry/data"]:
#             nimages_dset = master_file["entry/instrument/detector/detectorSpecific/nimages"]
#             logging.info(f" DATA_RANGE= 1 {nimages_dset}")
#             logging.info(f" BACKGROUND_RANGE= 1 {nimages_dset}")
#             logging.info(f" SPOT_RANGE= 1 {nimages_dset}")
#             h = master_file['entry/data/data_000001'].shape[2]
#             w = master_file['entry/data/data_000001'].shape[1]
#             for i in range(1):
#                 image = master_file['entry/data/data_000001'][i]
#                 logging.info(f"   !Image dimensions: {image.shape}, 1st value: {image[0]}")
#                 org_x, org_y = 0, 0
#             break

#         myxds = XDSparams(xdstempl=xds_template_filepath)
#         myxds.update(org_x, org_y, template_filepath, nimages_dset, oscillation_range,
#                      self.control.tem_status['eos.GetMagValue'][0]*10)
#         myxds.xdswrite(filepath=xds_filepath)
        