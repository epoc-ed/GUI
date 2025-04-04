import logging
import time
import os
from datetime import datetime as dt
import numpy as np
import threading

from PySide6.QtCore import Signal, Slot, QObject, QThread, QMetaObject, Qt, QTimer

from .task import Task
from .record_task import RecordTask

from .beam_focus_task import AutoFocusTask

from .adjustZ_task import AdjustZ
from .get_teminfo_task import GetInfoTask
from .stage_centering_task import CenteringTask

from simple_tem import TEMClient
from ..toolbox import tool as tools

from epoc import ConfigurationClient, auth_token, redis_host

import jungfrau_gui.ui_threading_helpers as thread_manager

from .... import globals

from ..gaussian_fitter_mp import GaussianFitterMP

def on_new_best_result_in_main_thread(result_dict):
    # This runs in the main thread. We can safely update GUI elements, logs, etc.
    print("New best result =>", result_dict)

class ControlWorker(QObject):
    """
    The 'ControlWorker' object coordinates the execution of tasks and redirects requests to the GUI.
    """
    connected = Signal()
    finished = Signal()
    updated = Signal()
    received = Signal(str)
    send = Signal(str)
    init = Signal()
    finished_record_task = Signal()
    
    trigger_tem_update_detailed = Signal(dict)
    trigger_tem_update = Signal(dict)
    trigger_tem_update_init = Signal(dict)

    draw_ellipses_on_ui = Signal(dict)
    
    trigger_stop_autofocus = Signal()
    remove_ellipse = Signal()

    trigger_record = Signal()
    trigger_shutdown = Signal()
    trigger_getteminfo = Signal(str)
    trigger_centering = Signal(bool, str)
    trigger_movewithbacklash = Signal(int, float, float)

    actionFit_Beam = Signal() # originally defined with QuGui
    # actionAdjustZ = Signal()

    def __init__(self, tem_action): #, timeout:int=10, buffer=1024):
        super().__init__()
        self.cfg = ConfigurationClient(redis_host(), token=auth_token())
        self.client = TEMClient(globals.tem_host, 3535,  verbose=False)

        self.task = Task(self, "Dummy")
        self.task_thread = QThread()
        self.tem_action = tem_action
        self.file_operations = self.tem_action.file_operations
        self.visualization_panel = self.tem_action.visualization_panel
        self.last_task: Task = None
        self.info_queries = tools.INFO_QUERIES
        self.more_queries = tools.MORE_QUERIES
        self.init_queries = tools.INIT_QUERIES
        
        self.setObjectName("control Thread")
        
        self.init.connect(self._init)
        self.send.connect(self.send_to_tem)
        self.trigger_record.connect(self.start_record)
        self.trigger_shutdown.connect(self.shutdown)
        self.trigger_getteminfo.connect(self.getteminfo)
        self.trigger_centering.connect(self.centering)
        self.trigger_movewithbacklash.connect(self.move_with_backlash)
        # self.actionAdjustZ.connect(self.start_adjustZ)

        self.beam_fitter = None
        self.actionFit_Beam.connect(self.start_beam_fit)
        
        self.trigger_tem_update_detailed.connect(self.update_tem_status_detailed)
        self.trigger_tem_update.connect(self.update_tem_status)
        self.trigger_tem_update_init.connect(self.update_tem_status_init)
        
        self.tem_status = {"stage.GetPos": [0.0, 0.0, 0.0, 0.0, 0.0], "stage.Getf1OverRateTxNum": self.cfg.rotation_speed_idx,
                           "stage.GetPos_diff": [0.0, 0.0, 0.0, 0.0, 0.0], 
                           "eos.GetFunctionMode": [-1, -1], "eos.GetMagValue": globals.mag_value_img,
                           "eos.GetMagValue_MAG": globals.mag_value_img, "eos.GetMagValue_DIFF": globals.mag_value_diff, "defl.GetBeamBlank": 0,
                           "apt.GetKind": 0, "apt.GetPosition_CL": [0, 0], "apt.GetPosition_OL": [0, 0], "apt.GetPosition_SA": [0, 0],
                           "ht.GetHtValue": 200000.00, "ht.GetHtValue_readout": 0}
        
        self.tem_update_times = {}
        self.triggerdelay_ms = 500
        self.previous_tx_abs = 0
        self.beam_intensity = {"pa_per_cm2": 0, "e_per_A2_sample": 0}
        self.beam_property_fitting = [-1, -1, 0] # sigmax, sigmay, angle

    @Slot()
    def _init(self):
        threading.current_thread().setName("ControlThread")
        self.interruptRotation = False                         
        self.sweepingWorkerReady = False
        logging.info("Initialized control thread")

    @Slot()
    def on_task_finished(self):
        logging.info(f"\033[1mFinished Task [{self.task.task_name}] !")
        
        if isinstance(self.task, AutoFocusTask):
            self.beam_fitter = None   # So we don't accidentally reuse it.
            logging.info(f"Instance of \033[1mGaussianFitterMP\033[0m\033[34m has been reset to None.")
            # Uncomment below if fitting results are being drawn (drawings are a bit delayed for now...)
            # logging.info("********** Emitting 'remove_ellipse' signal from -MAIN- Thread **********")
            # self.remove_ellipse.emit()

        self.handle_task_cleanup()
        thread_manager.disconnect_worker_signals(self.task)
        thread_manager.terminate_thread(self.task_thread)
        thread_manager.remove_worker_thread_pair(self.tem_action.parent.threadWorkerPairs, self.task_thread)
        self.task, self.task_thread = thread_manager.reset_worker_and_thread(self.task, self.task_thread)
        logging.info(f"Is Task actually reset to None ? -> {self.task is None}")

        # Ask for a full update after the end and clean up of the task
        self.send_to_tem("#more", asynchronous=True)

    def handle_task_cleanup(self):
        if self.task is not None: # TODO This does not seem to be enough 
            # to prevent entering again after call from ui_main_window [handle_tem_task_cleanup]
            if isinstance(self.task, RecordTask):
                logging.info("The \033[1mRecordTask\033[0m\033[34m has ended, performing cleanup...")
            elif isinstance(self.task, GetInfoTask):
                logging.info("The \033[1mGetInfo\033[0m\033[34m has ended, performing cleanup...")
            elif isinstance(self.task, AutoFocusTask):
                logging.info("The \033[1mAutoFocusTask\033[0m\033[34m has ended, performing cleanup...")
            
            self.stop_task()
            
    def reset_autofocus_button(self):
        self.tem_action.tem_tasks.beamAutofocus.setText("Start Beam Autofocus")
        self.tem_action.tem_tasks.beamAutofocus.started = False
        # Close Pop-up Window
        if self.tem_action.tem_tasks.parent.plotDialog != None:
            self.tem_action.tem_tasks.parent.plotDialog.close_window()

    def start_task(self, task):
        logging.debug("Control is starting a Task...")
        self.last_task = self.task
        self.task = task
        # Create a new QThread for each task to avoid reuse issues
        self.task_thread = QThread()  
        self.tem_action.parent.threadWorkerPairs.append((self.task_thread, self.task))
        self.task.finished.connect(self.on_task_finished)
        self.task.moveToThread(self.task_thread)
        self.task_thread.started.connect(self.task.start.emit)
        self.task_thread.start()

    @Slot(str)
    def getteminfo(self, gui=''):
        logging.info("Start GetInfo")
        if self.task is not None:
            if self.task.running:
                logging.warning("\033[38;5;214mGetInfoTask\033[33m - task is currently running...\n"
                                "You need to stop the current task before starting a new one.")
                # self.stop_task()
                return

        command='TEMstatus'

        if gui=='':
            x = input(f'Write TEM status on a file? If YES, give a filename or "Y" ({command}_[timecode].log). [N]\n')
            task = GetInfoTask(self, x)
        else:
            task = GetInfoTask(self, gui)

        self.start_task(task)

    @Slot(bool, str)
    def centering(self, gui=False, vector='10, 1'):
        logging.info("Start Centering")            
        if self.task is not None:
            if self.task.running:
                logging.warning("\033[38;5;214mCenteringTask\033[33m - task is currently running...\n"
                                "You need to stop the current task before starting a new one.")
                return
        pixels = np.array(vector.split(sep=','), dtype=float)
        task = CenteringTask(self, pixels)
        self.start_task(task)

    @Slot()
    def start_record(self):
        logging.info("Starting Rotation/Record")

        # Check if a task is already running, and stop it if so
        if self.task is not None:
            if self.task.running:
                logging.warning("\033[38;5;214mRecordTask\033[33m - task is currently running...\n"
                                "You need to stop the current task before starting a new one.")
                # self.stop_task()  # Ensure that the current task is fully stopped
                return

        end_angle = self.tem_action.tem_tasks.update_end_angle.value() # 60
        logging.info(f"End angle = {end_angle}")

        # Stop the Gaussian Fitting if running
        if self.tem_action.tem_tasks.btnGaussianFit.started:
            self.tem_action.tem_controls.toggle_gaussianFit_beam(by_user=True) # Simulate a user-forced off operation 
            time.sleep(0.1)
            self.tem_action.tem_tasks.btnGaussianFit.clicked.disconnect()
            
        self.beam_property_fitting = [self.tem_action.tem_controls.sigma_x_spBx.value(),
                                      self.tem_action.tem_controls.sigma_y_spBx.value(),
                                      self.tem_action.tem_controls.angle_spBx.value()]
            
        if self.tem_action.tem_tasks.withwriter_checkbox.isChecked():
            self.file_operations.update_base_data_directory() # Update the GUI
            filename_suffix = self.cfg.data_dir / 'RotEDlog_test'
            task = RecordTask(
                self,
                end_angle,
                filename_suffix.as_posix(),
                writer_event = [self.visualization_panel.startCollection.clicked.emit, self.visualization_panel.stop_jfj_measurement.clicked.emit])
        else:
            task = RecordTask(self, end_angle) #, filename_suffix.as_posix())

        self.start_task(task)

    @Slot()
    def start_beam_fit(self):
        logging.info("Start AutoFocus")

        if self.task is not None:
            if self.task.running:
                logging.warning("\033[38;5;214mAutoFocus\033[33m - task is currently running...\n"
                                "You need to stop the current task before starting a new one.")
                # self.stop_task()
                return           

        if self.tem_status['eos.GetFunctionMode'][1] != 4:
            logging.warning('Switches ' + str(self.tem_status['eos.GetFunctionMode'][1]) + ' to DIFF mode')
            
            # Switching to Diffraction Mode
            self.client.SelectFunctionMode(4)

        # Stop the Gaussian Fitting if running
        if self.tem_action.tem_tasks.btnGaussianFit.started:
            self.tem_action.tem_controls.toggle_gaussianFit_beam(by_user=True) # Simulate a user-forced off operation 
            time.sleep(0.1)
            # self.tem_action.tem_tasks.btnGaussianFit.clicked.disconnect()

        self.beam_fitter = GaussianFitterMP()

        task = AutoFocusTask(self)
        
        # Optional
        task.newBestResult.connect(on_new_best_result_in_main_thread)
        
        self.sweepingWorkerReady = True

        self.start_task(task)

    def set_sweeper_to_off_state(self):
        logging.info("####### ######## Sweeping worker ready? --> FALSE")
        self.sweepingWorkerReady = False

    @Slot(dict)
    def update_tem_status_detailed(self, response):
        """Update control worker with detailed TEM status."""
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            logging.debug("Updating ControlWorker map with last TEM Status")
        
        try:
            if logging.getLogger().isEnabledFor(logging.DEBUG):
                logging.debug("START of the update loop")
            
            # Pre-fetch references to avoid dictionary lookups in loop
            tem_status = self.tem_status
            tem_update_times = self.tem_update_times
            
            # Update status in single loop
            for entry, data in response.items():
                tem_status[entry] = data["val"]
                tem_update_times[entry] = (data["tst_before"], data["tst_after"])
            
            if logging.getLogger().isEnabledFor(logging.DEBUG):
                logging.debug("END of update loop")
                logging.debug(f"self.tem_status['eos.GetFunctionMode'] = {tem_status['eos.GetFunctionMode']}")
            
            # Get function mode once
            function_mode = tem_status.get('eos.GetFunctionMode', [None, None])[0]
            mag_value = tem_status.get('eos.GetMagValue')
            
            # Handle magnification mode
            if function_mode == 0:  # MAG
                tem_status['eos.GetMagValue_MAG'] = mag_value
                globals.mag_value_img = mag_value
                tem_update_times['eos.GetMagValue_MAG'] = tem_update_times['eos.GetMagValue']
            elif function_mode == 4:  # DIFF
                tem_status['eos.GetMagValue_DIFF'] = mag_value
                globals.mag_value_diff = mag_value
                tem_update_times['eos.GetMagValue_DIFF'] = tem_update_times['eos.GetMagValue']
            
            # Handle aperture kind
            apt_kind = tem_status.get('apt.GetKind')
            if apt_kind is not None:
                apt_position = tem_status.get('apt.GetPosition')
                if apt_kind == 1:  # CLA
                    tem_status['apt.GetPosition_CL'] = apt_position
                elif apt_kind == 2:  # OLA
                    tem_status['apt.GetPosition_OL'] = apt_position
                elif apt_kind == 4:  # SAA
                    tem_status['apt.GetPosition_SA'] = apt_position

            # Update blanking button with live status at TEM - do this once
            self._update_blanking_button(tem_status.get("defl.GetBeamBlank", 0))

            if logging.getLogger().isEnabledFor(logging.DEBUG):
                logging.debug("TEM Status Dictionary updated!")
            
            # Signal update
            self.updated.emit()
        except Exception as e:
            logging.error(f"Error during updating detailed tem_status map: {e}")

    @Slot(dict)
    def update_tem_status_init(self, response):
        """Update control worker with initial TEM status."""
        try:
            # Pre-fetch references
            tem_status = self.tem_status
            tem_update_times = self.tem_update_times
            
            # Update in single loop
            for entry, data in response.items():
                tem_status[entry] = data["val"]
                tem_update_times[entry] = (data["tst_before"], data["tst_after"])
            
            # Set default HT value if needed
            ht_value = tem_status.get('ht.GetHtValue')
            if ht_value is not None:
                tem_status['ht.GetHtValue_readout'] = 1
            else:
                tem_status['ht.GetHtValue'] = 200000.00
            
            # Signal update
            self.updated.emit()
        except Exception as e:
            logging.error(f"Error during starting tem_status map: {e}")

    @Slot(dict)
    def update_tem_status(self, response):
        """Update control worker with basic TEM status."""
        try:
            # Pre-fetch references
            tem_status = self.tem_status
            
            # Save previous position
            tem_status["stage.GetPos_prev"] = tem_status.get("stage.GetPos", [0, 0, 0, 0, 0])
            
            # Update status in single loop
            for entry, value in response.items():
                tem_status[entry] = value
            
            logging.debug(f"self.tem_status['eos.GetFunctionMode'] = {tem_status.get('eos.GetFunctionMode')}")
            
            # Get function mode once
            function_mode_list = tem_status.get('eos.GetFunctionMode') or [None, None]
            function_mode = function_mode_list[0]
            mag_value = tem_status.get('eos.GetMagValue', None)
            
            # Handle magnification mode
            if function_mode is not None:
                if function_mode == 0:  # MAG
                    tem_status['eos.GetMagValue_MAG'] = mag_value
                    globals.mag_value_img = mag_value
                elif function_mode == 4:  # DIFF
                    tem_status['eos.GetMagValue_DIFF'] = mag_value
                    globals.mag_value_diff = mag_value

            # Update blanking button with live status at TEM
            self._update_blanking_button(tem_status.get("defl.GetBeamBlank", 0))

            # Calculate position difference using numpy operations
            pos_list = tem_status.get("stage.GetPos", [0, 0, 0, 0, 0])
            pos_prev_list = tem_status.get("stage.GetPos_prev", [0, 0, 0, 0, 0])
            
            # Calculate difference and apply threshold in one step
            if pos_list is not None and pos_prev_list is not None:
                position = np.array(pos_list)
                position_prev = np.array(pos_prev_list)
                diff_pos = position - position_prev
                threshold = np.array([30, 30, 30, 0.2, 100])  # nm, nm, nm, deg., deg.
                update_mask = np.abs(diff_pos) > threshold
            
                # Update diff using vectorized operations
                prev_diff = tem_status.get("stage.GetPos_diff", np.zeros(5))
                tem_status["stage.GetPos_diff"] = np.where(update_mask, diff_pos, prev_diff)
            
            # Signal update
            self.updated.emit()
        except Exception as e:
            logging.error(f"Error during quick updating tem_status map: {e}")

    def _update_blanking_button(self, beam_blank_state):
        """Helper method to update blanking button state."""
        # Cache reference to button
        button = self.tem_action.tem_stagectrl.blanking_button
        
        if beam_blank_state is not None:
            if beam_blank_state == 0:
                button.setText("Blank beam")
                button.setStyleSheet('background-color: rgb(53, 53, 53); color: white;')
            else:
                button.setText("Unblank beam")
                button.setStyleSheet('background-color: orange; color: white;')
        else:
            button.setText("Unknown Blanking State...")
            button.setStyleSheet('background-color: red; color: white;')

    @Slot(str) 
    def send_to_tem(self, message, asynchronous=True):
        """Send commands to TEM with optimized thread handling."""
        logging.debug(f'Sending {message} to TEM...')
        
        # Create a mapping of commands to their handler functions
        command_map = {
            "#info": self._handle_info_command,
            "#more": self._handle_more_command,
            "#init": self._handle_init_command
        }
        
        # Execute the appropriate handler if command is valid
        handler = command_map.get(message)
        if handler:
            if asynchronous:
                # Use daemon threads to prevent hanging
                thread = threading.Thread(target=handler, args=(asynchronous,))
                thread.daemon = True
                thread.start()
            else:
                handler(asynchronous)
        else:
            logging.error(f"{message} is not valid for ControlWorker::send_to_tem()")

    def _handle_info_command(self, asynchronous):
        """Handle '#info' command in a worker thread."""
        # If we have a worker, use it
        if hasattr(self.tem_action, 'tem_threads') and self.tem_action.tem_threads.get('update_worker'):
            # Invoke the worker method
            QMetaObject.invokeMethod(self.tem_action.tem_threads['update_worker'], 
                                    "process_tem_info", 
                                    Qt.QueuedConnection)
        else:
            # Fallback to old method
            results = self.get_state_batched()
            self.trigger_tem_update.emit(results)

    def _handle_more_command(self, asynchronous):
        """Handle '#more' command."""
        # Get detailed state with batched processing
        results = self.get_state_detailed_batched()
        # Emit signal with results
        self.trigger_tem_update_detailed.emit(results)

    def _handle_init_command(self, asynchronous):
        """Handle '#init' command."""
        # Get init state with batched processing
        results = self.get_state_init_batched()
        # Emit signal with results
        self.trigger_tem_update_init.emit(results)

    def get_state_batched(self, batch_size=3):
        """Get TEM state in batches to prevent freezes."""
        results = {}
        tic_loop = time.perf_counter()
        mapping = tools.full_mapping
        
        # Process queries in batches to allow UI updates between batches
        query_batches = [self.info_queries[i:i+batch_size] for i in range(0, len(self.info_queries), batch_size)]
        
        for batch in query_batches:
            batch_results = {}
            
            # Process each query in the batch
            for query in batch:
                logging.debug(f"Processing command: {query}")
                
                # Execute command with mapped value and timeout
                batch_results[query] = self.execute_command(mapping[query])
            
            # Update results with batch results
            results.update(batch_results)
            
            # Short yield to allow UI updates
            if len(query_batches) > 1:
                time.sleep(0.001)  # Minimal sleep to allow event loop to process

        toc_loop = time.perf_counter()
        logging.debug(f"Getting #info took {toc_loop - tic_loop} seconds")
        
        return results

    def get_state_detailed_batched(self, batch_size=3):
        """Get detailed TEM state in batches."""
        results = {}
        tic_loop = time.perf_counter()
        mapping = tools.full_mapping
        del_items = []
        
        # Process queries in batches
        query_batches = [self.more_queries[i:i+batch_size] for i in range(0, len(self.more_queries), batch_size)]
        
        for batch in query_batches:
            batch_results = {}
            
            # Process each query in the batch
            for query in batch:
                # Create result structure
                result = {
                    "tst_before": time.time(),
                    "val": self.execute_command(mapping[query]),
                    "tst_after": time.time()
                }
                
                # Store result
                batch_results[query] = result
                
                # Check for None values
                if result["val"] is None and query in ["apt.GetKind", "apt.GetPosition"]:
                    del_items.append(query)
            
            # Update results with batch results
            results.update(batch_results)
            
            # Short yield to allow UI updates
            if len(query_batches) > 1:
                time.sleep(0.001)
        
        # Remove failed queries
        for query in del_items:
            if query in self.more_queries:
                self.more_queries.remove(query)
                logging.warning(f"{query} removed from query list")

        toc_loop = time.perf_counter()
        logging.warning(f"Getting #more took {toc_loop - tic_loop} seconds")
        
        return results

    def get_state_init_batched(self, batch_size=3):
        """Get initial TEM state in batches."""
        results = {}
        tic_loop = time.perf_counter()
        mapping = tools.full_mapping
        del_items = []
        
        # Process queries in batches
        query_batches = [self.init_queries[i:i+batch_size] for i in range(0, len(self.init_queries), batch_size)]
        
        for batch in query_batches:
            batch_results = {}
            
            # Process each query in the batch
            for query in batch:
                # Create result structure
                result = {
                    "tst_before": time.time(),
                    "val": self.execute_command(mapping[query]),
                    "tst_after": time.time()
                }
                
                # Store result
                batch_results[query] = result
                
                # Check for None values
                if result["val"] is None:
                    del_items.append(query)
            
            # Update results with batch results
            results.update(batch_results)
            
            # Short yield to allow UI updates
            if len(query_batches) > 1:
                time.sleep(0.001)
        
        # Remove failed queries
        for query in del_items:
            if query in self.init_queries:
                self.init_queries.remove(query)
                logging.warning(f"{query} removed from query list")
        
        toc_loop = time.perf_counter()
        logging.warning(f"Getting #init took {toc_loop - tic_loop} seconds")

        return results 

    def execute_command(self, command_str):
        """Execute a TEM command with optimized performance."""
        # Early validation
        if not command_str or not hasattr(self, 'client'):
            logging.error(f"Invalid command format or missing client: {command_str}")
            return None
            
        try:
            # Handle methods with and without parentheses
            if '(' in command_str:
                # Cache frequently used operations
                method_parts = command_str.split('(', 1)
                method_name = method_parts[0]
            
                # Handle the case where there might not be a closing parenthesis
                if ')' in method_parts[1]:
                    arguments = method_parts[1].split(')', 1)[0]
                else:
                    arguments = method_parts[1]
                
                # Prepare arguments (only process if we have arguments)
                if arguments.strip():
                    # Pre-split arguments
                    arg_list = arguments.split(',')
                    args = []
                    
                    # Process each argument once with optimized type conversion
                    for arg in arg_list:
                        arg = arg.strip()
                        if arg.lower() == 'true':
                            args.append(True)
                        elif arg.lower() == 'false':
                            args.append(False)
                        else:
                            # Try numeric conversion with minimal overhead
                            try:
                                if '.' in arg:
                                    args.append(float(arg))
                                else:
                                    args.append(int(arg))
                            except ValueError:
                                args.append(arg)
                    
                    # Convert to tuple once
                    args = tuple(args)
                else:
                    args = ()
            else:
                # Method without arguments
                method_name = command_str
                args = ()

            # Get method reference once (expensive operation)
            try:
                method = getattr(self.client, method_name)
            except AttributeError:
                logging.error(f"Method '{method_name}' does not exist")
                return None
                
            # Set a timeout for TEM communication
            result = self._execute_with_timeout(method, args)
            return result
            
        except Exception as e:
            logging.error(f"Error executing '{command_str}': {str(e)}")
            return None

    def _execute_with_timeout(self, method, args, timeout=0.5):
        """Execute a method with a timeout to prevent UI freezes."""
        # Create a result container
        result_container = []
        exception_container = []
        
        # Define the worker function
        def worker():
            try:
                result_container.append(method(*args))
            except Exception as e:
                exception_container.append(e)
        
        # Create and start the thread
        thread = threading.Thread(target=worker)
        thread.daemon = True  # Allow program to exit even if thread is running
        thread.start()
        
        # Wait for thread with timeout
        thread.join(timeout)
        
        # Check if thread is still alive (timed out)
        if thread.is_alive():
            logging.warning(f"TEM command timed out: {method.__name__}")
            return None
        
        # Check for exceptions
        if exception_container:
            logging.error(f"Error in TEM command: {str(exception_container[0])}")
            return None
        
        # Return the result
        return result_container[0] if result_container else None

    def stop_task(self):
        if self.task:
            if isinstance(self.task, AutoFocusTask):
                logging.info("Stopping the - \033[1mAutoFocus\033[0m\033[34m - task!")
                self.reset_autofocus_button()
            
            elif isinstance(self.task, RecordTask):
                logging.info("Stopping the - \033[1mRecord\033[0m\033[34m - task!")
                try:
                    tools.send_with_retries(self.client.StopStage)
                except Exception as e:
                    logging.error(f"Unexpected error @ client.StopStage(): {e}")
                    pass

            elif isinstance(self.task, GetInfoTask):
                logging.info("Stopping the - \033[1mGetInfo\033[0m\033[34m - task!")

    @Slot()
    def shutdown(self):
        logging.info("Shutting down control")
        try:
            # self.client.exit_server()
            # logging.warning("TEM server is OFF")
            # time.sleep(0.12)
            logging.warning("GUI diconnected from TEM")
            # self.task_thread.quit() # TODO Raises error: Internal C++ object (PySide6.QtCore.QThread) already deleted.
        except Exception as e:
            logging.error(f'Shutdown of Task Manager triggered error: {e}')
            pass

    @Slot(int, float, float)
    def move_with_backlash(self, moverid=0, value=10, backlash=0, scale=1): # +x, -x, +y, -y, +z, -z, +tx, -tx (0-7) 
        # self.send_to_tem("#info")
        QTimer.singleShot(0, lambda: self.send_to_tem("#info", asynchronous=True))
        
        # time.sleep(0.5)
        # backlash correction
        if moverid%2 == 0 and np.sign(self.tem_status["stage.GetPos_diff"][moverid//2]) >= 0: backlash = 0
        elif moverid%2 == 1 and np.sign(self.tem_status["stage.GetPos_diff"][moverid//2]) < 0: backlash = 0
        
        logging.debug(f"xyz0, dxyz0 : {list(map(lambda x, y: f'{x/1e3:8.3f}{y/1e3:8.3f}', self.tem_status['stage.GetPos'][:3], self.tem_status['stage.GetPos_diff'][:3]))}, {self.tem_status['stage.GetPos'][3]:6.2f} {self.tem_status['stage.GetPos_diff'][3]:6.2f}, {backlash}")
        
        client = self.client
        match moverid:
            case 0: threading.Thread(target=client.SetXRel, args=(value*scale-backlash,)).start()
            case 1: threading.Thread(target=client.SetXRel, args=(value*scale+backlash,)).start()
            case 2: threading.Thread(target=client.SetYRel, args=(value*scale-backlash,)).start()
            case 3: threading.Thread(target=client.SetYRel, args=(value*scale+backlash,)).start()
            case 4: threading.Thread(target=client.SetZRel, args=(value*scale+backlash,)).start()
            case 5: threading.Thread(target=client.SetZRel, args=(value*scale-backlash,)).start()
            case 6: threading.Thread(target=client.SetTXRel, args=(value*scale+backlash,)).start()
            case 7: threading.Thread(target=client.SetTXRel, args=(value*scale-backlash,)).start()
            case _:
                logging.warning(f"Undefined moverid {moverid}")
                return

        if moverid < 2:
            logging.info(f"Moved stage {value*scale/1e3:.1f} um in X-direction")
        logging.debug(f"xyz1, dxyz1 : {list(map(lambda x, y: f'{x/1e3:8.3f}{y/1e3:8.3f}', self.tem_status['stage.GetPos'][:3], self.tem_status['stage.GetPos_diff'][:3]))}, {self.tem_status['stage.GetPos'][3]:6.2f} {self.tem_status['stage.GetPos_diff'][3]:6.2f}, {backlash}")