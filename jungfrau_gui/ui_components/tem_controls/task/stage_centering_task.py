import time
from datetime import datetime as dt
import logging
import numpy as np
from .task import Task

from simple_tem import TEMClient
from .... import globals
from epoc import ConfigurationClient, auth_token, redis_host
from jungfrau_gui.ui_components.tem_controls.toolbox import config as cfg_jf

'''
click-on-move
    when get dx/dy [px] on clicking, move stage to be centered
'''

class CenteringTask(Task):   
    def __init__(self, control_worker, pixels=[10, 1]):
        super().__init__(control_worker, "Centering")
        self.control = control_worker
        self.pixels = pixels
        logging.info("CenteringTask initialized")
        self.client = TEMClient(globals.tem_host, 3535,  verbose=True)
        self.cfg = ConfigurationClient(redis_host(), token=auth_token())
        for shape in self.cfg.overlays:
            if shape['type'] == 'rectangle':
                self.lowmag_jump = shape['xy'][0]+shape['width']//2, shape['xy'][1]+shape['height']//2
                break
        self.thresholds = [0.3, 100, 1, 10] # xy-min, xy-max, z-min, x-max [um]

    def rot2d(self, vector, theta):# anti-clockwise
        theta_r = np.radians(theta)
        rotmatrix = np.array([[np.cos(theta_r), -np.sin(theta_r)],
                              [np.sin(theta_r),  np.cos(theta_r)]])
        return rotmatrix @ vector
    
    def translationvector(self, pixels, magnification):
        calibrated_mag = cfg_jf.lookup(cfg_jf.lut.magnification, magnification[2], 'displayed', 'calibrated')
        if int(magnification[0]) >= 1500 : # Mag
            logging.debug(f'Estimate with rotation')
            tr_vector = (pixels - [self.cfg.ncols/2, self.cfg.nrows/2]) * cfg_jf.others.pixelsize * 1e3 / calibrated_mag # in um
            tr_vector = self.rot2d(tr_vector, cfg_jf.others.rotation_axis_theta) # deg., angle between detector y and rotation axes.
        else: # Lowmag, targeting to the rectangular overlay
            logging.debug(f'Estimate with rotation at LM')
            tr_vector = (pixels - [self.lowmag_jump[0], self.lowmag_jump[1]]) * cfg_jf.others.pixelsize * 1e3 / calibrated_mag # in um
            tr_vector = self.rot2d(tr_vector, cfg_jf.others.rotation_axis_theta_lm1200x)
        return np.round(tr_vector, 3)

    def run(self):
        px_array = np.array(self.pixels)
        tilt_X_abs = np.abs(self.client.GetTiltXAngle())
        if tilt_X_abs > 1 and tilt_X_abs < 5:
            logging.warning('Stage tilts! Reset tilting or Adjust Z manually. ')
            return
        magnification = self.control.tem_status["eos.GetMagValue"]
        try:
            movexy = self.translationvector(px_array, magnification) # in um
        except ZeroDivisionError:
            logging.warning(f'Value invalid: {magnification[2]}')
            return
        
        # == INSERT A ROUTINE HERE TO AVOID OVER-SHIFTING ==
        
        if np.abs(movexy[0]) > self.thresholds[1] or np.abs(movexy[1]) > self.thresholds[1]:
            logging.info(f'Vector too large: {movexy[0]}, {movexy[1]}')
            return
        
        if tilt_X_abs < 5:
            if np.abs(movexy[0]) < self.thresholds[0] and np.abs(movexy[1]) < self.thresholds[0]:
                logging.info(f'Vector already small enough (< {self.thresholds[0]} um): {movexy[0]}, {movexy[1]}')
                return
            logging.info(f'Move X: {movexy[0]},  Y: {movexy[1]} with MAG: {magnification[2]}')
            self.client.SetXRel(movexy[0]*-1e3)
            time.sleep(0.5)
            self.client.SetYRel(movexy[1]*-1e3)
            time.sleep(0.5)
        else:
            if tilt_X_abs < 11:
                logging.info('Start Z-adjustment from Tx=0.')
                self.control.previous_tx_abs = 0
            else:
                logging.info('Continue Z-adjustment.')
            movez  = np.round(movexy[1] / (np.sin(np.deg2rad(tilt_X_abs)) - np.sin(np.deg2rad(self.control.previous_tx_abs))), 3) # in um
            self.control.previous_tx_abs = tilt_X_abs
            if np.abs(movez) < self.thresholds[2] or np.abs(movez) > self.thresholds[3]:
                logging.info(f'Too small or too large Z-Vector: {movez}')
                return
            logging.info(f'Move Z: {movez} with MAG: {magnification[2]}')
            logging.warning(f'Move Z is not activated yet!!')
            # self.client.SetZRel(movez*-1e3)
        
        # Wait until the stage is done moving 
        # (Is this useful?) -> Fast/Async movement  
        # while self.client.is_moving():
        #     time.sleep(0.1)
        # logging.info('Stage movement ended or was interrupted.')

        logging.info('Stage is now ready.')
        return
