import os
import time
import logging
import numpy as np
from .task import Task

from .... import globals
from PySide6.QtCore import Qt, QMetaObject, Signal
from datetime import datetime

from simple_tem import TEMClient

IL1_0 = 21780 # 21819 
ILS_0 = [32920, 32776] # [32820, 32976]
WAIT_TIME_S = 0.25 # TODO: optimize value

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
        # Start from a known set (but creates a freeze) 
        self.client.SetILFocus(IL1_0)
        self.client.SetILs(*ILS_0)
        self.lens_parameters = {
                                "il1": IL1_0, # an integer
                                "ils": ILS_0, # two integers for stigmation
        }
        self.beam_fitter = self.control.beam_fitter
        self.results = []
        self.best_result = None

        # Fast mode
        self.rapid_mode = self.tem_action.tem_tasks.fast_autofocus_checkbox.isChecked()

        # Track current optimization mode
        self._current_mode = None
        
        # Tracking previous best values for each mode
        self._best_focus = None
        self._best_stigmation = None

    def run(self, init_IL1=IL1_0, init_stigm=ILS_0, time_budget=15):
        try:
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

            if self.rapid_mode:
                # Use the rapid optimization approach
                logging.warning(" ############ RAPID MODE ############ ")
                results = self.rapid_autofocus(init_IL1, init_stigm, time_budget)
                print("Results of fast focusing:") 
                print(results)
            else:
                logging.warning(" ############ SLOW MODE ############ ")  
                self.slow_focus()

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

    ##########
    # METHOD A
    ##########
    def rapid_parabolic_focus(self, init_IL1, range_width=100, num_points=5, wait_time_s=WAIT_TIME_S):
        """
        Rapidly optimize beam focus by sampling points and fitting a parabola.
        
        Args:
            init_IL1: Initial IL1 value to center the search around
            range_width: Total width of the search range (init_IL1 ± range_width/2)
            num_points: Number of points to sample for fitting the parabola
            wait_time_s: Wait time between lens adjustments
            
        Returns:
            dict: Result dictionary with optimal IL1 and metrics
        """
        # Set mode to focus optimization
        self._current_mode = "IL1_FOCUS"
        
        # Record start time
        start_time = time.perf_counter()
        logging.info("################ Starting rapid parabolic focus ################")
        
        # Generate sampling points, distributed across the range
        lower = init_IL1 - range_width//2
        upper = init_IL1 + range_width//2
        
        # Create sampling points - include endpoints and distribute the rest
        il1_sample_points = []
        if num_points <= 2:
            il1_sample_points = [lower, upper]
        else:
            # Always include the endpoints and middle
            il1_sample_points = [lower, init_IL1, upper]
            
            # Add more points if requested
            if num_points > 3:
                # Add points at 1/4 and 3/4 of the range
                quarter_point = lower + (upper - lower) // 4
                three_quarter_point = lower + 3 * (upper - lower) // 4
                il1_sample_points.append(quarter_point)
                il1_sample_points.append(three_quarter_point)
                
            # Sort the points
            il1_sample_points.sort()
        
        # Include the initial point in the sampling if not already present
        if init_IL1 not in il1_sample_points:
            il1_sample_points.append(init_IL1)
            il1_sample_points.sort()
        
        # Limit to requested number of points
        il1_sample_points = il1_sample_points[:num_points]
        
        logging.info(f"Sampling IL1 values: {il1_sample_points}")
        
        # Store measurements
        measurements = []
        
        # Sample each point
        for il1 in il1_sample_points:
            # Check if process is alive
            if not self.check_process_alive():
                return None
            
            # Approach with hysteresis compensation ?
            # self.goto_il1_with_hysteresis_compensation(il1, margin=20)
            self.client.SetILFocus(il1)
            time.sleep(wait_time_s)
            
            # Request fit and process result
            fit_success = self.request_fit_and_process_result()
            if not fit_success:
                logging.warning(f"Failed to get valid fit for IL1={il1}")
                continue
            
            # If we got a valid result, record it
            if self.best_result and "area" in self.best_result:
                measurements.append((il1, self.best_result["area"]))
                logging.info(f"Measured IL1={il1}, area={self.best_result['area']:.2f}")
        
        # Check if we have enough measurements to fit a parabola
        if len(measurements) < 3:
            logging.warning("Not enough valid measurements to fit parabola")
            
            # Return best result found if available
            if self.best_result:
                logging.info(f"Using best measured result: IL1={self.best_result['il1_value']}")
                return self.best_result
            else:
                logging.warning("No valid measurements found")
                return None
        
        # Extract data for fitting
        il1_values = np.array([m[0] for m in measurements])
        area_values = np.array([m[1] for m in measurements])
        
        try:
            # Fit quadratic curve: y = ax^2 + bx + c
            coeffs = np.polyfit(il1_values, area_values, 2)
            a, b, c = coeffs
            
            # Check if we have a proper minimum (parabola opens upward)
            if a <= 0:
                logging.warning("Fitted curve doesn't have a proper minimum (a <= 0)")
                # Return the best measured result
                best_idx = np.argmin(area_values)
                best_il1 = il1_values[best_idx]
                logging.info(f"Using best measured point: IL1={best_il1}")
                
                # Move to best measured point
                self.goto_il1_with_hysteresis_compensation(int(best_il1))
                
                # Get the corresponding result
                for result in self.results:
                    if result["il1_value"] == int(best_il1):
                        return result
                
                # If we can't find the exact result, return best_result
                return self.best_result
            
            # Calculate theoretical minimum of the parabola
            theoretical_min_il1 = -b / (2 * a)
            theoretical_min_area = a * theoretical_min_il1**2 + b * theoretical_min_il1 + c
            
            logging.info(f"Parabola fit: a={a:.6f}, b={b:.2f}, c={c:.2f}")
            logging.warning(f" <><><><>><><><> Theoretical minimum: IL1={theoretical_min_il1:.1f}, area={theoretical_min_area:.2f}")
            
            # Check if the minimum is within our sampled range
            if not (lower <= theoretical_min_il1 <= upper):
                logging.warning(f"Theoretical minimum ({theoretical_min_il1:.1f}) outside sampled range [{lower}, {upper}]")
                
                # If outside range, use the best measured value
                best_idx = np.argmin(area_values)
                best_il1 = il1_values[best_idx]
                logging.info(f"Using best measured point: IL1={best_il1}")
                theoretical_min_il1 = best_il1
            
            # Convert to integer
            optimal_il1 = int(round(theoretical_min_il1))
            
            # Move to the predicted optimal position
            self.goto_il1_with_hysteresis_compensation(optimal_il1)
            
            # Measure at the predicted optimum
            fit_success = self.request_fit_and_process_result()
            if not fit_success:
                logging.warning(f"Failed to get valid fit at predicted optimum IL1={optimal_il1}")
                # Return best result seen so far
                return self.best_result
            
            # Calculate elapsed time
            elapsed_time = time.perf_counter() - start_time
            logging.info(f"Parabolic focus completed in {elapsed_time:.2f} seconds")
            
            # Return the final result
            return self.best_result
            
        except Exception as e:
            logging.error(f"Error during parabolic fitting: {e}")
            
            # Return best result seen so far
            if self.best_result:
                return self.best_result
            else:
                return None

    def rapid_stigmation_optimization(self, init_stigm, deviation=100, num_points=10, wait_time_s=WAIT_TIME_S):
        """
        Rapidly optimize beam stigmation using a simplified grid search.
        
        Args:
            init_stigm: Initial stigmation values [x, y]
            deviation: Range to search around center
            num_points: Number of points to sample in each dimension (reduced grid)
            wait_time_s: Wait time between lens adjustments
            
        Returns:
            dict: Result dictionary with optimal stigmation values and metrics
        """
        # Set mode to stigmation optimization
        self._current_mode = "ILS_STIGMATION"
        
        # Record start time
        start_time = time.perf_counter()
        logging.info("################ Starting rapid stigmation optimization ################")
        
        # We'll implement a simplified grid search focused on the most promising areas
        # Define a reduced grid around the initial point
        x_center, y_center = init_stigm
        
        # Create cruciform sampling pattern instead of full grid
        # This samples along the X and Y axes more densely
        points = []
        
        # Add center point
        points.append((x_center, y_center))
        
        # Add points along X axis
        x_offsets = np.linspace(-deviation, deviation, num_points)
        for x_offset in x_offsets:
            if x_offset != 0:  # Skip center (already added)
                points.append((int(x_center + x_offset), y_center))
        
        # Add points along Y axis
        y_offsets = np.linspace(-deviation, deviation, num_points)
        for y_offset in y_offsets:
            if y_offset != 0:  # Skip center (already added)
                points.append((x_center, int(y_center + y_offset)))
        
        # Sample each point
        for ils_x, ils_y in points:
            # Check if process is alive
            if not self.check_process_alive():
                return None
            
            # Set stigmation with hysteresis compensation ?
            # self.goto_ils_with_hysteresis_compensation([ils_x, ils_y])
            self.client.SetILs(ils_x, ils_y)
            time.sleep(wait_time_s)
            
            # Request fit and process result
            fit_success = self.request_fit_and_process_result()
            if not fit_success:
                logging.warning(f"Failed to get valid fit for ILs=[{ils_x}, {ils_y}]")
                continue
        
        # After sampling, find the best point
        if not self.best_result:
            logging.warning("No valid measurements found")
            return None
        
        # Best point should already be in self.best_result due to process_fit_results updating it
        optimal_ils = self.best_result.get("ils_value")
        
        # Ensure we're at the optimal position
        self.goto_ils_with_hysteresis_compensation(optimal_ils)
        
        # Calculate elapsed time
        elapsed_time = time.perf_counter() - start_time
        logging.info(f"Rapid stigmation completed in {elapsed_time:.2f} seconds")
        
        return self.best_result

    def rapid_autofocus(self, init_IL1=None, init_stigm=None, time_budget_seconds=15):
        """
        Perform rapid autofocus optimization within a specified time budget.
        
        Args:
            init_IL1: Initial IL1 value (if None, uses current value)
            init_stigm: Initial stigmation values [x, y] (if None, uses current values)
            time_budget_seconds: Maximum time allowed for optimization
            
        Returns:
            dict: Combined results with optimal lens values
        """
        # Start timing
        start_time = time.perf_counter()
        
        try:
            # Get current lens values if not provided
            if init_IL1 is None:
                init_IL1 = self.lens_parameters.get("il1", IL1_0)
            
            if init_stigm is None:
                init_stigm = self.lens_parameters.get("ils", ILS_0)
            
            # Reset results and best tracking
            self.results = []
            self.best_result = None
            self._best_focus = None
            self._best_stigmation = None
            
            # Step 1: First pass focus optimization
            focus_result = self.rapid_parabolic_focus(
                init_IL1=init_IL1,
                range_width=100,  # Adjust based on expected focus range
                num_points=7,     # 7 points is a good balance between speed and accuracy ?
                wait_time_s=WAIT_TIME_S   # Reduced wait time for speed
            )
            
            if focus_result:
                self._best_focus = focus_result
                optimal_il1 = focus_result.get("il1_value")
                logging.critical(f"First pass focus: IL1={optimal_il1}")
            else:
                logging.warning("Focus optimization failed")
                return None
            
            # Check if we have time for stigmation optimization
            elapsed_time = time.perf_counter() - start_time
            remaining_time = time_budget_seconds - elapsed_time
            
            if remaining_time < 2:  # Need at least 2 seconds for stigmation
                logging.info(f"Time budget nearly exceeded ({elapsed_time:.2f}s). Skipping stigmation.")
                return {
                    "focus": self._best_focus,
                    "elapsed_time": elapsed_time,
                    "completed_steps": ["focus"]
                }
            
            # Step 2: Stigmation optimization with remaining time budget
            self.best_result = None  # Reset for stigmation phase
            stigmation_result = self.rapid_stigmation_optimization(
                init_stigm=init_stigm,
                deviation=100,    # Adjust based on expected stigmation range
                num_points=5,     # number of points in each dimension
                wait_time_s=WAIT_TIME_S   # Reduced wait time for speed
            )
            
            if stigmation_result:
                self._best_stigmation = stigmation_result
                optimal_ils = stigmation_result.get("ils_value")
                logging.critical(f"Stigmation optimization: ILs={optimal_ils}")
            
            # Check if we have time for a final focus refinement
            elapsed_time = time.perf_counter() - start_time
            remaining_time = time_budget_seconds - elapsed_time
            
            # Step 3: Optional final focus refinement if time permits
            if remaining_time >= 2 and optimal_il1 is not None:
                logging.info(f"Time remaining: {remaining_time:.2f}s. Performing final focus refinement.")
                
                self.best_result = None  # Reset for final focus refinement
                final_focus_result = self.rapid_parabolic_focus(
                    init_IL1=optimal_il1,
                    range_width=60,   # Narrower range for refinement
                    num_points=4,     # Fewer points needed for refinement
                    wait_time_s=WAIT_TIME_S
                )
                
                if final_focus_result:
                    self._best_focus = final_focus_result
                    final_il1 = final_focus_result.get("il1_value")
                    logging.critical(f"Final focus refinement: IL1={final_il1}")
            
            # Calculate total elapsed time
            total_elapsed_time = time.perf_counter() - start_time
            logging.warning(f"Rapid autofocus completed in {total_elapsed_time:.2f} seconds")
            
            # Combine and return results
            return {
                "focus": self._best_focus,
                "stigmation": self._best_stigmation,
                "elapsed_time": total_elapsed_time,
                "completed_steps": ["focus", "stigmation", "refinement"] if remaining_time >= 2 else ["focus", "stigmation"]
            }
            
        except Exception as e:
            logging.error(f"Error during rapid autofocus: {e}")
            return None

    ##########
    # METHOD B
    ##########
    def slow_focus(self, init_IL1=IL1_0, init_stigm=ILS_0):      
            # Start counter
            autofocus_start = time.perf_counter()

            """ ----------------------
            # Start IL1 ROUGH Sweeping 
            ---------------------- """
            logging.info("################ Start IL1 rough-sweeping ################")

            completed = self.sweep_il1_linear(init_IL1 - 100, init_IL1 + 100, 25)
            if not completed:
                logging.warning("ROUGH Sweep interrupted! Exiting AutoFocusTask::run() method...")
                return  # Exit the run method if the sweep was interrupted

            # Determine the rough optimal IL1 value
            il1_guess1 = self.best_result["il1_value"]
            logging.warning(f"{datetime.now()}, ROUGH IL1 VALUE IS {il1_guess1}")

            # Store this as our best focus result
            self._best_focus = self.best_result
            
            # Once task finished, move lens to optimal position
            self.goto_il1_with_hysteresis_compensation(target_il1=il1_guess1, margin=20)

            """ ----------------------
            # Start ILs ROUGH Sweeping 
            ---------------------- """
            self.best_result = None  # Reset for rough stigmatism sweep
            logging.info("################ Start ILs rough-sweeping ################")

            completed = self.sweep_stig_linear(init_stigm=init_stigm, deviation=500, step=50)
            if not completed:
                logging.warning("STIG Sweep interrupted! Exiting AutoFocusTask::run() method...")
                return  # Exit the run method if the sweep was interrupted

            # Determine the rough optimal ILs value
            ils_guess1 = self.best_result["ils_value"]
            logging.warning(f"{datetime.now()}, ROUGH ILs VALUE IS {ils_guess1}")

            # Store this as our best stigmation result
            self._best_stigmation = self.best_result

            # Once task finished, move lens to optimal position
            self.goto_ils_with_hysteresis_compensation(target_ils=ils_guess1, margin = 50)

            """ ----------------------
            # Start ILs FINE Sweeping 
            ---------------------- """
            # self.best_result = None  # Reset for fine stig sweep
            # logging.info("################ Start ILs fine-sweeping ################")

            # completed = self.sweep_stig_linear(init_stigm=ils_guess1, deviation=250, step=50)
            # if not completed:
            #     logging.warning("STIG Sweep interrupted! Exiting AutoFocusTask::run() method...")
            #     return  # Exit the run method if the sweep was interrupted

            # # Determine the rough optimal ILs value
            # ils_guess2 = self.best_result["ils_value"]
            # logging.warning(f"{datetime.now()}, ROUGH ILs VALUE IS {ils_guess2}")

            # # Update best stigmation
            # self._best_stigmation = self.best_result

            # # Once task finished, move lens to optimal position
            # self.goto_ils_with_hysteresis_compensation(target_ils=ils_guess2, margin = 50)

            """ ----------------------
            # Start IL1 FINE Sweeping 
            ---------------------- """
            self.best_result = None  # Reset for fine IL1 sweep
            logging.info("################ Start IL1 fine-sweeping ################")

            completed = self.sweep_il1_linear(il1_guess1 - 25, il1_guess1 + 30, 5)
            if not completed:
                logging.warning("ROUGH Sweep interrupted! Exiting AutoFocusTask::run() method...")
                return  # Exit the run method if the sweep was interrupted

            # Determine the rough optimal IL1 value
            il1_guess2 = self.best_result["il1_value"]
            logging.warning(f"{datetime.now()}, ROUGH IL1 VALUE IS {il1_guess2}")

            # Update best focus
            self._best_focus = self.best_result
            
            # Once task finished, move lens to optimal position
            self.goto_il1_with_hysteresis_compensation(target_il1=il1_guess2, margin=20)

            # Calculate final results
            best_focus = self._best_focus or {}
            best_stigmation = self._best_stigmation or {}
            
            final_results = {
                "focus": {
                    "il1": best_focus.get("il1_value"),
                    "area": best_focus.get("area"),
                    "sigma_x": best_focus.get("sigma_x"),
                    "sigma_y": best_focus.get("sigma_y"),
                },
                "stigmation": {
                    "ils": best_stigmation.get("ils_value"),
                    "ellipticity": best_stigmation.get("ellipticity"),
                    "circularity_error": best_stigmation.get("circularity_error"),
                },
                "total_evaluations": len(self.results),
            }
            
            autofocus_end = time.perf_counter()
            autofocus_time = autofocus_end - autofocus_start
            
            logging.warning(f" ###### AUTOFOCUSED COMPLETED in {autofocus_time:.6f} seconds")
            logging.info(f"Final results: {final_results}")
            
            # Emit final result signal (for UI update)
            self.newBestResult.emit(final_results)

    def sweep_il1_linear(self, lower, upper, step, wait_time_s=WAIT_TIME_S):
        """
        Perform a linear sweep of IL1 TEM lens positions with Gaussian fitting at each step.
        
        Adjusts IL1 focus through specified range, requesting Gaussian fitting at each position.
        Sweep continues while 'sweepingWorkerReady' is True.
        
        Parameters:
            lower (int): Starting IL1 lens position
            upper (int): Ending IL1 lens position
            step (int): Increment between positions
            wait_time_s (float, optional): Wait time after setting focus before fitting
            
        Returns:
            bool: True if sweep completes, False if interrupted
        """
        self._current_mode = "IL1_FOCUS"
        for il1_value in range(lower, upper, step):
            # Check if process is alive
            if not self.check_process_alive():
                return False

            # Set IL1 to current position
            iter_start = time.perf_counter()
            logging.info(datetime.now().strftime(" BEGIN IL1 SWEEP @ %H:%M:%S.%f")[:-3])
            self.client.SetILFocus(il1_value)
            logging.info(datetime.now().strftime(" END IL1 SWEEP @ %H:%M:%S.%f")[:-3])
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

            fit_success = self.request_fit_and_process_result()
            if not fit_success:
                logging.warning(f"Failed to get a valid fit for IL1={il1_value}")

        return True
    
    def sweep_stig_linear(self, init_stigm, deviation, step, wait_time_s=WAIT_TIME_S):
        """
        Perform a linear sweep of stigmation parameters in X and Y directions.
        
        Scans range [ils_x0±deviation, ils_y0±deviation] with increment 'step'.
        At each setting, sets ILs lens, waits, then requests Gaussian fit.
        Aborts if 'sweepingWorkerReady' becomes False.
        
        Parameters
            init_stigm (list[2]): Initial stigmation values [ils_x0, ils_y0]
            deviation (int): Range around initial values to explore
            step (int): Increment between stigmation values
            wait_time_s (float, optional): Wait time after setting stigmation
            
        Returns:
            bool: True if completed, False if interrupted
        """
        self._current_mode = "ILS_STIGMATION"
        # Store the current Y stigmatism lens position (unchanged during X-sweep)
        current_ils_y = self.lens_parameters["ils"][1]

        logging.info("################ Start X-ILs sweep ################")

        for ils_x in range(init_stigm[0] - deviation, init_stigm[0] + deviation + step, step):
            # Check if process is alive
            if not self.check_process_alive():
                return False
            
            # Set ILs lens to the current position
            iter_start = time.perf_counter()
            logging.info(datetime.now().strftime(" BEGIN STIG-x SWEEP @ %H:%M:%S.%f")[:-3])
            self.client.SetILs(ils_x, current_ils_y)
            logging.info(datetime.now().strftime(" END STIG-X SWEEP @ %H:%M:%S.%f")[:-3])
            iter_end = time.perf_counter()
            iter_time = iter_end - iter_start
            logging.critical(f"SetILs({ils_x}, {current_ils_y}) took {iter_time:.6f} seconds")

            # Wait for the system to stabilize after setting ILs
            time.sleep(wait_time_s)

            # Update dictionnary
            self.lens_parameters["ils"] = [ils_x, current_ils_y]

            # Request fit and process results - skip to next iteration if it fails
            fit_success = self.request_fit_and_process_result()
            if not fit_success:
                logging.warning(f"Failed to get a valid fit for ILs=[{ils_x}, {current_ils_y}]")
        
        # Store the current X stigmatism lens position (unchanged during Y-sweep)
        current_ils_x = self.lens_parameters["ils"][0]

        logging.info("################ Start Y-ILs sweep ################")

        for ils_y in range(init_stigm[1] - deviation, init_stigm[1] + deviation + step, step):
            # Check if process is alive
            if not self.check_process_alive():
                return False
                
            # Set ILs lens to the current position
            iter_start = time.perf_counter()
            logging.info(datetime.now().strftime(" BEGIN STIG-Y SWEEP @ %H:%M:%S.%f")[:-3])
            self.client.SetILs(current_ils_x, ils_y)
            logging.info(datetime.now().strftime(" END STIG-Y SWEEP @ %H:%M:%S.%f")[:-3])
            iter_end = time.perf_counter()
            iter_time = iter_end - iter_start
            logging.critical(f"SetILs({current_ils_x}, {ils_y}) took {iter_time:.6f} seconds")

            # Wait for the system to stabilize after setting ILs
            time.sleep(wait_time_s)

            # Update dictionnary
            self.lens_parameters["ils"] = [current_ils_x, ils_y]

            # Request fit and process results - skip to next iteration if it fails
            fit_success = self.request_fit_and_process_result()
            if not fit_success:
                logging.warning(f"Failed to get a valid fit for ILs=[{current_ils_x}, {ils_y}]")

        return True

    ################
    # Common methods
    ################
    def check_process_alive(self):
        """Check if the beam fitting process is still alive and ready."""
        if not self.beam_fitter.fitting_process.is_alive():
            logging.error("GaussianFitterMP process has terminated unexpectedly. Aborting optimization.")
            return False
            
        if not self.control.sweepingWorkerReady:
            logging.warning("Interrupting optimization due to sweepingWorkerReady=False")
            return False
            
        return True

    def goto_il1_with_hysteresis_compensation(self, target_il1, margin=20):
        """
        Approach target IL1 value with hysteresis compensation.
        
        Args:
            target_il1: Target IL1 value
            margin: Overshoot margin for hysteresis compensation
        """
        logging.info(f"Moving to IL1={target_il1} with hysteresis compensation")
        
        # Go to a value well below the target
        self.client.SetILFocus(target_il1 - 50)
        time.sleep(WAIT_TIME_S)
        
        # Overshoot by a fixed amount
        self.client.SetILFocus(target_il1 + margin)
        time.sleep(WAIT_TIME_S)
        
        # Approach the final value
        self.client.SetILFocus(target_il1)
        time.sleep(WAIT_TIME_S)
        
        # Update stored value
        self.lens_parameters["il1"] = target_il1
    
    def goto_ils_with_hysteresis_compensation(self, target_ils, margin=50):
        """
        Approach target ILs values with hysteresis compensation.
        
        Args:
            target_ils: Target ILs values [x, y]
            margin: Overshoot margin for hysteresis compensation
        """
        ils_x, ils_y = target_ils
        logging.info(f"Moving to ILs=[{ils_x}, {ils_y}] with hysteresis compensation")
        
        # X axis approach
        current_ils_y = self.lens_parameters.get("ils", [0, 0])[1]
        self.client.SetILs(ils_x - 100, current_ils_y)
        time.sleep(WAIT_TIME_S)
        self.client.SetILs(ils_x + margin, current_ils_y)
        time.sleep(WAIT_TIME_S)
        self.client.SetILs(ils_x, current_ils_y)
        time.sleep(WAIT_TIME_S)
        
        # Y axis approach
        self.client.SetILs(ils_x, ils_y - 100)
        time.sleep(WAIT_TIME_S)
        self.client.SetILs(ils_x, ils_y + margin)
        time.sleep(WAIT_TIME_S)
        self.client.SetILs(ils_x, ils_y)
        time.sleep(WAIT_TIME_S)
        
        # Update stored value
        self.lens_parameters["ils"] = [ils_x, ils_y]

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
        # self.process_fit_results(fit_result)
        self.process_fit_results_refined(fit_result)
        
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

    def process_fit_results_refined(self, fit_values):
        """
        Process fit results with separate optimization goals for IL1 and ILs.
        
        Args:
            fit_values: Dictionary with fit parameters
        """
        # Extract measurements
        sigma_x = float(fit_values.get("sigma_x", 0))
        sigma_y = float(fit_values.get("sigma_y", 0))
        
        # Skip invalid measurements
        if sigma_x <= 0 or sigma_y <= 0:
            logging.warning(f"Invalid fit values: sigma_x={sigma_x}, sigma_y={sigma_y}")
            return
        
        # Calculate metrics
        area = sigma_x * sigma_y
        ellipticity = max(sigma_x, sigma_y) / min(sigma_x, sigma_y)
        circularity_error = abs(ellipticity - 1.0)
        
        # Add a combined metric (for comparison across modes)
        # This prioritizes small area with good roundness
        combined_metric = area * (1 + circularity_error)
        
        # Store the result
        result_dict = {
            "il1_value": self.lens_parameters["il1"],
            "ils_value": self.lens_parameters["ils"],
            "sigma_x": sigma_x,
            "sigma_y": sigma_y,
            "area": area,
            "ellipticity": ellipticity,
            "circularity_error": circularity_error,
            "combined_metric": combined_metric,
            "timestamp": datetime.now().strftime("%H:%M:%S.%f"),
        }
        self.results.append(result_dict)
        
        # Update the best result based on current lens operation mode
        if self._current_mode == "IL1_FOCUS":
            # For focus mode, prioritize small area (sharp focus)
            if self.best_result is None or area < self.best_result.get("area", float('inf')):
                self.best_result = result_dict
                # Notify the main GUI thread of the new best result
                self.newBestResult.emit(result_dict)
                logging.info(f"New best focus: IL1={result_dict['il1_value']}, area={area:.2f}")
        
        elif self._current_mode == "ILS_STIGMATION":
            # For stigmation mode, prioritize circularity (ellipticity near 1.0)
            if self.best_result is None or circularity_error < self.best_result.get("circularity_error", float('inf')):
                self.best_result = result_dict
                # Notify the main GUI thread of the new best result
                self.newBestResult.emit(result_dict)
                logging.info(f"New best stigmation: ILs={result_dict['ils_value']}, ellipticity={ellipticity:.2f}")
        
        logging.info(f"Processed fit: area={area:.2f}, ellipticity={ellipticity:.2f}")

    def cleanup(self):
        """
        Clean up the fitter and references.
        """
        if self.beam_fitter is not None:
            self.beam_fitter.stop()   # This calls input_queue.put(None), .join(), etc.