import time
import json
import math
import logging
import threading
import numpy as np
import pyqtgraph as pg
from datetime import datetime
from PySide6.QtCore import Slot
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

        # self.control.fit_complete.connect(self.process_fit_results)
        self.max_amplitude = -float('inf')
        self.amp_il1_map = {}

    def run(self, init_IL1=IL1_0):
        logging.info("Start IL1 rough-sweeping.")
        self.sweep_il1_linear(init_IL1 - 500, init_IL1 + 500, 25)

        if not self.max_amplitude == -float('inf'):
            self.client.SetILFocus(self.amp_il1_map[self.max_amplitude]) # If task finished, move lens to optimal position 
        else:
            self.client.SetILFocus(init_IL1) # If task interrupted, back to initial position of lens 
        """ amp_last_fit = self.fit().best_values["amplitude"]  # Need to update the ellipse to fit the optimal the choice"""

        if self.control.fitterWorkerReady == True:
            self.control.tem_action.tem_tasks.beamAutofocus.setText("Remove axis / pop-up")   
        else:
            print("********************* Emitting 'remove_ellipse' signal from -FITTING- Thread *********************")
            self.control.remove_ellipse.emit()  
    

    def sweep_il1_linear(self, lower, upper, step, wait_time_s=0.01): 
        # typically it takes a few milliseconds for the lens to reach its position between 1 and 5 ms
        # this has been determined through some profiling (ref. timing of REQ and REP status of TEM commands in terminal)
        # wait_time_s is defined here as 10 ms, unless a dynamic wait is implemeted (commented area below)
        for il1_value in range(lower, upper, step):
            print(f"********************* fitterWorkerReady = {self.control.fitterWorkerReady}")
            if self.control.fitterWorkerReady == True:
                self.client.SetILFocus(il1_value)
                logging.debug(f"{datetime.now()}, il1_value = {il1_value}")
                
                time.sleep(wait_time_s) # NOT THE BEST WAY..
                # Dynamically wait until the lens is reported as ready
                # while not self.client.is_lens_ready():
                #     time.sleep(0.01)  # Check every 10 ms if the lens is ready

                logging.info(datetime.now().strftime(" EMISSION @ %H:%M:%S.%f")[:-3])
                self.control.request_fit.emit(il1_value)
                time.sleep(10*wait_time_s)
            else:
                print("IL1 LINEAR sweeping INTERRUPTED")
                break

        logging.info("Now reset to the initial value (for safety in testing)")
        self.client.SetILFocus((lower + upper)//2)
        time.sleep(wait_time_s)
