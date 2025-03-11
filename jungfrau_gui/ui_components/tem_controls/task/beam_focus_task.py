import os
import time
import logging
import numpy as np
from .task import Task

from .... import globals
from PySide6.QtCore import Qt, QMetaObject, Signal
from datetime import datetime

from simple_tem import TEMClient

IL1_0 = 21780 #21902 #40345 40736
ILs_0 = [32920, 32776] #[33040, 32688] #[32856, 32856]
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

            """ ----------------
            # Start IL1 Sweeping 
            ---------------- """
            # logging.info("################ Start IL1 rough-sweeping ################")

            # # Option A: Go and come back
            # completed = self.sweep_il1_linear(init_IL1 - 50, init_IL1 + 55, 5)
            
            # # Option B: Shoot straight
            # # completed = self.sweep_il1_linear(init_IL1, init_IL1 + 105, 5)

            # if not completed:
            #     logging.warning("ROUGH Sweep interrupted! Exiting AutoFocusTask::run() method...")
            #     return  # Exit the run method if the sweep was interrupted

            # # Determine the rough optimal IL1 value
            # il1_guess1 = self.best_result["il1_value"]
            # logging.warning(f"{datetime.now()}, ROUGH IL1 OPTIMAL VALUE IS {il1_guess1}")
            
            # # Once task finished, move lens to optimal position

            # # Option A: Go and come back
            # for il1_value in range(init_IL1 - 50, il1_guess1 + 10, 5): 
            #     self.client.SetILFocus(il1_value)
            # self.client.SetILFocus(il1_guess1)

            # # Option B: Shoot straight
            # # for il1_value in range(init_IL1, il1_guess1+5, 5): 
            # #     self.client.SetILFocus(il1_value)

            # self.lens_parameters["il1"] = il1_guess1

            """ ----------------
            # Start ILs Sweeping 
            ---------------- """

            logging.info("################ Start ILs rough-sweeping ################")
            completed = self.sweep_stig_linear(init_stigm=init_stigm, deviation=500, step=100)
            if not completed:
                logging.warning("STIG Sweep interrupted! Exiting AutoFocusTask::run() method...")
                return  # Exit the run method if the sweep was interrupted

            # Determine the rough optimal ILs value
            ils_guess1 = self.best_result["ils_value"]
            logging.warning(f"{datetime.now()}, ROUGH ILs OPTIMAL VALUE IS {ils_guess1}")

            # Once task finished, move lens to optimal position 
            for ils_x_value in range(ILs_0[0] - 500, ils_guess1[0] + 600, 100): 
                for ils_y_value in range(ILs_0[1] - 500, ils_guess1[1] + 600, 50): 
                    self.client.SetILs(ils_x_value, ils_y_value)
            self.client.SetILs(*ils_guess1)
            time.sleep(1)

            self.lens_parameters["ils"] = ils_guess1
            
            autofocus_end = time.perf_counter()
            autofocus_time = autofocus_end - autofocus_start
            logging.warning(f" ###### ROUGH SWEEP took {autofocus_time:.6f} seconds")

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
            # Check if the beam fitter process is still alive.
            if not self.beam_fitter.fitting_process.is_alive():
                logging.error("GaussianFitterMP process has terminated unexpectedly. Aborting sweep.")
                return False

            if not self.control.sweepingWorkerReady:
                logging.warning("Interrupting sweep due to sweepingWorkerReady=False")
                return False

            # Set IL1 to current position
            iter_start = time.perf_counter()
            logging.info(datetime.now().strftime(" BEGIN SWEEP @ %H:%M:%S.%f")[:-3])
            self.client.SetILFocus(il1_value)
            logging.info(datetime.now().strftime(" END SWEEP @ %H:%M:%S.%f")[:-3])
            iter_end = time.perf_counter()
            iter_time = iter_end - iter_start
            logging.critical(f"SetILFocus({il1_value}) took {iter_time:.6f} seconds")

            # (Optional?) small wait for hardware to stabilize
            time.sleep(wait_time_s)

            # Update lens_parameters so we know what was used
            self.lens_parameters["il1"] = il1_value

            """
            # Option 1
            # Now request a fit. We'll pass the current image & ROI.
            image_data = self.tem_action.parent.imageItem.image.copy()
            roi = self.tem_action.parent.roi
            logging.info(datetime.now().strftime(" UPDATED PARAMS FOR FITTER @ %H:%M:%S.%f")[:-3])
            self.beam_fitter.updateParams(image_data, roi) 

            time.sleep(3*wait_time_s)
            """

            # Optional - capture the success status for logging
            fit_success = self.request_fit_and_process_result()
            if not fit_success:
                logging.warning(f"Failed to get a valid fit for IL1={il1_value}")

            """ # Prepare ROI data as a serializable dictionary.
            # Option 2
            roi = self.tem_action.parent.roi
            roi_data = {
                "pos": [roi.pos().x(), roi.pos().y()],
                "size": [roi.size().x(), roi.size().y()]
            }
            # Trigger capture & fitting in the worker process.
            self.beam_fitter.trigger_capture(roi_data)

            # Wait for the result (blocking in this thread only!)
            fit_result = self.beam_fitter.fetch_result()
            if fit_result is None:
                logging.warning("No fit result arrived in time; continuing anyway.")
                continue

            # Draw fitting result on ui for last captured frame
            ''' self.control.draw_ellipses_on_ui.emit(fit_result) '''

            # Process the result
            self.process_fit_results(fit_result) """

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

        # Parameters
        init_stigm : list or tuple of length 2
            The initial stigmation values along the X and Y axes, e.g. [ils_x0, ils_y0].
        deviation : int
            The ± range around `init_stigm` to explore for each axis.
        step : int
            The increment between stigmation values in each axis.
        wait_time_s : float, optional
            The time (in seconds) to wait after setting each stigmation value before requesting
            a fit. Defaults to the class constant `WAIT_TIME_S`.

        # Returns
        bool
            True if the sweep completes successfully.
            False if the sweeping is interrupted (e.g., `sweepingWorkerReady` becomes False).
        """
        for ils_x in range(init_stigm[0] - deviation, init_stigm[0] + deviation + step, step):
            if not self.beam_fitter.fitting_process.is_alive():
                logging.error("GaussianFitterMP process has terminated unexpectedly. Aborting sweep.")
                return False

            if not self.control.sweepingWorkerReady:
                logging.warning(f"Interrupting Task - {self.control.task.task_name} - during STIG X Sweeping")
                return False

            for ils_y in range(init_stigm[1] - deviation, init_stigm[1] + deviation + step, step):
                # Check if the beam fitter process is still alive.
                if not self.beam_fitter.fitting_process.is_alive():
                    logging.error("GaussianFitterMP process has terminated unexpectedly. Aborting sweep.")
                    return False
                
                if not self.control.sweepingWorkerReady:
                    logging.warning(f"Interrupting Task - {self.control.task.task_name} - during STIG Y Sweeping")
                    return False
                
                # Set ILs lens to the current position
                # Set IL1 to current position
                iter_start = time.perf_counter()
                logging.info(datetime.now().strftime(" BEGIN STIG SWEEP @ %H:%M:%S.%f")[:-3])
                self.client.SetILs(ils_x, ils_y)
                logging.info(datetime.now().strftime(" END STIG SWEEP @ %H:%M:%S.%f")[:-3])
                iter_end = time.perf_counter()
                iter_time = iter_end - iter_start
                logging.critical(f"SetILs({ils_x}, {ils_y}) took {iter_time:.6f} seconds")

                # Wait for the system to stabilize after setting ILs
                time.sleep(wait_time_s)

                # Update dictionnary
                self.lens_parameters["ils"] = [ils_x, ils_y]

                # Request fit and process results - skip to next iteration if it fails
                fit_success = self.request_fit_and_process_result()
                if not fit_success:
                    logging.warning(f"Failed to get a valid fit for ILs=[{ils_x}, {ils_y}]")

                """ # Prepare ROI data as a serializable dictionary.
                # Option 2
                roi = self.tem_action.parent.roi
                roi_data = {
                    "pos": [roi.pos().x(), roi.pos().y()],
                    "size": [roi.size().x(), roi.size().y()]
                }
                # Trigger capture & fitting in the worker process.
                self.beam_fitter.trigger_capture(roi_data)

                # Wait for the result (blocking in this thread only!)
                fit_result = self.beam_fitter.fetch_result()
                if fit_result is None:
                    logging.warning("No fit result arrived in time; continuing anyway.")
                    continue

                # Draw fitting result on ui for last captured frame
                ''' self.control.draw_ellipses_on_ui.emit(fit_result) '''

                # Process the result
                self.process_fit_results(fit_result) """

        return True

    def request_fit_and_process_result(self, roi=None):
        """
        Request a beam fit and process the results.
        
        # Args
        roi: Optional ROI override. If None, uses the current ROI from the UI.
            
        # Returns
        bool: True if the fit was successful, False otherwise
        """
        if roi is None:
            roi = self.tem_action.parent.roi
            roi_data = {
                "pos": [roi.pos().x(), roi.pos().y()],
                "size": [roi.size().x(), roi.size().y()]
            }
        else:
            roi_data = roi
            
        # Trigger capture & fitting in the worker process
        self.beam_fitter.trigger_capture(roi_data)
        
        # Wait for the result (blocking in this thread only!)
        fit_result = self.beam_fitter.fetch_result()
        
        if fit_result is None:
            logging.warning("No fit result arrived in time; skipping this iteration.")
            return False
        
        # Process the result
        self.process_fit_results(fit_result)
        
        # Optionally draw fitting result on UI (uncomment if needed)
        # self.control.draw_ellipses_on_ui.emit(fit_result)
        
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
        print("=============================================================================")

    def cleanup(self):
        """
        Clean up the fitter and references.
        """
        if self.beam_fitter is not None:
            self.beam_fitter.stop()   # This calls input_queue.put(None), .join(), etc.