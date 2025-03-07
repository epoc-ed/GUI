import os
import time
import logging
import numpy as np
from .task import Task

from .... import globals
from PySide6.QtCore import Qt, QMetaObject
from datetime import datetime

from simple_tem import TEMClient

IL1_0 = 21902 #40345 40736
ILs_0 = [33040, 32688] #[32856, 32856]
WAIT_TIME_S = 0.5 # TODO: optimize value

class AutoFocusTask(Task):
    def __init__(self, control_worker):
        super().__init__(control_worker, "AutoFocus")
        self.duration_s = 60 # should be replaced with a practical value
        self.estimateds_duration = self.duration_s + 0.1
        self.control = control_worker
        self.tem_action = self.control.tem_action
        self.is_first_AutoFocus = True        
        self.client = TEMClient(globals.tem_host, 3535)
        self.lens_parameters = {
                                "il1": self.client.GetIL1(), # an integer
                                "ils": self.client.GetILs(), # two integers for stigmation
        }
        self.results = []

    def run(self, init_IL1=IL1_0, init_stigm=ILs_0):
        try:
            # ------------------------
            # Interrupting TEM Polling
            # ------------------------
            if self.tem_action.tem_tasks.connecttem_button.started:
                QMetaObject.invokeMethod(self.tem_action.tem_tasks.connecttem_button, "click", Qt.QueuedConnection)

            while self.tem_action.tem_tasks.connecttem_button.started:
                time.sleep(0.1)

            logging.warning("TEM Connect button is OFF now.\nPolling is interrupted during data collection!")

            # Disable the Gaussian Fitting
            QMetaObject.invokeMethod(self.tem_action.tem_controls, 
                                    "disableGaussianFitButton", 
                                    Qt.QueuedConnection
            )
            logging.warning("Gaussian Fitting is disabled during Beam Autofocus task!")
            
            # --------------------------
            # Start IL1 Sweeping (ROUGH)
            # --------------------------
            logging.info("################ Start IL1 rough-sweeping ################")
            completed = self.sweep_il1_linear(init_IL1 - 500, init_IL1 + 550, 50)
            if not completed:
                logging.warning("ROUGH Sweep interrupted! Exiting AutoFocusTask::run() method...")
                return  # Exit the run method if the sweep was interrupted

            # Determine the rough optimal IL1 value
            best_result_IL1_rough = min(self.results, key=lambda x: x["fom"])
            il1_guess1 = best_result_IL1_rough["il1_value"]
            logging.warning(f"{datetime.now()}, ROUGH IL1 OPTIMAL VALUE IS {il1_guess1}")

            # Once task finished, move lens to optimal position 
            for il1_value in range(init_IL1 - 500, il1_guess1+150, 50): 
                self.client.SetILFocus(il1_value)
                time.sleep(WAIT_TIME_S)
            self.client.SetILFocus(il1_guess1)
            time.sleep(1)

            self.lens_parameters["il1"] = il1_guess1
            
            # ------------------
            # Start ILs Sweeping 
            # ------------------

            logging.info("################ Start ILs rough-sweeping ################")
            completed = self.sweep_stig_linear(init_stigm=init_stigm, deviation=1000, step=50)
            if not completed:
                logging.warning("STIG Sweep interrupted! Exiting AutoFocusTask::run() method...")
                return  # Exit the run method if the sweep was interrupted

            # Determine the rough optimal IL1 value
            best_result_ILs_rough = min(self.results, key=lambda x: x["fom"])
            ils_guess1 = best_result_ILs_rough["ils_value"]
            logging.warning(f"{datetime.now()}, ROUGH ILs OPTIMAL VALUE IS {ils_guess1}")
            
            # DEBUGGING ####################################
            # Check whether IL1 has changed
            print("@@@@@@@@@@ OPTIMAL LENS VALUES AFTER ROUGH IL1 and ILs SWEEPS @@@@@@@@@@")
            # for key, value in best_result_ILs_rough.items():
            #     print(f"{key}: {value}")
            logging.warning(f"Is IL1_guess the same after rough ILs sweep? --> {best_result_ILs_rough["il1_value"] == il1_guess1}")
            print("@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@")
            # ##############################################

            # Once task finished, move lens to optimal position 
            for ils_x_value in range(ILs_0[0] - 1000, ils_guess1[0] + 150, 50): 
                for ils_y_value in range(ILs_0[1] - 1000, ils_guess1[1] + 150, 50): 
                    self.client.SetILs(ils_x_value, ils_y_value)
                    time.sleep(WAIT_TIME_S)
            self.client.SetILs(*ils_guess1)
            time.sleep(1)

            self.lens_parameters["ils"] = ils_guess1

            # -------------------------
            # Start IL1 Sweeping (FINE)
            # -------------------------

            logging.info("################ Start IL1 fine-sweeping ################")
            completed = self.sweep_il1_linear(il1_guess1 - 45, il1_guess1 + 50, 5)
            if not completed:
                logging.warning("FINE Sweep interrupted! Exiting AutoFocusTask::run() method...")
                return  # Exit the run method if the sweep was interrupted

            # Determine the rough optimal IL1 value
            best_result_IL1_fine = min(self.results, key=lambda x: x["fom"])
            il1_guess2 = best_result_IL1_fine["il1_value"]
            logging.warning(f"{datetime.now()}, FINE IL1 OPTIMAL VALUE IS {il1_guess2}")

            # Once task finished, move lens to optimal position 
            for il1_value in range(il1_guess1 - 45, il1_guess2 + 15, 5):
                self.client.SetILFocus(il1_value)
                time.sleep(WAIT_TIME_S)
            self.client.SetILFocus(il1_guess2)
            time.sleep(1)

            self.lens_parameters["il1"] = il1_guess2
            
        except Exception as e:
            logging.error(f"Unexpected error during beam focusing: {e}")
        finally:
            # Restarting TEM polling
            if not self.tem_action.tem_tasks.connecttem_button.started:
                QMetaObject.invokeMethod(self.tem_action.tem_tasks.connecttem_button, "click", Qt.QueuedConnection)

            while not self.tem_action.tem_tasks.connecttem_button.started:
                time.sleep(0.1)

            logging.warning('Polling of TEM-info restarted.')
    
    def sweep_il1_linear(self, lower, upper, step, wait_time_s=WAIT_TIME_S):
        """
        Perform a linear sweep of IL1 TEM lens positions and request Gaussian fitting for each beam frame.

        This method adjusts the IL1 (Intermediate Lens 1) focus of a Transmission Electron Microscope (TEM)
        through a specified range of positions, incrementing by 'step'. At each lens position, it requests
        a (Super) Gaussian fitting for the current beam frame, representing the beam's status at that particular setting.

        The sweep continues as long as 'sweepingWorkerReady' is True. If it becomes False, the sweep is interrupted,
        and the method returns False to indicate that the sweep did not complete successfully.

        Parameters:
            - lower (int): The starting position value for the IL1 lens.
            - upper (int): The ending position value for the IL1 lens.
            - step (int): The increment between IL1 lens positions.
            - wait_time_s (float, optional): Time in seconds to wait after setting the IL1 focus before requesting a fit.

        """
        for il1_value in range(lower, upper, step):
            if not self.control.sweepingWorkerReady:
                logging.warning(f"Interrupting Task - {self.control.task.task_name} -")
                return False

            logging.warning(f"sweepingWorkerReady = {self.control.sweepingWorkerReady}")

            # Set IL1 lens to the current position
            self.client.SetILFocus(il1_value)
            logging.debug(f"{datetime.now()}, il1_value = {il1_value}")

            # Update dictionnary
            self.lens_parameters["il1"] = il1_value

            # Wait for the system to stabilize after setting IL1
            time.sleep(wait_time_s)

            # Emit the signal to request Gaussian fitting
            logging.info(datetime.now().strftime(" REQUESTED_FIT @ %H:%M:%S.%f")[:-3])
            # self.control.request_fit.emit(il1_value)
            self.control.request_fit.emit(self.lens_parameters)

            # Wait before proceeding to the next IL1 position
            time.sleep(1)
        
        return True

    def sweep_stig_linear(self, init_stigm, deviation, step, wait_time_s=WAIT_TIME_S):
        """
        Perform a linear sweep of the stigmation parameters in the X and Y directions.

        Starting from an initial stigmation value (`init_stigm = [ils_x0, ils_y0]`), this function
        scans over the range `[ils_x0 - deviation, ils_x0 + deviation]` for the X-axis and
        `[ils_y0 - deviation, ils_y0 + deviation]` for the Y-axis, incrementing in steps of `step`.
        At each stigmation setting, it sets the ILs lens, waits for the system to stabilize,
        and then requests a Gaussian (or Super-Gaussian) fit. The sweeping is aborted if
        `sweepingWorkerReady` becomes False at any point.

        Parameters
        ----------
        init_stigm : list or tuple of length 2
            The initial stigmation values along the X and Y axes, e.g. [ils_x0, ils_y0].
        deviation : int
            The ± range around `init_stigm` to explore for each axis.
        step : int
            The increment between stigmation values in each axis.
        wait_time_s : float, optional
            The time (in seconds) to wait after setting each stigmation value before requesting
            a fit. Defaults to the class constant `WAIT_TIME_S`.

        Returns
        -------
        bool
            True if the sweep completes successfully.
            False if the sweeping is interrupted (e.g., `sweepingWorkerReady` becomes False).

        Notes
        -----
        - The method updates the class attribute `lens_parameters["ils"]` with the current (X, Y)
        stigmation values before emitting the fit request signal.
        - A short additional wait of 1 second is included at the end of each X-axis iteration
        before proceeding to the next value in the sweep.
        - Logs at various stages indicate when a fit request is issued or if the sweep is interrupted.
        """
        for ils_x in range(init_stigm[0] - deviation, init_stigm[0] + deviation + step, step):
            if not self.control.sweepingWorkerReady:
                logging.warning(f"Interrupting Task - {self.control.task.task_name} - during STIG X Sweeping")
                return False

            for ils_y in range(init_stigm[1] - deviation, init_stigm[1] + deviation + step, step):
                if not self.control.sweepingWorkerReady:
                    logging.warning(f"Interrupting Task - {self.control.task.task_name} - during STIG Y Sweeping")
                    return False
                
                # Set ILs lens to the current position
                self.client.SetILs(ils_x, ils_y)
                logging.info(f"{datetime.now()}, ILs = [{ils_x}, {ils_y}]")

                # Update dictionnary
                self.lens_parameters["ils"] = [ils_x, ils_y]

                # Wait for the system to stabilize after setting ILs
                time.sleep(wait_time_s)

                # Emit the signal to request Gaussian fitting
                logging.info(datetime.now().strftime(" REQUESTED_FIT @ %H:%M:%S.%f")[:-3])
                self.control.request_fit.emit(self.lens_parameters)

                # Wait before proceeding to the next ILs_x position
                time.sleep(1)
        
        return True


# import time
# import logging
# from datetime import datetime as dt

# from .task import Task

# from ..toolbox.fit_beam_intensity import fit_2d_gaussian_roi, fit_2d_gaussian_roi_test

# from simple_tem import TEMClient

# IL1_0 = 21902 #40345
# ILs_0 = [33040, 32688]

# class AutoFocusTask(Task):
#     def __init__(self, control_worker):
#         super().__init__(control_worker, "AutoFocus")
#         self.duration_s = 60 # should be replaced with a practical value
#         self.estimateds_duration = self.duration_s + 0.1
#         self.control = control_worker        
#         self.client = TEMClient("temserver", 3535,  verbose=True)

#     def run(self, init_IL1=IL1_0):

#         logging.info("Start IL1 rough-sweeping.")
#         amp_guess_1, il1_guess1 = self.sweep_il1_linear(init_IL1 - 500, init_IL1 + 500, 25)
#         self.client.SetILFocus(il1_guess1)
#         amp_last_fit = self.fit().best_values["amplitude"]
#         print(f" ACTUAL POSITION ({self.client.GetIL1()}), the GUESS WAS ({il1_guess1})")
#         print(f" ACTUAL PEAK ({amp_last_fit}), THE GUESS WAS ({amp_guess_1})  ")

#         """ logging.info("Start ILs rough-sweeping.")
#         _, _, ils_guess1 = self.sweep_stig_linear(1000, 50)
#         # self.tem_command("defl", "SetILs", ils_guess1)
#         self.client.SetILs(ils_guess1[0], ils_guess1[1])
#         time.sleep(1) """
               
        
#         """ logging.info("Start IL1 fine-sweeping.")
#         _, il1_guess2 = self.sweep_il1_linear(il1_guess1 - 50, il1_guess1 + 50, 5)
#         self.client.SetILFocus(il1_guess2)
#         time.sleep(1)

#         logging.info("Start ILs fine-sweeping.")
#         _, _, ils_guess2 = self.sweep_stig_linear(50, 5)
#         self.client.SetILs(ils_guess2[0], ils_guess2[1])
#         time.sleep(1) """

#         if self.control.fitterWorkerReady == True:
#             self.control.tem_action.tem_tasks.beamAutofocus.setText("Remove axis / pop-up")   
#         else:
#             print("********************* Emitting 'remove_ellipse' signal from -FITTING- Thread *********************")
#             self.control.remove_ellipse.emit()  
    
#     def sweep_il1_linear(self, lower, upper, step, wait_time_s=0.2):
#         max_amplitude = 0
#         max_il1value = None

#         for il1_value in range(lower, upper, step):
#             print(f"********************* fitterWorkerReady = {self.control.fitterWorkerReady}")
#             if self.control.fitterWorkerReady == True:
#                 self.client.SetILFocus(il1_value)
#                 logging.debug(f"{dt.now()}, il1_value = {il1_value}")
#                 # time.sleep(wait_time_s) # sleep 1
#                 """ *** Fitting *** """
#                 fit_result = self.fit()
#                 amplitude = float(fit_result.best_values['amplitude']) # Determine peak value (amplitude)
#                 """ *************** """
#                 if max_amplitude < amplitude:
#                     max_amplitude = amplitude
#                     max_il1value = il1_value

#                 time.sleep(wait_time_s) # sleep 2
#                 logging.debug(f"{dt.now()}, amplitude = {amplitude}")
#             else:
#                 print("IL1 LINEAR sweeping INTERRUPTED")
#                 break

#         logging.info("Now reset to the initial value (for safety in testing)")
#         self.client.SetILFocus((lower + upper)//2)
#         time.sleep(1)

#         return max_amplitude, max_il1value
        
#     def move_to_stigm(self, stigm_x, stigm_y):
#         # self.tem_command("defl", "SetILs", [stigm_x, stigm_y])
#         self.client.SetILs(stigm_x, stigm_y)
        
#     def sweep_stig_linear(self, deviation, step, wait_time_s=0.2, init_stigm=ILs_0):
#         min_sigma1 = 1000
#         min_stigmvalue = init_stigm
#         best_ratio = 2

#         for stigmx_value in range(init_stigm[0]-deviation, init_stigm[0]+deviation, step):
#             print(f"********************* fitterWorkerReady = {self.control.fitterWorkerReady}")
#             if self.control.fitterWorkerReady == True:
#                 # self.tem_command("defl", "SetILs", [stigmx_value, init_stigm[1]])
#                 self.client.SetILs(stigmx_value, init_stigm[1])

#                 time.sleep(wait_time_s)
#                 logging.debug(f"{dt.now()}, stigmx_value = {stigmx_value}")
                
#                 """ *** Fitting *** """
#                 # sigma1 = self.control.stream_receiver.fit[0] # smaller sigma value (shorter axis)
#                 im = self.control.tem_action.parent.imageItem.image
#                 roi = self.control.tem_action.parent.roi
#                 fit_result = fit_2d_gaussian_roi_test(im, roi)
#                 # Update pop-up plot and drawn ellipse 
#                 self.control.fit_updated.emit(fit_result.best_values)  # Emit the signal
#                 # Determine smaller sigma (sigma1)
#                 sigma_x = float(fit_result.best_values['sigma_x'])
#                 sigma_y = float(fit_result.best_values['sigma_y'])
#                 sigma1 = min(sigma_x, sigma_y)
#                 """ *************** """
                
#                 if min_sigma1 > sigma1:
#                     min_sigma1 = sigma1
#                     min_stigmvalue = [stigmx_value, init_stigm[1]]
#             else:
#                 print("ILs STIGMATISM in X axis sweeping INTERRUPTED")
#                 break

#         # self.tem_command("defl", "SetILs", min_stigmvalue)
#         self.client.SetILs(min_stigmvalue[0], min_stigmvalue[1])        
#         time.sleep(1)
        
#         for stigmy_value in range(init_stigm[1]-deviation, init_stigm[1]+deviation, step):
#             print(f"********************* fitterWorkerReady = {self.control.fitterWorkerReady}")
#             if self.control.fitterWorkerReady == True:
#                 # self.tem_command("defl", "SetILs", [min_stigmvalue[0], stigmy_value])
#                 self.client.SetILs(min_stigmvalue[0], stigmy_value)        

#                 time.sleep(wait_time_s)
#                 logging.debug(f"{dt.now()}, stigmy_value = {stigmy_value}")
                
#                 """ *** Fitting *** """
#                 # ratio = self.control.stream_receiver.fit[0] # sigma ratio
#                 im = self.control.tem_action.parent.imageItem.image
#                 roi = self.control.tem_action.parent.roi
#                 fit_result = fit_2d_gaussian_roi_test(im, roi)
#                 # Update pop-up plot and drawn ellipse 
#                 self.control.fit_updated.emit(fit_result.best_values)  # Emit the signal
#                 # Determine sigmas ratio
#                 sigma_x = float(fit_result.best_values['sigma_x'])
#                 sigma_y = float(fit_result.best_values['sigma_y'])
#                 ratio = max(sigma_x, sigma_y)/min(sigma_x, sigma_y)
#                 """ *************** """
                
#                 if abs(best_ratio - 1) > abs(ratio - 1):
#                     best_ratio = ratio
#                     min_stigmvalue = [min_stigmvalue[0], stigmy_value]
#             else:
#                 print("ILs STIGMATISM in Y axis sweeping INTERRUPTED")
#                 break
        
#         logging.debug("Now reset to the initial value (for safety in testing)")
#         time.sleep(1)
#         # self.tem_command("defl", "SetILs", init_stigm)
#         self.client.SetILs(init_stigm[0], init_stigm[1])        

#         return min_sigma1, best_ratio, min_stigmvalue
    
#     def fit(self):
#         # im = self.control.tem_action.parent.imageItem.image
#         # roi = self.control.tem_action.parent.roi
#         # fit_result = fit_2d_gaussian_roi_test(im, roi)
#         fit_result = fit_2d_gaussian_roi_test(self.control.tem_action.parent.imageItem.image, 
#                                               self.control.tem_action.parent.roi)
#         self.control.fit_updated.emit(fit_result.best_values)
#         return fit_result