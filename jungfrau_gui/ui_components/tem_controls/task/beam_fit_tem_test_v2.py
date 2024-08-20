import time
import json
import math
import logging
import numpy as np
import pyqtgraph as pg
from datetime import datetime as dt
from ....ui_components.tem_controls.task.task_test import Task

from simple_tem import TEMClient

IL1_0 = 21902 #40345
ILs_0 = [33040, 32688]

class BeamFitTask(Task):
    def __init__(self, control_worker):
        super().__init__(control_worker, "BeamFit")
        self.duration_s = 60 # should be replaced with a practical value
        self.estimateds_duration = self.duration_s + 0.1
        self.control = control_worker        
        self.client = TEMClient("localhost", 3535)

        self.control.fit_complete.connect(self.process_fit_results)
        self.max_amplitude = -float('inf')
        self.amp_il1_map = {}

    def run(self, init_IL1=IL1_0):
        logging.info("Start IL1 rough-sweeping.")
        self.sweep_il1_linear(init_IL1 - 500, init_IL1 + 500, 25)
        self.client.SetILFocus(self.amp_il1_map[self.max_amplitude])
        """ amp_last_fit = self.fit().best_values["amplitude"]  # Need to update the ellipse to fit the optimal the choice"""

        if self.control.fitterWorkerReady == True:
            self.control.tem_action.tem_tasks.beamAutofocus.setText("Remove axis / pop-up")   
        else:
            print("********************* Emitting 'remove_ellipse' signal from -FITTING- Thread *********************")
            self.control.remove_ellipse.emit()  
    

    def sweep_il1_linear(self, lower, upper, step, wait_time_s=0.2):
        for il1_value in range(lower, upper, step):
            print(f"********************* fitterWorkerReady = {self.control.fitterWorkerReady}")
            if self.control.fitterWorkerReady == True:
                self.client.SetILFocus(il1_value)
                logging.debug(f"{dt.now()}, il1_value = {il1_value}")
                time.sleep(wait_time_s) # Wait for the lens to reach position (TO IMPROVE)
                # while not self.client.is_lens_ready():
                #     time.sleep(0.01)  # Check every 10 ms if the lens is ready
                self.control.request_fit.emit(il1_value)
                time.sleep(wait_time_s) # Wait for the fitting?? 
            else:
                print("IL1 LINEAR sweeping INTERRUPTED")
                break

        logging.info("Now reset to the initial value (for safety in testing)")
        self.client.SetILFocus((lower + upper)//2)
        time.sleep(1)

    def process_fit_results(self, fit_result, il_value):
            amplitude = float(fit_result['amplitude'])
            self.amp_il1_map[amplitude] = il_value 
            if amplitude > self.max_amplitude:
                self.max_amplitude = amplitude
            logging.info(f"Processed il_value {il_value} with amplitude {amplitude}")
            logging.info(f"Current best focus at position {self.best_il1value} with amplitude {self.max_amplitude}")
