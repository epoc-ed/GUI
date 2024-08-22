import logging
import time
from datetime import datetime as dt
import os
import re
import numpy as np
import threading

from PySide6.QtCore import Signal, Slot, QObject, QThread
from PySide6.QtNetwork import QTcpSocket, QAbstractSocket
import json

from ....ui_components.tem_controls.task.task_test import Task
from ....ui_components.tem_controls.task.record_task_test import RecordTask
from ....ui_components.tem_controls.task.beam_fit_tem_test import BeamFitTask
from ....ui_components.tem_controls.task.adjustZ_test import AdjustZ
from ....ui_components.tem_controls.task.get_teminfo_test import GetInfoTask
from ....ui_components.tem_controls.task.stage_centering_test import CenteringTask

from simple_tem import TEMClient


def create_full_mapping(info_queries, more_queries, info_queries_client, more_queries_client):
    mapping = {}

    # Mapping for INFO_QUERIES to INFO_QUERIES_CLIENT
    for info_query, client_query in zip(info_queries, info_queries_client):
        mapping[info_query] = client_query

    # Mapping for MORE_QUERIES to MORE_QUERIES_CLIENT
    for more_query, client_query in zip(more_queries, more_queries_client):
        mapping[more_query] = client_query

    return mapping

# Example usage
INFO_QUERIES = [
    "stage.GetPos", 
    "stage.GetStatus", 
    "eos.GetMagValue", 
    "eos.GetFunctionMode", 
    "stage.Getf1OverRateTxNum"
]

MORE_QUERIES = [
    "stage.GetPos", 
    "stage.GetStatus", 
    "eos.GetMagValue", 
    "eos.GetFunctionMode",
    "stage.Getf1OverRateTxNum",
    "apt.GetSize(1)", 
    "apt.GetSize(4)",  # 1=CL, 4=SA
    "eos.GetSpotSize", 
    "eos.GetAlpha", 
    "lens.GetCL3", 
    "lens.GetIL1", 
    "lens.GetOLf",
    "lens.GetIL3", 
    "lens.GetOLc",  # OLf = defocus(fine)
    "defl.GetILs", 
    "defl.GetPLA", 
    "defl.GetBeamBlank",
    "stage.GetMovementValueMeasurementMethod"  # 0=encoder/1=potentio
]

INFO_QUERIES_CLIENT = [
    "GetStagePosition()", 
    "GetStageStatus()", 
    "GetMagValue()", 
    "GetFunctionMode()", 
    "Getf1OverRateTxNum()"
]

MORE_QUERIES_CLIENT = [
    "GetStagePosition()", 
    "GetStageStatus()", 
    "GetMagValue()", 
    "GetFunctionMode()",
    "Getf1OverRateTxNum()",
    "GetAperatureSize(1)", 
    "GetAperatureSize(4)",  # 1=CL, 4=SA
    "GetSpotSize()", 
    "GetAlpha()", 
    "GetCL3()", 
    "GetIL1()", 
    "GetOLf()",
    "GetIL3()", 
    "GetOLc()",  # OLf = defocus(fine)
    "GetILs()", 
    "GetPLA()", 
    "GetBeamBlank()",
    "GetMovementValueMeasurementMethod()"  # 0=encoder/1=potentio
]

# Creating the full mapping
full_mapping = create_full_mapping(INFO_QUERIES, MORE_QUERIES, INFO_QUERIES_CLIENT, MORE_QUERIES_CLIENT)

class ControlWorker(QObject):
    """
    The 'ControlWorker' object controls communication with the TEM over a TCP channel and redirects requests to the GUI.
    It also coordinates the execution of tasks.
    """
    connected = Signal()
    finished = Signal()
    updated = Signal()
    received = Signal(str)
    send = Signal(str)
    init = Signal()
    finished_task = Signal()
    finished_record_task = Signal()
    """ tem_socket_status = Signal(int, str) """
    
    """ ********************* """
    trigger_tem_update = Signal(dict)
    """ ********************* """

    fit_complete = Signal(dict)
    
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
        
        self.client = TEMClient("temserver", 3535)

        """ self.tem_socket: QTcpSocket = None """
        # self.tem_socket = self.client.socket
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
        self.trigger_centering.connect(self.centering)
        # self.actionAdjustZ.connect(self.start_adjustZ)

        self.actionFit_Beam.connect(self.start_beam_fit)
        self.trigger_stop_autofocus.connect(self.set_worker_not_ready)
        
        self.trigger_tem_update.connect(self.update_tem_status)
        
        self.tem_status = {"stage.GetPos": [0.0, 0.0, 0.0, 0.0, 0.0], "stage.Getf1OverRateTxNum": 0.5,
                           "eos.GetFunctionMode": [-1, -1], "eos.GetMagValue": [0, 'X', 'X0k'],
                           "eos.GetMagValue_MAG": [0, 'X', 'X0k'], "eos.GetMagValue_DIFF": [0, 'X', 'X0k']}
        
        self.tem_update_times = {}
        self.triggerdelay_ms = 500
        
        if os.name == 'nt': # test on Win-Win
            self.host = "131.130.27.31"
        else: # practice on Linux-Win
            self.host = "172.17.41.22"
        self.port = 12345
        # self.__timeout = timeout
        # self.__buffer = buffer

    @Slot()
    def _init(self):
        threading.current_thread().setName("ControlThread")      
        """ self.send_to_tem("#more") """                       
        """ self.task_thread.start() """
        self.sweepingWorkerReady = False
        # self.send.emit("stage.Setf1OverRateTxNum(2)")
        logging.info("Initialized control thread")

    def start_task(self, task):
        print("In start_task in control_worker.py")
        self.last_task = self.task
        self.task = task
        print(f"task_name is {self.task.task_name}")
        """ self.send_to_tem("#more") """
        self.tem_action.parent.threadWorkerPairs.append((self.task_thread, self.task))

        """ self.task.finished.connect(self.on_task_finished)
        self.finished_task.connect(self.on_fitting_over) """
        self.task.finished.connect(self.on_task_finished)
        self.finished_record_task.connect(self.stop_task)

        self.task.moveToThread(self.task_thread)
        # ******
        self.task_thread.start()
        if isinstance(self.task, BeamFitTask):
            self.sweepingWorkerReady = True
        self.task_thread.started.connect(self.task.start.emit)
        # ******
        """ self.task.start.emit() """
        # time.sleep(1)

    @Slot()
    def on_task_finished(self):
        self.finished_task.emit()
        if isinstance(self.task, RecordTask):
            self.finished_record_task.emit()

    @Slot(dict)
    def update_tem_status(self, response):
        """ *************** """
        # print(f"Display update values")
        # for key, value in response.items():
        #     print(f"{key}: {value}")
        """ *************** """
        print("Updating TEM Status")
        try:
            print("BEGINNING update loop")
            for entry in response:
                self.tem_status[entry] = response[entry]["val"]
                self.tem_update_times[entry] = (response[entry]["tst_before"], response[entry]["tst_after"])
            print("END update loop")
            print(f"self.tem_status['eos.GetFunctionMode'] = {self.tem_status['eos.GetFunctionMode']}")
            if self.tem_status['eos.GetFunctionMode'][0] == 0: #MAG
                self.tem_status['eos.GetMagValue_MAG'] = self.tem_status['eos.GetMagValue']
                self.tem_update_times['eos.GetMagValue_MAG'] = self.tem_update_times['eos.GetMagValue']
            elif self.tem_status['eos.GetFunctionMode'][0] == 4: #DIFF
                self.tem_status['eos.GetMagValue_DIFF'] = self.tem_status['eos.GetMagValue']
                self.tem_update_times['eos.GetMagValue_DIFF'] = self.tem_update_times['eos.GetMagValue']

            print("Before emission")
            self.updated.emit()
            print("After emission")
        except Exception as e:
            print(f"Error: {e}")

    @Slot(str) 
    def send_to_tem(self, message):
        logging.debug(f'sending {message} to TEM...')
        if message == "#info":
            results = self.get_state()
            self.trigger_tem_update.emit(results)
            # self.update_tem_status(results)
        elif message == "#more":
            results = self.get_state_detailed()
            self.trigger_tem_update.emit(results)
            # self.update_tem_status(results)
        else:
            print("Just passing through")
            pass

    def get_state(self):
        results = {}
        for query in INFO_QUERIES:
            tic = time.perf_counter()
            # print(" ++++++++++++++++ ")
            # print(f"Command from list {query}")
            # print(f"Command as executed {full_mapping[query]}")
            results[query] = self.execute_command(full_mapping[query])
            # print(f"results[query] is {results[query]}")
            toc = time.perf_counter()
            print("Getting info for", query, "Took", toc - tic, "seconds")

        return results
    
    def get_state_detailed(self):
        results = {}
        for query in MORE_QUERIES:
            result = {}
            result["tst_before"] = time.time()
            result["val"] = self.execute_command(full_mapping[query])
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
            print(f"Error: The method '{method_name}' does not exist.")
        except Exception as e:
            print(f"Error: {e}")

    @Slot()
    def shutdown(self):
        logging.info("shutting down control")
        try:
            # self.send_to_tem("#quit")
            self.client.exit()
            time.sleep(0.12)
            # self.tem_socket.close()
            logging.info("disconnected")
            self.task_thread.quit()
        except:
            pass

    @Slot()
    def stop_task(self):
        if self.task:
            if isinstance(self.task, BeamFitTask):
                print("Stopping the - Sweeping - task !")
                self.trigger_stop_autofocus.emit() # self.set_worker_not_ready()
            elif isinstance(self.task, RecordTask):
                print("Stopping the - Record - task!!!")
                self.client.StopStage()
        
        if isinstance(self.task, BeamFitTask):
                print("********************* Emitting 'remove_ellipse' signal from -MAIN- Thread *********************")
                self.remove_ellipse.emit() 

        if self.task_thread is not None:
            if self.task_thread.isRunning():
                print(f"Quitting {self.task.task_name} Thread")
                self.task_thread.quit()
                self.task_thread.wait() # Wait for the thread to actually finish
                self.task.deleteLater() # --> RuntimeError: Internal C++ object (BeamFitTask) already deleted.
                self.task = None

    @Slot()
    def stop(self):
        # self.send_to_tem('stage.Stop()')
        self.client.StopStage()
        self.finished_task.emit()
        pass
    
    @Slot()
    def start_record(self):
        print("Start record")
        if self.task is not None:
            if self.task.running:
                self.stop_task()
        end_angle = self.tem_action.tem_tasks.update_end_angle.value() # 60
        print(f"End angle + {end_angle}")
        ### filename_suffix = self.tem_action.formatted_filename[:-3]
        ### filename_suffix = self.tem_action.file_operations.generate_h5_filename(self.tem_action.file_operations.prefix_input.text().strip())[:-3]
        filename_suffix = self.tem_action.datasaving_filepath + '/RotEDlog_test'
        ###
        # self.task.tem_command("eos", "SetSelector", [11])
        """ self.client.SetSelector(11) """
        ###
        if self.tem_action.tem_tasks.withwriter_checkbox.isChecked():
            task = RecordTask(self, end_angle, filename_suffix, writer_event = self.tem_action.file_operations.toggle_hdf5Writer)
        else:
            task = RecordTask(self, end_angle, filename_suffix)
        print("before")
        self.start_task(task)
        print("after")

    @Slot()
    def start_beam_fit(self):
        print("Start AutoFocus")
        if self.task is not None:
            if self.task.running:
                logging.warning('task already running')
                return           
        ###
        if os.name == 'nt': # test on Win-Win
            while True:
                self.send_to_tem('#more')
                time.sleep(0.12)
                if self.tem_status['eos.GetFunctionMode'][0] != -1: break
        ###
        if self.tem_status['eos.GetFunctionMode'][1] != 4:
            logging.info('Switches ' + str(self.tem_status['eos.GetFunctionMode'][1]) + ' to DIFF mode')
            
            # self.task.tem_command("eos", "SelectFunctionMode", [4])
            self.client.SelectFunctionMode(4)

        task = BeamFitTask(self)
        self.start_task(task)

    def set_worker_not_ready(self):
        print("Sweeping WORKER READY = FALSE")
        self.sweepingWorkerReady = False

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

    @Slot(str)
    def getteminfo(self, gui=''):
        # if self.task.running:
        #     self.stop()
        # self.send.emit("stage.Setf1OverRateTxNum(2)")
        command='TEMstatus'
        if gui=='':
            x = input(f'Write TEM status on a file? If YES, give a filename or "Y" ({command}_[timecode].log). [N]\n')
            task = GetInfoTask(self, x)
        else:
            task = GetInfoTask(self, gui)
        self.start_task(task)
        
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
    
    def with_max_speed(self, tem_command):
        speed = self.client.Getf1OverRateTxNum()
        self.client.Setf1OverRateTxNum(0)
        self.execute_command(tem_command)
        self.client.Setf1OverRateTxNum(speed)
    
    def update_rotation_info(self, reset=False):
        if reset:
            self.rotation_status = {"start_angle": 0, "end_angle": 0,
                                    "start_time": 0, "end_time": 0,
                                    "nimages": 0,}
        else:
            self.rotation_status["oscillation_per_frame"] = np.abs(self.rotation_status["end_angle"] - self.rotation_status["start_angle"]) / self.rotation_status["nimages"]