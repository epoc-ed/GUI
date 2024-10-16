import logging
import time
import os
import numpy as np
import threading

from PySide6.QtCore import Signal, Slot, QObject, QThread

from .task import Task
from .record_task import RecordTask
from .beam_focus_task import BeamFitTask
from .adjustZ_task import AdjustZ
from .get_teminfo_task import GetInfoTask
from .stage_centering_task import CenteringTask

from simple_tem import TEMClient
from ..toolbox import tool as tools

from epoc import ConfigurationClient, auth_token, redis_host

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
    finished_task = Signal()
    finished_record_task = Signal()
    # tem_socket_status = Signal(int, str)
    
    trigger_tem_update = Signal(dict)

    fit_complete = Signal(dict)
    
    trigger_stop_autofocus = Signal()
    remove_ellipse = Signal()

    trigger_record = Signal()
    trigger_shutdown = Signal()
    # trigger_interactive = Signal()
    trigger_getteminfo = Signal(str)
    # trigger_centering = Signal(bool, str)

    actionFit_Beam = Signal() # originally defined with QuGui
    # actionAdjustZ = Signal()

    def __init__(self, tem_action): #, timeout:int=10, buffer=1024):
        super().__init__()
        self.cfg = ConfigurationClient(redis_host(), token=auth_token())
        self.client = TEMClient("localhost", 3535,  verbose=False)

        self.task = Task(self, "Dummy")
        self.task_thread = QThread()
        self.tem_action = tem_action
        self.last_task: Task = None
        
        self.setObjectName("control Thread")
        
        self.init.connect(self._init)
        self.send.connect(self.send_to_tem)
        self.trigger_record.connect(self.start_record)
        self.trigger_shutdown.connect(self.shutdown)
        # self.trigger_interactive.connect(self.interactive)
        self.trigger_getteminfo.connect(self.getteminfo)
        # self.trigger_centering.connect(self.centering)
        # self.actionAdjustZ.connect(self.start_adjustZ)

        self.actionFit_Beam.connect(self.start_beam_fit)
        self.trigger_stop_autofocus.connect(self.set_worker_not_ready)
        
        self.trigger_tem_update.connect(self.update_tem_status)
        
        self.tem_status = {"stage.GetPos": [0.0, 0.0, 0.0, 0.0, 0.0], "stage.Getf1OverRateTxNum": self.cfg.rotation_speed_idx,
                           "eos.GetFunctionMode": [-1, -1], "eos.GetMagValue": [0, 'X', 'X0k'],
                           "eos.GetMagValue_MAG": [0, 'X', 'X0k'], "eos.GetMagValue_DIFF": [0, 'X', 'X0k']}
        
        self.tem_update_times = {}
        self.triggerdelay_ms = 500

        """ 
        if os.name == 'nt': # test on Win-Win
            self.host = "131.130.27.31"
        else: # practice on Linux-Win
            self.host = "172.17.41.22"
        self.port = 12345
        # self.__timeout = timeout
        # self.__buffer = buffer
        """
    @Slot()
    def _init(self):
        threading.current_thread().setName("ControlThread")      
        # try:
        #     self.send_to_tem("#more") # Update tem_status map and GUI   
        # except Exception as e:
        #     logging.error(f"Error occured when initializing task manager: {e}")                     
        self.sweepingWorkerReady = False
        # self.send.emit("stage.Setf1OverRateTxNum(2)")
        logging.info("Initialized control thread")

    @Slot()
    def on_task_finished(self):
        self.finished_task.emit()

        if isinstance(self.task, RecordTask):
            # self.finished_record_task.emit()
            logging.info("RecordTask has finished, performing cleanup...")
            self.stop_task()

        elif isinstance(self.task, GetInfoTask):
            logging.info("GetInfoTask has finished, performing cleanup...")
            self.stop_task()

        # After stopping the task, safely delete the task and the thread
        if self.task is not None:
            logging.info(f"Deleting task: {self.task.task_name}")
            self.task.deleteLater()  # Safe deletion after thread stops

        # Ensure thread is also cleaned up
        if self.task_thread:
            self.task_thread.quit()
            self.task_thread.wait()
            self.task_thread.deleteLater()  # Clean up the thread itself

        self.task = None
        self.task_thread = None  # Reset thread for the next task

    def start_task(self, task):
        logging.debug("Control is starting a Task...")
        self.last_task = self.task
        self.task = task

        # Create a new QThread for each task to avoid reuse issues
        self.task_thread = QThread()  
        logging.info(f"Task name is {self.task.task_name}")

        self.tem_action.parent.threadWorkerPairs.append((self.task_thread, self.task))

        self.task.finished.connect(self.on_task_finished)

        self.task.moveToThread(self.task_thread)
        self.task_thread.started.connect(self.task.start.emit)
        self.task_thread.start()

        if isinstance(self.task, BeamFitTask):
            self.sweepingWorkerReady = True

    @Slot(str)
    def getteminfo(self, gui=''):
        logging.info("Start GetInfo")
        if self.task is not None:
            if self.task.running:
                self.stop_task()
        # self.send.emit("stage.Setf1OverRateTxNum(2)")
        command='TEMstatus'
        if gui=='':
            x = input(f'Write TEM status on a file? If YES, give a filename or "Y" ({command}_[timecode].log). [N]\n')
            task = GetInfoTask(self, x)
        else:
            task = GetInfoTask(self, gui)
        self.start_task(task)

    @Slot()
    def start_record(self):
        logging.info("Start Rotation/Record")
        if self.task is not None:
            if self.task.running:
                self.stop_task()
        end_angle = self.tem_action.tem_tasks.update_end_angle.value() # 60
        logging.info(f"End angle = {end_angle}")
        ### filename_suffix = self.tem_action.formatted_filename[:-3]
        ### filename_suffix = self.tem_action.file_operations.generate_h5_filename(self.tem_action.file_operations.prefix_input.text().strip())[:-3]
        filename_suffix = self.tem_action.datasaving_filepath + '/RotEDlog_test'
        ###
        # self.client.SetSelector(11)
        ###
        if self.tem_action.tem_tasks.withwriter_checkbox.isChecked():
            task = RecordTask(self, end_angle, filename_suffix, writer_event = self.tem_action.file_operations.toggle_hdf5Writer)
        else:
            task = RecordTask(self, end_angle, filename_suffix)
        self.start_task(task)

    @Slot()
    def start_beam_fit(self):
        logging.info("Start AutoFocus")
        if self.task is not None:
            if self.task.running:
                logging.warning('task already running')
                return           
        ###
        # if os.name == 'nt': # test on Win-Win
        #     while True:
        #         self.send_to_tem('#more')
        #         time.sleep(0.12)
        #         if self.tem_status['eos.GetFunctionMode'][0] != -1: break
        ###
        if self.tem_status['eos.GetFunctionMode'][1] != 4:
            logging.info('Switches ' + str(self.tem_status['eos.GetFunctionMode'][1]) + ' to DIFF mode')
            
            self.client.SelectFunctionMode(4) # Diffraction Mode

        task = BeamFitTask(self)
        self.start_task(task)

    def set_worker_not_ready(self):
        logging.debug("Sweeping worker ready --> FALSE")
        self.sweepingWorkerReady = False

    @Slot(dict)
    def update_tem_status(self, response):
        """ 
        #*************** 
        print(f"Display update values")
        for key, value in response.items():
            print(f"{key}: {value}")
        #*************** 
        # """
        logging.info("Updating ControlWorker map with last TEM Status")
        try:
            logging.debug("START of the update loop")
            for entry in response:
                self.tem_status[entry] = response[entry]["val"]
                self.tem_update_times[entry] = (response[entry]["tst_before"], response[entry]["tst_after"])
            logging.debug("END of update loop")
            logging.info(f"self.tem_status['eos.GetFunctionMode'] = {self.tem_status['eos.GetFunctionMode']}")
            if self.tem_status['eos.GetFunctionMode'][0] == 0: #MAG
                self.tem_status['eos.GetMagValue_MAG'] = self.tem_status['eos.GetMagValue']
                self.tem_update_times['eos.GetMagValue_MAG'] = self.tem_update_times['eos.GetMagValue']
            elif self.tem_status['eos.GetFunctionMode'][0] == 4: #DIFF
                self.tem_status['eos.GetMagValue_DIFF'] = self.tem_status['eos.GetMagValue']
                self.tem_update_times['eos.GetMagValue_DIFF'] = self.tem_update_times['eos.GetMagValue']
            self.updated.emit()
        except Exception as e:
            logging.error(f"Error during updating tem_status map: {e}")

    @Slot(str) 
    def send_to_tem(self, message):
        logging.debug(f'Sending {message} to TEM...')
        if message == "#info":
            results = self.get_state()
            self.trigger_tem_update.emit(results)
        elif message == "#more":
            results = self.get_state_detailed()
            self.trigger_tem_update.emit(results)
        else:
            logging.debug("Just passing through")
            pass

    def get_state(self):
        results = {}
        for query in tools.INFO_QUERIES:
            tic = time.perf_counter()
            logging.debug(" ++++++++++++++++ ")
            logging.debug(f"Command from list {query}")
            logging.debug(f"Command as executed {tools.full_mapping[query]}")
            results[query] = self.execute_command(tools.full_mapping[query])
            logging.debug(f"results[query] is {results[query]}")
            toc = time.perf_counter()
            logging.info(f"Getting info for {query} took {toc - tic} seconds")

        return results
    
    def get_state_detailed(self):
        results = {}
        for query in tools.MORE_QUERIES:
            result = {}
            result["tst_before"] = time.time()
            result["val"] = self.execute_command(tools.full_mapping[query])
            result["tst_after"] = time.time()
            results[query] = result
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
        except Exception as e:
            logging.error(f"Error: {e}")

    def stop_task(self):
        if self.task:
            if isinstance(self.task, BeamFitTask):
                logging.info("Stopping the - Sweeping - task!")
                self.trigger_stop_autofocus.emit()

            elif isinstance(self.task, RecordTask):
                logging.info("Stopping the - Record - task!")
                try:
                    tools.send_with_retries(self.client.StopStage)
                except Exception as e:
                    logging.error(f"Unexpected error @ client.StopStage(): {e}")
                    pass

            elif isinstance(self.task, GetInfoTask):
                logging.info("Stopping the - GetInfo - task!")

        # Ensure the thread is fully stopped before starting a new task
        if self.task_thread and self.task_thread.isRunning():
            logging.info(f"Quitting {self.task.task_name} Thread")
            self.task_thread.quit()
            self.task_thread.wait()

        # Do not delete task here; deletion is handled in `on_task_finished`
        self.task = None
        self.task_thread = None
        
        if isinstance(self.task, BeamFitTask):
                logging.info("********** Emitting 'remove_ellipse' signal from -MAIN- Thread **********")
                self.remove_ellipse.emit() 

        if self.task_thread is not None:
            if self.task_thread.isRunning():
                logging.info(f"Quitting {self.task.task_name} Thread")
                self.task_thread.quit()
                self.task_thread.wait() # Wait for the thread to actually finish
                self.task.deleteLater() # --> RuntimeError: Internal C++ object (BeamFitTask) already deleted.
                self.task = None

    @Slot()
    def stop(self):
        tools.send_with_retries(self.client.StopStage)
        self.finished_task.emit()
        pass

    @Slot()
    def shutdown(self):
        logging.info("Shutting down control")
        try:
            # self.send_to_tem("#quit")
            self.client.exit()
            time.sleep(0.12)
            # self.tem_socket.close()
            logging.info("disconnected")
            self.task_thread.quit()
        except:
            pass

    """ 
    @Slot()
    def start_adjustZ(self):
        if self.task.running:
            logging.warning('task already running')
            return
        ###
        if os.name == 'nt': # test on Win-Win
            while True:
                #########################
                define #more 
                #########################
                self.send_to_tem('#more')
                time.sleep(0.12)
                if self.tem_status['eos.GetFunctionMode'][0] != -1: break
        ###
        # if self.tem_status['eos.GetFunctionMode'][1] != 0:
        #     print('Switches ' + str(self.tem_status['eos.GetFunctionMode'][0]) + ' to MAG mode')
        #     self.task.tem_command("eos", "SelectFunctionMode", [0])
        #         ## self.client.SelectFunctionMode(0)  
        # if self.tem_status['eos.GetMagValue'][0] <= 200: # 1
        #     print('Changes magnifitation ' + str(self.tem_status['eos.GetMagValue'][2]) + ' to x20k')
        #     self.task.tem_command("eos", "SetSelector", [20])
        #     ##self.client.SetSelector(20) 
        #stop##
        if os.name == 'nt': # test on Win-Win
            while True:
                self.send_to_tem('#more')
                time.sleep(0.12)
                if int(self.tem_status['eos.GetMagValue'][0]) == 20000: break
        ###
        task = AdjustZ(self)
        self.start_task(task) 
        """
    
    """ 
    @Slot()
    def interactive(self):
        if self.task.running:
            self.stop()
        x = input('Input a command sending to TEM. q: quit\n')
        while True:
            if x == 'q':
                break
            elif x != '':
                #########################
                self.send_to_tem(x)
                #########################
            x = input() """

        
    """ 
    @Slot(bool, str)
    def centering(self, gui=False, vector='10, 1'):
        if self.task.running:
            self.stop()
            
        if not gui:
            x = input('Input translation vector in px, e.g. \'10, 1\'. q: quit\n')
            while True:
                if x == 'q':
                    break
                elif x != '':
                    pixels = np.array(x.split(sep=','), dtype=float)
                    task = CenteringTask(self, pixels)
                    self.start_task(task)
                x = input()
        else:
            pixels = np.array(vector.split(sep=','), dtype=float)
            task = CenteringTask(self, pixels)
            self.start_task(task) 
        """
    
    def update_rotation_info(self, reset=False):
        if reset:
            self.rotation_status = {"start_angle": 0, "end_angle": 0,
                                    "start_time": 0, "end_time": 0,
                                    "nimages": 0,}
        else:
            self.rotation_status["oscillation_per_frame"] = np.abs(self.rotation_status["end_angle"] - self.rotation_status["start_angle"]) / self.rotation_status["nimages"]