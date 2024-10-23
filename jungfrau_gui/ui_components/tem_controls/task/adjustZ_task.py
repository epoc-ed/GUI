import time
import numpy as np

from .task import Task

from simple_tem import TEMClient

# data measured by TG, using Au-grating grid, on 26 Oct 2023
mag_on_jf = [[100000,  80000, 60000, 50000, 40000, 30000, 25000, 20000, 15000, 12000, 10000,  8000, 6000, 5000, 4000, 3000, 2500, 2000, 1500], 
             [133920, 106704, 77112, 65016, 52056, 39852, 33120, 26136, 20196, 15898, 13046, 10553, 7830, 5364, 5227, 3888, 3294, 2592, 1890]]

magnification = 1
jf_px = 75 # um
jf_y = 512 # px
dtheta = 68.2 # deg., angle between detector y and rotation axes.

class AdjustZ(Task):
    def __init__(self, control_worker):
        super().__init__(control_worker, "AdjustZ")
        self.control = control_worker
        self.client = TEMClient("temserver", 3535,  verbose=True)
        
    def px2um(self, px):
        magnification = int(self.control.tem_status['eos.GetMagValue'][0])
        try:
            return px * jf_px / mag_on_jf[1][mag_on_jf[0].index(magnification)]
        except ValueError:
            print('Current Mag value is not in Table.')
            return 0

    # def zadjust_sequence(self, max_itr=5, max_tilt=50):
    def run(self, max_itr=5, max_tilt=50):
        itr = 0
        tilt_speed = 1   # 2 deg/s
        dummy_step = 8

        magnification = int(self.control.tem_status['eos.GetMagValue'][0])
        print(f'Current Mag: {magnification}')
        phi0 = float(self.control.tem_status['stage.GetPos'][3])
        ### self.client.Setf1OverRateTxNum(tilt_speed)  # requires ED package
        time.sleep(1)
        while itr <= 5 and phi0 <= max_tilt and dummy_step < 40:
            phi0 = float(self.control.tem_status['stage.GetPos'][3])
            x = input('Tilt stage until a central object goes on detector edge. Is it on top [T] or bottom [B] edge? \nOr type \'E\' for exit. [T]/B/E:')
            # x = 'T'
            self.client.SetTXRel(dummy_step)
            time.sleep(dummy_step/10)
            ### dummy move for test ###
            while True:
                time.sleep(1)
                phi1 = float(self.control.tem_status['stage.GetPos'][3])
                if phi1 >= phi0 + dummy_step*0.9:
                    break
            dummy_step += dummy_step
            ### 
            if x == 'E': break
            z_sign = 1 if x != 'B' else -1
            phi1 = float(self.control.tem_status['stage.GetPos'][3])
            print(f'TiltX updated: {phi0:.3f} -> {phi1:.3f}')
            shift_object = self.px2um(jf_y / 2 / np.sin(np.deg2rad(dtheta)))
            delta_z = shift_object / np.sin(np.deg2rad(phi1 - phi0)) * z_sign
            print(f'Shift Z: {delta_z:.3f} um for calibrate {shift_object:.3f} um shift')
            if delta_z > 10:
                print('Shift value is too large. Please adjust Z manually.')
                return 0
            else:
                self.client.SetZRel(delta_z * 1e3)
                time.sleep(delta_z)
            itr += 1
        print('Stage Z is now eucentric height.')
