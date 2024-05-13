import time
import numpy as np
from datetime import datetime as dt
from task.task import Task
import subprocess

import os

class RecordTask(Task):
    def __init__(self, control_worker, end_angle = 60):
        super().__init__(control_worker, "Record")
        self.phi_dot = 0 # 10 deg/s
        self.conrol = control_worker
        self.end_angle = end_angle
        self.rotations_angles = []

    def run(self, filename='RotEDlog_test'):
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
        print(f'{self.estimated_duration_s:8.3f} sec expected.')

        logfile = open(filename + '.log', 'w')
        print(f'Start logging: {filename}.log')
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
        self.control.send_to_tem("#more")
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
        
        time.sleep(log_duration)
        t0 = time.time()
        self.rotations_angles = []
        # while True:
        stage_move = False
        while self.control.tem_status['stage.GetPos'][3] < phi1:
            if os.name == 'nt':
                self.tem_command("stage", "SetTXRel", [self.phi_dot])
            time.sleep(0.5)
            self.control.send_to_tem("#info")
            print(f"{self.control.tem_update_times['stage.GetPos'][0]:20.6f}  {self.control.tem_status['stage.GetPos'][3]:8.3f} deg")
            logfile.write(f"{self.control.tem_update_times['stage.GetPos'][0]:20.6f}  {self.control.tem_status['stage.GetPos'][3]:8.3f} deg\n")
            if int(self.control.tem_status['stage.GetStatus'][3]) == 1: stage_move=True
            if int(self.control.tem_status['stage.GetStatus'][3]) != 1 and stage_move:
                print('Rotation was end or interrupted.')
                break
        time.sleep(0.5)
        self.tem_command("defl", "SetBeamBlank", [1]) # beam blanking ON
        self.control.send_to_tem("#more")
        time.sleep(0.5)
        print(self.control.tem_status)
        if self.control.send_to_tem("defl.GetBeamBlank()") == 1:
            print('Beam is now blanking.')
        phi1 = float(self.control.tem_status['stage.GetPos'][3])
        logfile.write(f"# Final Angle (measured):   {phi1:.3f} deg\n")
        logfile.close()
        print(f"Stage rotation end at {phi1:.1f} deg. Return to zero-tilt.")
        time.sleep(1)
        if not os.name == 'nt': self.tem_command("stage", "Setf1OverRateTxNum", [return_speed_idx]) # requires ED package
        self.tem_command("stage", "SetTiltXAngle", [0])
        print("Recording task stopped.")
        
        while True:
            time.sleep(0.25)
            self.control.send_to_tem("#info")
            if int(self.control.tem_status['stage.GetStatus'][3]) != 1:
                print('Now stage is ready.')
                break

    def on_tem_receive(self):
        self.rotations_angles.append(
            (self.control.tem_update_times['stage.GetPos'][0],
            self.control.tem_status['stage.GetPos'][3],
            self.control.tem_update_times['stage.GetPos'][1])
        )
