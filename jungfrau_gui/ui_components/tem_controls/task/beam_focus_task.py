import time
import logging
from datetime import datetime

from .task import Task

from simple_tem import TEMClient

IL1_0 = 21902 #40345 40736
ILs_0 = [33040, 32688] #[32856, 32856]
wait_time_s = 0.2 # 70ms
class BeamFitTask(Task):
    def __init__(self, control_worker):
        super().__init__(control_worker, "BeamFit")
        self.duration_s = 60 # should be replaced with a practical value
        self.estimateds_duration = self.duration_s + 0.1
        self.control = control_worker
        self.is_first_beamfit = True        
        self.client = TEMClient("temserver", 3535)
        # self.control.fit_complete.connect(self.process_fit_results)
        self.max_amplitude = -float('inf')
        self.amp_il1_map = {}

    def run(self, init_IL1=IL1_0):
        logging.info("################ Start IL1 rough-sweeping ################")
        self.sweep_il1_linear(init_IL1 - 500, init_IL1 + 550, 50)
        il1_guess1 = self.amp_il1_map[self.max_amplitude]
        logging.info(f"{datetime.now()}, ROUGH OPTIMAL VALUE IS {il1_guess1}")
        print("------------------------------ BIG SLEEP ------------------------------")
        time.sleep(1)
        # Once task finished, move lens to optimal position 
        for il1_value in range(init_IL1 - 500, il1_guess1+150, 50): 
            self.client.SetILFocus(il1_value)
            time.sleep(wait_time_s)
        self.client.SetILFocus(il1_guess1)
        time.sleep(1)
        # Need to update the drawn ellipse to fit the optimal the choice

        logging.info("################ Start IL1 fine-sweeping ################")
        self.sweep_il1_linear(il1_guess1 - 45, il1_guess1 + 50, 5)
        il1_guess2 = self.amp_il1_map[self.max_amplitude]
        logging.info(f"{datetime.now()}, FINE OPTIMAL VALUE IS {il1_guess2}")
        # Once task finished, move lens to optimal position 
        print("------------------------------ BIG SLEEP ------------------------------")
        time.sleep(1)
        for il1_value in range(il1_guess1 - 45, il1_guess2+15, 5): # upper = {il1_guess2 + 5} ???
            self.client.SetILFocus(il1_value)
            time.sleep(wait_time_s)
        self.client.SetILFocus(il1_guess2)
        time.sleep(1)
    
        # Write the computed map of Gaussian peaks to lens positions to a file
        with open('amplitude_to_il1_map.txt', 'w') as file:
            file.write("Amplitude to IL1 Map:\n")
            for amplitude, il1 in self.amp_il1_map.items():
                file.write(f"Amplitude: {amplitude}, IL1: {il1}\n")
        logging.info("Amplitude to IL1 map written to file.")

        if self.control.sweepingWorkerReady == True:
            self.control.tem_action.tem_tasks.beamAutofocus.setText("Remove axis / pop-up")   
        else:
            print("********************* Emitting 'remove_ellipse' signal from -SWEEPING- Thread *********************")
            self.control.remove_ellipse.emit()  
        
        # self.control.cleanup_fitter.emit()
    

    def sweep_il1_linear(self, lower, upper, step, wait_time_s=wait_time_s): 
        for il1_value in range(lower, upper, step):
            logging.debug(f"********************* sweepingWorkerReady = {self.control.sweepingWorkerReady}")
            if self.control.sweepingWorkerReady == True:
                self.client.SetILFocus(il1_value)
                logging.debug(f"{datetime.now()}, il1_value = {il1_value}")
                
                time.sleep(wait_time_s)

                logging.info(datetime.now().strftime(" REQUESTED_FIT @ %H:%M:%S.%f")[:-3])
                self.control.request_fit.emit(il1_value)
                time.sleep(1)
            else:
                print("IL1 LINEAR sweeping INTERRUPTED")
                break

        # logging.info("Now reset to the initial value (for safety in testing)")
        # self.client.SetILFocus((lower + upper-step)//2)
        # time.sleep(wait_time_s)
