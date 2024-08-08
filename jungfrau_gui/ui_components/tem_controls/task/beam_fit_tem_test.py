import time
import json
import math
import logging
from datetime import datetime as dt
from ....ui_components.tem_controls.task.task import Task
import numpy as np
from PySide6.QtGui import QTransform
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsRectItem
from PySide6.QtCore import Signal, QRectF, Qt, QMetaObject, Q_ARG

import pyqtgraph as pg

from ..fit_beam_intensity import fit_2d_gaussian_roi, fit_2d_gaussian_roi_test

from simple_tem import TEMClient

IL1_0 = 21902 #40345
ILs_0 = [33040, 32688]

class BeamFitTask(Task):
    """ fit_updated = Signal(dict)"""

    def __init__(self, control_worker):
        super().__init__(control_worker, "BeamFit")
        self.duration_s = 60 # should be replaced with a practical value
        self.estimateds_duration = self.duration_s + 0.1
        self.control = control_worker 

        """ self.fit_updated.connect(self.updateFitParams_json) """
        
        self.client = TEMClient("temserver", 3535)
    

    def run(self, init_IL1=IL1_0):

        logging.info("Start ILs rough-sweeping.")
        _, _, ils_guess1 = self.sweep_stig_linear(1000, 50)
        # self.tem_command("defl", "SetILs", ils_guess1)
        self.client.SetILs(ils_guess1[0], ils_guess1[1])
        time.sleep(1)
               
        logging.info("Start IL1 rough-sweeping.")
        _, il1_guess1 = self.sweep_il1_linear(init_IL1 - 500, init_IL1 + 500, 50)
        # self.tem_command("lens", "SetILFocus", [il1_guess1])
        self.client.SetILFocus(il1_guess1)
        time.sleep(1)
        
        logging.info("Start IL1 fine-sweeping.")
        _, il1_guess2 = self.sweep_il1_linear(il1_guess1 - 50, il1_guess1 + 50, 5)
        # self.tem_command("lens", "SetILFocus", [il1_guess2])
        self.client.SetILFocus(il1_guess2)
        time.sleep(1)

        logging.info("Start ILs fine-sweeping.")
        _, _, ils_guess2 = self.sweep_stig_linear(50, 5)
        # self.tem_command("defl", "SetILs", ils_guess2)
        self.client.SetILs(ils_guess2[0], ils_guess2[1])
        time.sleep(1)
    
    def sweep_il1_linear(self, lower, upper, step, wait_time_s=0.2):
        max_amplitude = 0
        max_il1value = None

        logging.info("before loop")

        for il1_value in range(lower, upper, step):
            # self.tem_command("lens", "SetILFocus", [il1_value])
            self.client.SetILFocus(il1_value)
            logging.debug(f"{dt.now()}, il1_value = {il1_value}")
            time.sleep(wait_time_s)

            """ *** Fitting *** """
            # amplitude = self.control.stream_receiver.fit[0] # amplitude
            im = self.control.tem_action.parent.imageItem.image
            roi = self.control.tem_action.parent.roi
            fit_result = fit_2d_gaussian_roi_test(im, roi)
            # Update pop-up plot and drawn ellipse 
            self.control.fit_updated.emit(fit_result.best_values)  # Emit the signal
            # Determine peak value (amplitude)
            amplitude = float(fit_result.best_values['amplitude'])
            """ *************** """
            
            if max_amplitude < amplitude:
                max_amplitude = amplitude
                max_il1value = il1_value

            logging.debug(f"{dt.now()}, amplitude = {amplitude}")

        logging.info("end loop")

        logging.info("Now reset to the initial value (for safety in testing)")
        time.sleep(1)
        # self.tem_command("lens", "SetILFocus", [(lower + upper)//2])
        self.client.SetILFocus((lower + upper)//2)

        return max_amplitude, max_il1value
        
    def move_to_stigm(self, stigm_x, stigm_y):
        # self.tem_command("defl", "SetILs", [stigm_x, stigm_y])
        self.client.SetILs(stigm_x, stigm_y)
        
    def sweep_stig_linear(self, deviation, step, wait_time_s=0.2, init_stigm=ILs_0):
        min_sigma1 = 1000
        min_stigmvalue = init_stigm
        best_ratio = 2

        for stigmx_value in range(init_stigm[0]-deviation, init_stigm[0]+deviation, step):
            # self.tem_command("defl", "SetILs", [stigmx_value, init_stigm[1]])
            self.client.SetILs(stigmx_value, init_stigm[1])

            time.sleep(wait_time_s)
            logging.debug(f"{dt.now()}, stigmx_value = {stigmx_value}")
            
            """ *** Fitting *** """
            # sigma1 = self.control.stream_receiver.fit[0] # smaller sigma value (shorter axis)
            im = self.control.tem_action.parent.imageItem.image
            roi = self.control.tem_action.parent.roi
            fit_result = fit_2d_gaussian_roi_test(im, roi)
            # Update pop-up plot and drawn ellipse 
            self.control.fit_updated.emit(fit_result.best_values)  # Emit the signal
            # Determine smaller sigma (sigma1)
            sigma_x = float(fit_result.best_values['sigma_x'])
            sigma_y = float(fit_result.best_values['sigma_y'])
            sigma1 = min(sigma_x, sigma_y)
            """ *************** """
            
            if min_sigma1 > sigma1:
                min_sigma1 = sigma1
                min_stigmvalue = [stigmx_value, init_stigm[1]]

        # self.tem_command("defl", "SetILs", min_stigmvalue)
        self.client.SetILs(min_stigmvalue[0], min_stigmvalue[1])        
        time.sleep(1)
        
        for stigmy_value in range(init_stigm[1]-deviation, init_stigm[1]+deviation, step):
            # self.tem_command("defl", "SetILs", [min_stigmvalue[0], stigmy_value])
            self.client.SetILs(min_stigmvalue[0], stigmy_value)        

            time.sleep(wait_time_s)
            logging.debug(f"{dt.now()}, stigmy_value = {stigmy_value}")
            
            """ *** Fitting *** """
            # ratio = self.control.stream_receiver.fit[0] # sigma ratio
            im = self.control.tem_action.parent.imageItem.image
            roi = self.control.tem_action.parent.roi
            fit_result = fit_2d_gaussian_roi_test(im, roi)
            # Update pop-up plot and drawn ellipse 
            self.control.fit_updated.emit(fit_result.best_values)  # Emit the signal
            # Determine sigmas ratio
            sigma_x = float(fit_result.best_values['sigma_x'])
            sigma_y = float(fit_result.best_values['sigma_y'])
            ratio = max(sigma_x, sigma_y)/min(sigma_x, sigma_y)
            """ *************** """
            
            if abs(best_ratio - 1) > abs(ratio - 1):
                best_ratio = ratio
                min_stigmvalue = [min_stigmvalue[0], stigmy_value]
        
        logging.debug("Now reset to the initial value (for safety in testing)")
        time.sleep(1)
        # self.tem_command("defl", "SetILs", init_stigm)
        self.client.SetILs(init_stigm[0], init_stigm[1])        

        return min_sigma1, best_ratio, min_stigmvalue