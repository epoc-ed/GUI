import time
import numpy as np

from .task import Task
from .... import globals
from ..toolbox import config as cfg_jf

from simple_tem import TEMClient

# data measured by TG, using Au-grating grid, on 26 Oct 2023
mag_on_jf = [[100000,  80000, 60000, 50000, 40000, 30000, 25000, 20000, 15000, 12000, 10000,  8000, 6000, 5000, 4000, 3000, 2500, 2000, 1500], 
             [133920, 106704, 77112, 65016, 52056, 39852, 33120, 26136, 20196, 15898, 13046, 10553, 7830, 5364, 5227, 3888, 3294, 2592, 1890]]

jf_px = 75 # um
jf_x, jf_y = 1024, 512 # px
dtheta = 68.2 # deg., angle between detector y and rotation axes.

class CenteringTask(Task):
    def __init__(self, control_worker, pixels=[10, 1]):
        super().__init__(control_worker, "Centering")
        self.conrol = control_worker
        self.pixels = pixels
        # self.duration_s = 60 # should be replaced with a practical value
        # self.estimateds_duration = self.duration_s + 0.1

        self.client = TEMClient(globals.tem_host, 3535,  verbose=True)

    def rot2d(self, vector, theta):# anti-clockwise
        theta_r = np.radians(theta)
        rotmatrix = np.array([[np.cos(theta_r), -np.sin(theta_r)],
                              [np.sin(theta_r),  np.cos(theta_r)]])
        return rotmatrix @ vector
    
    def translationvector(self, pixels, magnification):
        tr_vector = (pixels - [jf_x/2, jf_y/2]) * jf_px / mag_on_jf[1][mag_on_jf[0].index(magnification)] # in um
        if magnification >= 10000 : # Mag
            print(f'Estimate with rotation')
            tr_vector = self.rot2d(tr_vector, dtheta)
        return np.round(tr_vector, 3)

    def run(self):
        px_array = np.array(self.pixels)
        while True:
            if self.control.tem_status['eos.GetMagValue'][0] != 0:
                prev_timestamp = self.control.tem_update_times['stage.GetPos'][0]
                break
            self.control.send_to_tem("#more")
            time.sleep(0.5)
        while True:
            self.control.send_to_tem("#more")
            if prev_timestamp != self.control.tem_update_times['stage.GetPos'][0]: break
            time.sleep(0.5)

        magnification = int(self.control.tem_status['eos.GetMagValue'][0])
        movexy = self.translationvector(px_array, magnification) # in um
        if np.abs(movexy[0]) > 100 or np.abs(movexy[1]) > 100:
            print(f'Vector too large: {movexy[0]}, {movexy[1]}')
            return
        elif np.abs(movexy[0]) < 1 and np.abs(movexy[1]) < 1:
            print(f'Vector already small enough: {movexy[0]}, {movexy[1]}')
            return
        # == INSERT A ROUTINE HERE TO AVOID OVER-SHIFTING ==
        print(f'Move X: {movexy[0]},  Y: {movexy[1]} with MAG: {magnification}')
        if np.abs(self.control.tem_status['stage.GetPos'][3]) > 1: 
            print('Stage tilts! Reset tilting and measure again.')
            return
        # self.tem_command("stage", "SetXRel", [movexy[0]*-1e3]) # nm for SetXRel
        self.client.SetXRel(movexy[0]*-1e3)
        time.sleep(0.5)
        # self.tem_command("stage", "SetYRel", [movexy[1]*-1e3]) # nm for SetYRel
        self.client.SetYRel(movexy[1]*-1e3)
        time.sleep(0.5)

        while True:
            self.control.send_to_tem("#info")
            time.sleep(0.5)        
            if int(self.control.tem_status['stage.GetStatus'][3]) != 1:
                print('Rotation was end or interrupted.')
                break
        print('Stage is now ready.')

'''
click-on-move
    when get dx/dy [px] on clicking, move stage to be centered
'''
'''
click-on-centering at low-mag, then higher mag
re-centering, then away and Z-adjust
return, re-centering, and autofocus
start rotED
take real image
'''
