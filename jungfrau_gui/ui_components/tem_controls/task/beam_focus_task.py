import time
import logging
from datetime import datetime as dt

from .task import Task

from ..toolbox.fit_beam_intensity import fit_2d_gaussian_roi, fit_2d_gaussian_roi_test

from simple_tem import TEMClient

IL1_0 = 21902 #40345
ILs_0 = [33040, 32688]

class BeamFitTask(Task):
    def __init__(self, control_worker):
        super().__init__(control_worker, "BeamFit")
        self.duration_s = 60 # should be replaced with a practical value
        self.estimateds_duration = self.duration_s + 0.1
        self.control = control_worker        
        self.client = TEMClient("localhost", 3535,  verbose=False)

    def run(self, init_IL1=IL1_0):

        logging.info("Start IL1 rough-sweeping.")
        amp_guess_1, il1_guess1 = self.sweep_il1_linear(init_IL1 - 500, init_IL1 + 500, 25)
        self.client.SetILFocus(il1_guess1)
        amp_last_fit = self.fit().best_values["amplitude"]
        print(f" ACTUAL POSITION ({self.client.GetIL1()}), the GUESS WAS ({il1_guess1})")
        print(f" ACTUAL PEAK ({amp_last_fit}), THE GUESS WAS ({amp_guess_1})  ")

        """ logging.info("Start ILs rough-sweeping.")
        _, _, ils_guess1 = self.sweep_stig_linear(1000, 50)
        # self.tem_command("defl", "SetILs", ils_guess1)
        self.client.SetILs(ils_guess1[0], ils_guess1[1])
        time.sleep(1) """
               
        
        """ logging.info("Start IL1 fine-sweeping.")
        _, il1_guess2 = self.sweep_il1_linear(il1_guess1 - 50, il1_guess1 + 50, 5)
        self.client.SetILFocus(il1_guess2)
        time.sleep(1)

        logging.info("Start ILs fine-sweeping.")
        _, _, ils_guess2 = self.sweep_stig_linear(50, 5)
        self.client.SetILs(ils_guess2[0], ils_guess2[1])
        time.sleep(1) """

        if self.control.fitterWorkerReady == True:
            self.control.tem_action.tem_tasks.beamAutofocus.setText("Remove axis / pop-up")   
        else:
            print("********************* Emitting 'remove_ellipse' signal from -FITTING- Thread *********************")
            self.control.remove_ellipse.emit()  
    
    def sweep_il1_linear(self, lower, upper, step, wait_time_s=0.2):
        max_amplitude = 0
        max_il1value = None

        for il1_value in range(lower, upper, step):
            print(f"********************* fitterWorkerReady = {self.control.fitterWorkerReady}")
            if self.control.fitterWorkerReady == True:
                self.client.SetILFocus(il1_value)
                logging.debug(f"{dt.now()}, il1_value = {il1_value}")
                # time.sleep(wait_time_s) # sleep 1
                """ *** Fitting *** """
                fit_result = self.fit()
                amplitude = float(fit_result.best_values['amplitude']) # Determine peak value (amplitude)
                """ *************** """
                if max_amplitude < amplitude:
                    max_amplitude = amplitude
                    max_il1value = il1_value

                time.sleep(wait_time_s) # sleep 2
                logging.debug(f"{dt.now()}, amplitude = {amplitude}")
            else:
                print("IL1 LINEAR sweeping INTERRUPTED")
                break

        logging.info("Now reset to the initial value (for safety in testing)")
        self.client.SetILFocus((lower + upper)//2)
        time.sleep(1)

        return max_amplitude, max_il1value
        
    def move_to_stigm(self, stigm_x, stigm_y):
        # self.tem_command("defl", "SetILs", [stigm_x, stigm_y])
        self.client.SetILs(stigm_x, stigm_y)
        
    def sweep_stig_linear(self, deviation, step, wait_time_s=0.2, init_stigm=ILs_0):
        min_sigma1 = 1000
        min_stigmvalue = init_stigm
        best_ratio = 2

        for stigmx_value in range(init_stigm[0]-deviation, init_stigm[0]+deviation, step):
            print(f"********************* fitterWorkerReady = {self.control.fitterWorkerReady}")
            if self.control.fitterWorkerReady == True:
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
            else:
                print("ILs STIGMATISM in X axis sweeping INTERRUPTED")
                break

        # self.tem_command("defl", "SetILs", min_stigmvalue)
        self.client.SetILs(min_stigmvalue[0], min_stigmvalue[1])        
        time.sleep(1)
        
        for stigmy_value in range(init_stigm[1]-deviation, init_stigm[1]+deviation, step):
            print(f"********************* fitterWorkerReady = {self.control.fitterWorkerReady}")
            if self.control.fitterWorkerReady == True:
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
            else:
                print("ILs STIGMATISM in Y axis sweeping INTERRUPTED")
                break
        
        logging.debug("Now reset to the initial value (for safety in testing)")
        time.sleep(1)
        # self.tem_command("defl", "SetILs", init_stigm)
        self.client.SetILs(init_stigm[0], init_stigm[1])        

        return min_sigma1, best_ratio, min_stigmvalue
    
    def fit(self):
        # im = self.control.tem_action.parent.imageItem.image
        # roi = self.control.tem_action.parent.roi
        # fit_result = fit_2d_gaussian_roi_test(im, roi)
        fit_result = fit_2d_gaussian_roi_test(self.control.tem_action.parent.imageItem.image, 
                                              self.control.tem_action.parent.roi)
        self.control.fit_updated.emit(fit_result.best_values)
        return fit_result