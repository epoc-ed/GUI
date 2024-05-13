import time
from datetime import datetime as dt
from task.task import Task
import numpy as np
import logging

IL1_0 = 21867 # 21902 #40345
ILs_0 = [32896, 33344] #[33040, 32688]

class BeamFitTask(Task):
    def __init__(self, control_worker):
        super().__init__(control_worker, "BeamFit")
        self.duration_s = 60 # should be replaced with a practical value
        self.estimateds_duration = self.duration_s + 0.1
    
    def run(self, init_IL1=IL1_0):
        logging.info("Start IL1 rough-sweeping.")
        _, il1_guess1 = self.sweep_il1_linear(init_IL1 - 250, init_IL1 + 250, 50)
        self.tem_command("lens", "SetILFocus", [il1_guess1])
        time.sleep(1)

        logging.info("Start ILs rough-sweeping.")
        _, _, ils_guess1 = self.sweep_stig_linear(500, 50)
        self.tem_command("defl", "SetILs", ils_guess1)
        time.sleep(1)
               
        logging.info("Start IL1 fine-sweeping.")
        _, il1_guess2 = self.sweep_il1_linear(il1_guess1 - 50, il1_guess1 + 50, 5)
        self.tem_command("lens", "SetILFocus", [il1_guess2])
        time.sleep(1)

        logging.info("Start ILs fine-sweeping.")
        _, _, ils_guess2 = self.sweep_stig_linear(50, 5)
        self.tem_command("defl", "SetILs", ils_guess2)
        time.sleep(1)
    
    def sweep_il1_linear(self, lower, upper, step, wait_time_s=0.2):
#        max_amplitude = 0
#        max_il1value = None
        for il1_value in range(lower, upper, step):
            self.tem_command("lens", "SetILFocus", [il1_value])
            time.sleep(wait_time_s)
            logging.info(f"{dt.now()}  {il1_value}")
#            amplitude = self.control.stream_receiver.fit[0]
#            if max_amplitude < amplitude:
#                max_amplitude = amplitud
#                max_il1value = il1_value
        logging.warning("Now reset to the initial value (for safety in testing)")
        time.sleep(1)
        self.tem_command("lens", "SetILFocus", [(lower + upper)//2])
        max_amplitude = 1 # dummy
        max_il1value = (lower + upper)//2 # dummy
        return max_amplitude, max_il1value
        
    def move_to_stigm(self, stigm_x, stigm_y):
        self.tem_command("defl", "SetILs", [stigm_x, stigm_y])
        
    def sweep_stig_linear(self, deviation, step, wait_time_s=0.2, init_stigm=ILs_0):
        min_sigma1 = 1000
        min_stigmvalue = init_stigm
        best_ratio = 2

        for stigmx_value in range(init_stigm[0]-deviation, init_stigm[0]+deviation, step):
            self.tem_command("defl", "SetILs", [stigmx_value, init_stigm[1]])
            time.sleep(wait_time_s)
            logging.info(f"{dt.now()}  {stigmx_value}")
            # simga1 = self.control.stream_receiver.fit[0] # smaller sigma value (shorter axis)
            # if min_sigma1 > sigma1:
            #     min_sigma1 = sigma1
            #     min_stigmvalue = [stigmx_value, init_stigm[1]]

        self.tem_command("defl", "SetILs", min_stigmvalue)
        time.sleep(1)
        
        for stigmy_value in range(init_stigm[1]-deviation, init_stigm[1]+deviation, step):
            self.tem_command("defl", "SetILs", [min_stigmvalue[0], stigmy_value])
            time.sleep(wait_time_s)
            logging.info(f"{dt.now()}  {stigmy_value}")
            # ratio = self.control.stream_receiver.fit[0] # sigma ratio
            # if np.abs(best_ratio - 1) > np.abs(ratio - 1):
            #     best_ratio = ratio
            #     min_stigmvalue = [min_stigmvalue[0], stigmy_value]
        
        logging.warning("Now reset to the initial value (for safety in testing)")
        time.sleep(1)
        self.tem_command("defl", "SetILs", init_stigm)
        min_stigmvalue = init_stigm # dummy
        return min_sigma1, best_ratio, min_stigmvalue

