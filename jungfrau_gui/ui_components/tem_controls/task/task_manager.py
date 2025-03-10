import logging
import time
import os
from datetime import datetime as dt
import numpy as np
import threading

from PySide6.QtCore import Signal, Slot, QObject, QThread, QMetaObject, Qt

from .task import Task
from .record_task import RecordTask

# from .beam_focus_task import AutoFocusTask
from .beam_focus_task_test import AutoFocusTask

from .adjustZ_task import AdjustZ
from .get_teminfo_task import GetInfoTask
from .stage_centering_task import CenteringTask

from simple_tem import TEMClient
from ..toolbox import tool as tools

from epoc import ConfigurationClient, auth_token, redis_host

import jungfrau_gui.ui_threading_helpers as thread_manager

from .... import globals

# from ..gaussian_fitter_autofocus import GaussianFitter
from ..gaussian_fitter_mp import GaussianFitterMP
import copy

'''
def create_roi_coord_tuple(roi):
    roiPos = roi.pos()
    roiSize = roi.size()

    roi_start_row = int(np.floor(roiPos.y()))
    roi_end_row = int(np.ceil(roiPos.y() + roiSize.y()))
    roi_start_col = int(np.floor(roiPos.x()))
    roi_end_col = int(np.ceil(roiPos.x() + roiSize.x()))
    roi_coords = (roi_start_row, roi_end_row, roi_start_col, roi_end_col)

    return roi_coords
'''

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

    # fit_complete = Signal(dict, int)
    # request_fit = Signal(int)
    # fit_complete = Signal(dict, object)
    # request_fit = Signal(object)
    # cleanup_fitter = Signal()

    draw_ellipses_on_ui = Signal(dict)
    
    trigger_stop_autofocus = Signal()
    remove_ellipse = Signal()

    trigger_record = Signal()
    trigger_shutdown = Signal()
    # trigger_interactive = Signal()
    trigger_getteminfo = Signal(str)
    trigger_centering = Signal(bool, str)

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
        
        self.setObjectName("control Thread")
        
        self.init.connect(self._init)
        self.send.connect(self.send_to_tem)
        self.trigger_record.connect(self.start_record)
        self.trigger_shutdown.connect(self.shutdown)
        # self.trigger_interactive.connect(self.interactive)
        self.trigger_getteminfo.connect(self.getteminfo)
        self.trigger_centering.connect(self.centering)
        # self.actionAdjustZ.connect(self.start_adjustZ)

        self.beam_fitter = None
        self.actionFit_Beam.connect(self.start_beam_fit)
        # self.request_fit.connect(self.handle_request_fit) 
        # self.trigger_stop_autofocus.connect(self.set_sweeper_to_off_state)
        # self.cleanup_fitter.connect(self.stop_and_clean_fitter)
        
        self.trigger_tem_update_detailed.connect(self.update_tem_status_detailed)
        self.trigger_tem_update.connect(self.update_tem_status)
        
        self.tem_status = {"stage.GetPos": [0.0, 0.0, 0.0, 0.0, 0.0], "stage.Getf1OverRateTxNum": self.cfg.rotation_speed_idx,
                           "eos.GetFunctionMode": [-1, -1], "eos.GetMagValue": globals.mag_value_img,
                           "eos.GetMagValue_MAG": globals.mag_value_img, "eos.GetMagValue_DIFF": globals.mag_value_diff, "defl.GetBeamBlank": 0,
                           "ht.GetHtValue": 200000, "ht.GetHtValue_readout": 0}
        
        self.tem_update_times = {}
        self.triggerdelay_ms = 500
        self.previous_tx_abs = 0
        self.beam_intensity = {"pa_per_cm2": 0, "e_per_A2_sample": 0}

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
            #self.stop_and_clean_fitter()
            # self.stop_and_clean_fitter_mp()
            self.beam_fitter = None   # So we don't accidentally reuse it.
            logging.info("********** Emitting 'remove_ellipse' signal from -MAIN- Thread **********")
            self.remove_ellipse.emit()

        self.handle_task_cleanup()
        thread_manager.disconnect_worker_signals(self.task)
        thread_manager.terminate_thread(self.task_thread)
        thread_manager.remove_worker_thread_pair(self.tem_action.parent.threadWorkerPairs, self.task_thread)
        self.task, self.task_thread = thread_manager.reset_worker_and_thread(self.task, self.task_thread)
        logging.critical(f"Is Task actually reset to None ? -> {self.task is None}")

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
        # if isinstance(self.task, AutoFocusTask):
            # self.beam_fitter = GaussianFitterMP()
            # # Optional ###############
            # self.task.newBestResult.connect(on_new_best_result_in_main_thread)
            # # ########################
            # self.sweepingWorkerReady = True

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

# vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv

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
            self.tem_action.tem_controls.toggle_gaussianFit_beam()
        time.sleep(0.05)

        self.beam_fitter = GaussianFitterMP()

        task = AutoFocusTask(self)
        
        # Optional ###############
        task.newBestResult.connect(on_new_best_result_in_main_thread)
        # ########################
        
        self.sweepingWorkerReady = True

        self.start_task(task)

    def set_sweeper_to_off_state(self):
        logging.info("####### ######## Sweeping worker ready? --> FALSE")
        self.sweepingWorkerReady = False

    '''
    def handle_request_fit(self, lens_params):
        """
        lens_params is a dict like: {"il1": int, "ils": [int, int]}
        """
        if self.task.is_first_AutoFocus:
            self.do_fit(lens_params)  # Run do_fit the first time
            self.task.is_first_AutoFocus = False  # Set flag to False after the first run
        else:
            self.getFitParams(lens_params)

    def do_fit(self, lens_params):
        if self.task is not None:
            im_data = self.tem_action.parent.imageItem.image
            roi_coords = create_roi_coord_tuple(self.tem_action.parent.roi)

            im_data_copy = copy.deepcopy(im_data)
            roi_coords_copy = copy.deepcopy(roi_coords)

            self.thread_fit = QThread()
            # self.fitter = GaussianFitter(imageItem=im, roi=roi, il1_value = il1_value)
            self.fitter = GaussianFitter(image=im_data_copy,
                                         roi_coords=roi_coords_copy,
                                         lens_params= lens_params)
            self.tem_action.parent.threadWorkerPairs.append((self.thread_fit, self.fitter))                              
            self.initializeFitter(self.thread_fit, self.fitter, lens_params) # Initialize the worker thread and fitter
            self.fitterWorkerReady = True # Flag to indicate worker is ready
            self.thread_fit.start()
            logging.info("Starting fitting process")
        else:
            logging.warning("Fitting worker has been deleted ! ")

    def initializeFitter(self, thread, worker, lens_params):
        thread_manager.move_worker_to_thread(thread, worker)
        worker.finished.connect(self.emit_fit_complete_signal)
        worker.finished.connect(self.getFitterReady)

    def emit_fit_complete_signal(self, im, fit_result_best_values, lens_params):
        self.fit_complete.emit(fit_result_best_values, lens_params)
        self.process_fit_results(im, fit_result_best_values, lens_params)

    def getFitterReady(self):
        self.fitterWorkerReady = True

    def updateWorkerParams(self, im_data, roi_coords, lens_params):
        if self.thread_fit.isRunning():
            self.fitter.updateParamsSignal.emit(im_data, roi_coords, lens_params)  

    def getFitParams(self, lens_params):
        if self.fitterWorkerReady:
            self.fitterWorkerReady = False

            im_data_copy = copy.deepcopy(self.tem_action.parent.imageItem.image)
            roi_coords = create_roi_coord_tuple(self.tem_action.parent.roi)
            roi_coords_copy = copy.deepcopy(roi_coords)

            self.updateWorkerParams(im_data_copy, roi_coords_copy, lens_params)
            time.sleep(0.01) # ensure update goes through before fitting starts 
            QMetaObject.invokeMethod(self.fitter, "run", Qt.QueuedConnection)

    def process_fit_results(self, im, fit_result, lens_params):
        # Extract necessary fit parameters
        sigma_x = float(fit_result["sigma_x"])
        sigma_y = float(fit_result["sigma_y"])
        
        # Compute metrics
        area = sigma_x * sigma_y
        aspect_ratio = max(sigma_x, sigma_y) / min(sigma_x, sigma_y)
        
        # Simple combined figure of merit
        fom = area * aspect_ratio #TODO: Optimize FOM
        
        # Initialize self.task.results if not present
        if not hasattr(self.task, "results"):
            self.task.results = []
        
        # Store all results
        self.task.results.append({
            "il1_value": lens_params["il1"],
            "ils_value": lens_params["ils"],
            "im": im,
            "sigma_x": sigma_x,
            "sigma_y": sigma_y,
            "area": area,
            "aspect_ratio": aspect_ratio,
            "fom": fom
        })
        
        # Optionally keep track of the best so far
        # If we haven't picked a best yet, or if this one is better
        if not hasattr(self.task, "best_result"):
            self.task.best_result = self.task.results[-1]
        else:
            if fom < self.task.best_result["fom"]:
                self.task.best_result = self.task.results[-1]
        
        logging.info(dt.now().strftime(" PROCESSED @ %H:%M:%S.%f")[:-3])

    def stop_and_clean_fitter(self):
        logging.info(f"Quitting GaussianFitting Thread")
        thread_manager.disconnect_worker_signals(self.fitter)
        thread_manager.terminate_thread(self.thread_fit)
        thread_manager.remove_worker_thread_pair(self.tem_action.parent.threadWorkerPairs, self.thread_fit)
        thread_manager.reset_worker_and_thread(self.fitter, self.thread_fit)
    '''

# AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA

    @Slot(dict)
    def update_tem_status_detailed(self, response):
        """ 
        #*************** 
        print(f"Display update values")
        for key, value in response.items():
            print(f"{key}: {value}")
        #*************** 
        # """
        logging.debug("Updating ControlWorker map with last TEM Status")
        try:
            logging.debug("START of the update loop")
            for entry in response:
                self.tem_status[entry] = response[entry]["val"]
                self.tem_update_times[entry] = (response[entry]["tst_before"], response[entry]["tst_after"])
            logging.debug("END of update loop")
            logging.debug(f"self.tem_status['eos.GetFunctionMode'] = {self.tem_status['eos.GetFunctionMode']}")
            if self.tem_status['eos.GetFunctionMode'][0] == 0: #MAG
                self.tem_status['eos.GetMagValue_MAG'] = self.tem_status['eos.GetMagValue']
                # self.cfg.mag_value_img = self.tem_status['eos.GetMagValue']
                globals.mag_value_img = self.tem_status['eos.GetMagValue']
                self.tem_update_times['eos.GetMagValue_MAG'] = self.tem_update_times['eos.GetMagValue']
            elif self.tem_status['eos.GetFunctionMode'][0] == 4: #DIFF
                self.tem_status['eos.GetMagValue_DIFF'] = self.tem_status['eos.GetMagValue']
                # self.cfg.mag_value_diff = self.tem_status['eos.GetMagValue']
                globals.mag_value_diff = self.tem_status['eos.GetMagValue']
                self.tem_update_times['eos.GetMagValue_DIFF'] = self.tem_update_times['eos.GetMagValue']
            
            # Update blanking button with live status at TEM
            if self.tem_status["defl.GetBeamBlank"] == 0:
                self.tem_action.tem_stagectrl.blanking_button.setText("Blank beam")
                self.tem_action.tem_stagectrl.blanking_button.setStyleSheet('background-color: rgb(53, 53, 53); color: white;')
            else:
                self.tem_action.tem_stagectrl.blanking_button.setText("Unblank beam")
                self.tem_action.tem_stagectrl.blanking_button.setStyleSheet('background-color: orange; color: white;')

            logging.debug("TEM Status Dictionnary updated!")
            
            # import json
            # # Save to text file
            # with open('tem_status.txt', 'w') as file:
            #     json.dump(self.tem_status, file, indent=4)  # 'indent=4' makes it pretty-printed

            self.updated.emit()
        except Exception as e:
            logging.error(f"Error during updating tem_status map: {e}")

    @Slot(dict)
    def update_tem_status(self, response):
        try:
            for entry in response:
                self.tem_status[entry] = response[entry]
            logging.debug(f"self.tem_status['eos.GetFunctionMode'] = {self.tem_status['eos.GetFunctionMode']}")
            if self.tem_status['eos.GetFunctionMode'][0] == 0: #MAG
                self.tem_status['eos.GetMagValue_MAG'] = self.tem_status['eos.GetMagValue']
                # self.cfg.mag_value_img = self.tem_status['eos.GetMagValue']
                globals.mag_value_img = self.tem_status['eos.GetMagValue']
            elif self.tem_status['eos.GetFunctionMode'][0] == 4: #DIFF
                self.tem_status['eos.GetMagValue_DIFF'] = self.tem_status['eos.GetMagValue']
                # self.cfg.mag_value_diff = self.tem_status['eos.GetMagValue']
                globals.mag_value_diff = self.tem_status['eos.GetMagValue']

            # Update blanking button with live status at TEM
            if self.tem_status["defl.GetBeamBlank"] == 0:
                self.tem_action.tem_stagectrl.blanking_button.setText("Blank beam")
                self.tem_action.tem_stagectrl.blanking_button.setStyleSheet('background-color: rgb(53, 53, 53); color: white;')
            else:
                self.tem_action.tem_stagectrl.blanking_button.setText("Unblank beam")
                self.tem_action.tem_stagectrl.blanking_button.setStyleSheet('background-color: orange; color: white;')

            self.updated.emit()
            
        except Exception as e:
            logging.error(f"Error during quick updating tem_status map: {e}")

    @Slot(str) 
    def send_to_tem(self, message, asynchronous = True):
        logging.debug(f'Sending {message} to TEM...')
        if message == "#info":
            if asynchronous:
                threading.Thread(target=lambda: self.trigger_tem_update.emit(self.get_state())).start()
            else:
                results = self.get_state()
                self.trigger_tem_update.emit(results)

        elif message == "#more":
            if asynchronous:
                threading.Thread(target=lambda: self.trigger_tem_update_detailed.emit(self.get_state_detailed())).start()
            else:
                results = self.get_state_detailed()
                self.trigger_tem_update_detailed.emit(results)
            
        else:
            logging.error(f"{message} is not valid for ControlWorker::send_to_tem()")
            pass

    def get_state(self):
        results = {}
        tic_loop = time.perf_counter()
        for query in tools.INFO_QUERIES:
            tic = time.perf_counter()
            logging.debug(" ++++++++++++++++ ")
            logging.debug(f"Command from list {query}")
            logging.debug(f"Command as executed {tools.full_mapping[query]}")
            results[query] = self.execute_command(tools.full_mapping[query])
            logging.debug(f"results[query] is {results[query]}")
            toc = time.perf_counter()
            logging.debug(f"Getting info for {query} took {toc - tic} seconds")
        toc_loop = time.perf_counter()
        logging.debug(f"Getting #info took {toc_loop - tic_loop} seconds")
        return results
    
    def get_state_detailed(self):
        results = {}
        tic_loop = time.perf_counter()
        for query in tools.MORE_QUERIES:
            result = {}
            result["tst_before"] = time.time()
            result["val"] = self.execute_command(tools.full_mapping[query])
            result["tst_after"] = time.time()
            results[query] = result   
        toc_loop = time.perf_counter()
        logging.warning(f"Getting #more took {toc_loop - tic_loop} seconds")
        return results

    def execute_command(self, command_str):
        try:
            # Split the command into method name and arguments
            parts = command_str.split('(')
            method_name = parts[0]
            arguments = parts[1].replace(')', '')
            # Function to convert string arguments to appropriate types
            def convert_arg(arg):
                if arg.lower() in ('true', 'false'):
                    return arg.lower() == 'true'  # Convert to boolean
                try:
                    if '.' in arg:
                        return float(arg)  # Convert to float
                    return int(arg)  # Convert to int
                except ValueError:
                    return arg  # Return as string if not a number
            # Check if there are no arguments
            if arguments:
                # Split arguments and convert them
                args = tuple(convert_arg(arg.strip()) for arg in arguments.split(','))
            else:
                args = ()
            # Get the method from the client object
            method = getattr(self.client, method_name)
            # Call the method with the arguments
            result = method(*args)
            # Return the result or a default value
            return result if result is not None else "No result returned"
        except AttributeError:
            logging.error(f"Error: The method '{method_name}' does not exist.")
            return None
        except Exception as e:
            logging.error(f"Error: {e}")
            return None

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

    def update_rotation_info(self, reset=False):
        if reset:
            self.rotation_status = {"start_angle": 0, "end_angle": 0,
                                    "start_time": 0, "end_time": 0,
                                    "nimages": 0,}
        else:
            self.rotation_status["oscillation_per_frame"] = np.abs(self.rotation_status["end_angle"] - self.rotation_status["start_angle"]) / self.rotation_status["nimages"]
