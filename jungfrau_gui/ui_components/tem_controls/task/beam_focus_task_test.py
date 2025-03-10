import os
import time
import logging
import numpy as np
from .task import Task

from .... import globals
from PySide6.QtCore import Qt, QMetaObject, Signal
from datetime import datetime

from simple_tem import TEMClient

IL1_0 = 21780 #40345 40736
ILs_0 = [32920, 32776] #[32856, 32856]
WAIT_TIME_S = 0.1 # TODO: optimize value

class AutoFocusTask(Task):
    # Signal to notify the main thread that a new best result arrived
    newBestResult = Signal(dict)

    def __init__(self, control_worker):
        super().__init__(control_worker, "AutoFocus")
        self.duration_s = 60 # should be replaced with a practical value
        self.estimateds_duration = self.duration_s + 0.1
        self.control = control_worker
        self.tem_action = self.control.tem_action
        self.is_first_AutoFocus = True        
        self.client = TEMClient(globals.tem_host, 3535)
        # TODO Creates a freeze (May be update earlier?)
        self.lens_parameters = {
                                "il1": self.client.GetIL1(), # an integer
                                "ils": self.client.GetILs(), # two integers for stigmation
        }
        self.beam_fitter = self.control.beam_fitter
        self.results = []
        self.best_result = None

    def run(self, init_IL1=IL1_0, init_stigm=ILs_0):
        try:
            autofocus_start = time.perf_counter()

            # ------------------------
            # Interrupting TEM Polling
            # ------------------------
            if self.tem_action.tem_tasks.connecttem_button.started:
                QMetaObject.invokeMethod(self.tem_action.tem_tasks.connecttem_button, "click", Qt.QueuedConnection)

            while self.tem_action.tem_tasks.connecttem_button.started:
                time.sleep(0.01)

            logging.warning("TEM Connect button is OFF now.\nPolling is interrupted during data collection!")

            # Disable the Gaussian Fitting
            QMetaObject.invokeMethod(self.tem_action.tem_controls, 
                                    "disableGaussianFitButton", 
                                    Qt.QueuedConnection
            )
            logging.warning("Gaussian Fitting is disabled during Beam Autofocus task!")
            
            # ----------------------
            # Start parallel process
            # ----------------------
            self.beam_fitter.start()

            # --------------------------
            # Start IL1 Sweeping (ROUGH)
            # --------------------------
            logging.info("################ Start IL1 rough-sweeping ################")

            # Option A: Go and come back
            completed = self.sweep_il1_linear(init_IL1 - 50, init_IL1 + 55, 5)
            
            # Option B: Shoot straight
            # completed = self.sweep_il1_linear(init_IL1, init_IL1 + 105, 5)

            if not completed:
                logging.warning("ROUGH Sweep interrupted! Exiting AutoFocusTask::run() method...")
                return  # Exit the run method if the sweep was interrupted

            # Determine the rough optimal IL1 value
            il1_guess1 = self.best_result["il1_value"]
            logging.warning(f"{datetime.now()}, ROUGH IL1 OPTIMAL VALUE IS {il1_guess1}")
            
            # Once task finished, move lens to optimal position

            # Option A: Go and come back
            for il1_value in range(init_IL1 - 50, il1_guess1 + 10, 5): 
                self.client.SetILFocus(il1_value)
            self.client.SetILFocus(il1_guess1)

            # Option B: Shoot straight
            # for il1_value in range(init_IL1, il1_guess1+5, 5): 
            #     self.client.SetILFocus(il1_value)

            self.lens_parameters["il1"] = il1_guess1
            
            autofocus_end = time.perf_counter()
            autofocus_time = autofocus_end - autofocus_start
            logging.warning(f" ###### ROUGH SWEEP took {autofocus_time:.6f} seconds")

            print(self.results)

        except Exception as e:
            logging.error(f"Unexpected error during beam focusing: {e}")
        finally:
            '''
            # Restarting TEM polling
            if not self.tem_action.tem_tasks.connecttem_button.started:
                QMetaObject.invokeMethod(self.tem_action.tem_tasks.connecttem_button, "click", Qt.QueuedConnection)

            while not self.tem_action.tem_tasks.connecttem_button.started:
                time.sleep(0.1)

            logging.warning('Polling of TEM-info restarted.')
            '''
            # Once done, call your cleanup logic
            self.cleanup()
    
    def sweep_il1_linear(self, lower, upper, step, wait_time_s=WAIT_TIME_S):
        for il1_value in range(lower, upper, step):
            # Check if the beam fitter process is still alive.
            if not self.beam_fitter.fitting_process.is_alive():
                logging.error("GaussianFitterMP process has terminated unexpectedly. Aborting sweep.")
                return False

            if not self.control.sweepingWorkerReady:
                logging.warning("Interrupting sweep due to sweepingWorkerReady=False")
                return False

            # Set IL1 to current position
            iter_start = time.perf_counter()
            logging.info(datetime.now().strftime(" NEW SWEEP @ %H:%M:%S.%f")[:-3])
            self.client.SetILFocus(il1_value)
            iter_end = time.perf_counter()
            iter_time = iter_end - iter_start
            logging.critical(f"SetILFocus({il1_value}) took {iter_time:.6f} seconds")

            """ self.lens_parameters["ils"] = self.client.GetILs() # ??? Double checking if ILs changed without explicitly changing it """

            # (Optional?) small wait for hardware to stabilize
            time.sleep(wait_time_s)

            # Update lens_parameters so we know what was used
            self.lens_parameters["il1"] = il1_value

            # Option 1
            # Now request a fit. We'll pass the current image & ROI.
            image_data = self.tem_action.parent.imageItem.image.copy()
            roi = self.tem_action.parent.roi
            logging.info(datetime.now().strftime(" UPDATED PARAMS FOR FITTER @ %H:%M:%S.%f")[:-3])
            self.beam_fitter.updateParams(image_data, roi) 

            time.sleep(3*wait_time_s)

            # Prepare ROI data as a serializable dictionary.
            """
            # Option 2
            roi = self.tem_action.parent.roi
            roi_data = {
                "pos": [roi.pos().x(), roi.pos().y()],
                "size": [roi.size().x(), roi.size().y()]
            }
            # Trigger capture & fitting in the worker process.
            self.beam_fitter.trigger_capture(roi_data)
             """

            # time.sleep(wait_time_s)

            # Wait for the result (blocking in this thread only!)
            fit_result = self.beam_fitter.fetch_result()
            if fit_result is None:
                logging.warning("No fit result arrived in time; continuing anyway.")
                continue

            # Draw fitting result on ui for last captured frame
            """ self.control.draw_ellipses_on_ui.emit(fit_result) """

            # Process the result
            self.process_fit_results(fit_result)

        return True

    def process_fit_results(self, fit_values):
        """
        Save the result, compute FOM, etc.
        """
        # Suppose fit_values is a dict like {"sigma_x":..., "sigma_y":...}
        sigma_x = float(fit_values["sigma_x"])
        sigma_y = float(fit_values["sigma_y"])
        area = sigma_x * sigma_y
        aspect_ratio = max(sigma_x, sigma_y) / min(sigma_x, sigma_y)
        fom = area * aspect_ratio

        result_dict = {
            "il1_value": self.lens_parameters["il1"],
            "ils_value": self.lens_parameters["ils"],
            "sigma_x": sigma_x,
            "sigma_y": sigma_y,
            "area": area,
            "aspect_ratio": aspect_ratio,
            "fom": fom,
        }
        self.results.append(result_dict)

        # Track best
        if self.best_result is None or fom < self.best_result["fom"]:
            self.best_result = result_dict
            # Debugging: notify the main GUI thread 
            self.newBestResult.emit(result_dict)
        
        logging.info(datetime.now().strftime(" FIT RESULTS PROCESSED @ %H:%M:%S.%f")[:-3])

    def cleanup(self):
        """
        Clean up the fitter and references.
        """
        if self.beam_fitter is not None:
            self.beam_fitter.stop()   # This calls input_queue.put(None), .join(), etc.
            # self.beam_fitter = None   # So we don't accidentally reuse it.