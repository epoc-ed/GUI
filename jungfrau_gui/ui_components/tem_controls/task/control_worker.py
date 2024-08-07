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

from ....ui_components.tem_controls.task.task import Task
from ....ui_components.tem_controls.task.record_task import RecordTask
from ....ui_components.tem_controls.task.beam_fit_tem import BeamFitTask
from ....ui_components.tem_controls.task.adjustZ import AdjustZ
from ....ui_components.tem_controls.task.get_teminfo import GetInfoTask
from ....ui_components.tem_controls.task.stage_centering import CenteringTask

from simple_tem import TEMClient


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
    tem_socket_status = Signal(int, str)

    fit_updated = Signal(dict)
    remove_ellipse = Signal()

    trigger_record = Signal()
    trigger_shutdown = Signal()
    trigger_interactive = Signal()
    trigger_getteminfo = Signal(str)
    trigger_centering = Signal(bool, str)

    actionFit_Beam = Signal() # originally defined with QuGui
    actionAdjustZ = Signal()

    def __init__(self, tem_action): #, timeout:int=10, buffer=1024):
        super().__init__()
        
        self.client = TEMClient("temserver", 3535)

        self.tem_socket: QTcpSocket = None
        self.task = Task(self, "Dummy")
        self.task_thread = QThread()
        # self.stream_receiver = StreamReceiver(self)
        self.tem_action = tem_action
        self.last_task: Task = None
        
        self.setObjectName("control Thread")
        
        self.init.connect(self._init)
        self.send.connect(self.send_to_tem)
        self.trigger_record.connect(self.start_record)
        self.trigger_shutdown.connect(self.shutdown)
        self.trigger_interactive.connect(self.interactive)
        self.trigger_getteminfo.connect(self.getteminfo)
        self.trigger_centering.connect(self.centering)

        self.actionFit_Beam.connect(self.start_beam_fit)
        self.actionAdjustZ.connect(self.start_adjustZ)
        
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
        logging.info("initializing control thread...")
        
        self.tem_socket = QTcpSocket()
        # self.tem_socket.readyRead.connect(self.readyread_check)
        self.tem_socket.readyRead.connect(self.on_tem_receive)
        self.tem_socket.stateChanged.connect(
            lambda state: self.tem_socket_status.emit(state, self.tem_socket.errorString()))
        self.tem_socket.errorOccurred.connect(
            lambda state: self.tem_socket_status.emit(self.tem_socket.state(), self.tem_socket.errorString()))        
        self.tcpconnect()
        
        self.task_thread.start()
        
        # self.send.emit("stage.Setf1OverRateTxNum(2)")
        logging.info("initialized control thread")

    def start_task(self, task):
        self.last_task = self.task
        self.task = task
        """ ********************************************* """
        self.tem_action.parent.threadWorkerPairs.append((self.task_thread, self.task))
        """ ********************************************* """
        self.task.finished.connect(self.on_task_finished)
        self.finished_task.connect(self.on_fitting_over)
        self.task.moveToThread(self.task_thread)
        self.task.start.emit()

    @Slot()
    def on_task_finished(self):
        self.finished_task.emit()

    def on_fitting_over(self):
        if isinstance(self.task, BeamFitTask):
            self.remove_ellipse.emit() 
    
    def tcpconnect(self): # renamed from 'connect' to avoid an error in PySide6
        logging.info(f"connecting to {self.host}:{self.port}")
        self.tem_socket.connectToHost(self.host, self.port)
        if self.tem_socket.waitForConnected(5000): # msec
            logging.info("connected.")
            return
        logging.warning("Connection failed.")        

    @Slot()
    def readyread_check(self):
        print('Readyread emitted!: ', self.tem_socket.state())

    @Slot()
    def on_tem_receive(self):
        # data = str(self.tem_socket.readAll()) # bytedata as QByteArray -> str
        data = self.tem_socket.readAll() # bytedata as QByteArray -> str
        if len(data) == 0 or data == b'': 
            return 0
        # elif not "None" in data:
        #     data = re.sub(r'^.*}}{(.*)}\'$', r'{\1}', data)
        #     # print('Data receiving...')
        try:
            response = json.loads(bytes(data)) # response = json.loads(data)
            # print(' Json data receiving...', data)
            for entry in response:
                self.tem_status[entry] = response[entry]["val"]
                self.tem_update_times[entry] = (response[entry]["tst_before"], response[entry]["tst_after"])
            if self.tem_status['eos.GetFunctionMode'][0] == 0: #MAG
                self.tem_status['eos.GetMagValue_MAG'] = self.tem_status['eos.GetMagValue']
                self.tem_update_times['eos.GetMagValue_MAG'] = self.tem_update_times['eos.GetMagValue']
            elif self.tem_status['eos.GetFunctionMode'][0] == 4: #DIFF
                self.tem_status['eos.GetMagValue_DIFF'] = self.tem_status['eos.GetMagValue']
                self.tem_update_times['eos.GetMagValue_DIFF'] = self.tem_update_times['eos.GetMagValue']
            self.updated.emit()
            # if self.task.running:
            #     self.task.on_tem_receive()
        except json.JSONDecodeError:
            # print(' Json data receiving failed...', data)
            pass
      

    @Slot()
    def shutdown(self):
        logging.info("shutting down control")
        try:
            self.send_to_tem("#quit")
            time.sleep(0.12)
            self.tem_socket.close()
            logging.info("disconnected")
            # self.timer.stop()
            self.task_thread.quit()
            # self.stream_thread.quit()
        except:
            pass

    """ ********************************************* """
    @Slot()
    def stop_task(self):
    
        ## TODO? -> tell TEM to stop: self.send_to_tem('stage.Stop()')  ???
        # self.send_to_tem('stage.Stop()')
        self.client.exit()
        time.sleep(0.1)
        
        if self.task:
            self.task.finished.disconnect()
            self.fit_updated.disconnect()
            self.remove_ellipse.emit()
        if self.task_thread is not None:
            if self.task_thread.isRunning():
                self.task_thread.quit()
                self.task_thread.wait() # Wait for the thread to actually finish

        """ index_to_delete = None
        for i, (thread, worker) in enumerate(self.tem_action.parent.threadWorkerPairs):
            if thread == self.task_thread:
                if worker is not None:
                    logging.info(f"Stopping {worker.task_name}!") # self.task.task_name
                    worker.deleteLater() # Schedule the worker for deletion
                    worker = None
                    logging.info("Process stopped!")
                index_to_delete = i
                break # because always only one instance of a thread/worker pair type
        if index_to_delete is not None:
            del self.tem_action.parent.threadWorkerPairs[index_to_delete]
        self.task_thread.deleteLater()  # Schedule the thread for deletion
        self.task_thread = None """
   
    """ ********************************************* """

    @Slot(str) 
    def send_to_tem(self, message):
        logging.debug(f'sending {message} to TEM...')
        logging.debug(self.tem_socket.state())
        # if self.tem_socket.state() == QAbstractSocket.SocketState.ConnectedState:
        if self.tem_socket.state() == QAbstractSocket.SocketState.ConnectingState or self.tem_socket.state() == QAbstractSocket.SocketState.ConnectedState:
            self.tem_socket.write(message.encode())
            # self.tem_socket.flush()
            self.tem_socket.waitForBytesWritten()
            # print(f'{message} sent to TEM...')
        else:
            logging.info("invalid socket state " + str(self.tem_socket.state()))
            pass

    @Slot()
    def stop(self):
        self.send_to_tem('stage.Stop()')
        self.finished_task.emit()
        pass
    
    @Slot()
    def start_record(self):
        if self.task.running:
            self.stop()
        end_angle = self.tem_action.tem_tasks.update_end_angle.value() # 60
        # filename_suffix = self.tem_action.formatted_filename[:-3]
        # filename_suffix = self.tem_action.file_operations.generate_h5_filename(self.tem_action.file_operations.prefix_input.text().strip())[:-3]
        filename_suffix = self.tem_action.datasaving_filepath + '/RotEDlog_test'
        ###
#        self.task.tem_command("eos", "SetSelector", [11])
        ###
        if self.tem_action.tem_tasks.withwriter_checkbox.isChecked():
            task = RecordTask(self, end_angle, filename_suffix, writer_event = self.tem_action.file_operations.toggle_hdf5Writer)
        else:
            task = RecordTask(self, end_angle, filename_suffix)
        self.start_task(task)

    @Slot()
    def start_beam_fit(self):
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
            self.task.tem_command("eos", "SelectFunctionMode", [4])
        task = BeamFitTask(self)
        self.start_task(task)

    @Slot()
    def start_adjustZ(self):
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
#        if self.tem_status['eos.GetFunctionMode'][1] != 0:
#            print('Switches ' + str(self.tem_status['eos.GetFunctionMode'][0]) + ' to MAG mode')
#            self.task.tem_command("eos", "SelectFunctionMode", [0])
#        if self.tem_status['eos.GetMagValue'][0] <= 200: # 1
#            print('Changes magnifitation ' + str(self.tem_status['eos.GetMagValue'][2]) + ' to x20k')
#            self.task.tem_command("eos", "SetSelector", [20])
        #stop##
        if os.name == 'nt': # test on Win-Win
            while True:
                self.send_to_tem('#more')
                time.sleep(0.12)
                if int(self.tem_status['eos.GetMagValue'][0]) == 20000: break
        ###
        task = AdjustZ(self)
        self.start_task(task)

    @Slot()
    def interactive(self):
        if self.task.running:
            self.stop()
        x = input('Input a command sending to TEM. q: quit\n')
        while True:
            if x == 'q':
                break
            elif x != '':
                self.send_to_tem(x)
            x = input()

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
        return "speed=stage.Getf1OverRateTxNum(); stage.Setf1OverRateTxNum(0); " + tem_command \
            + "; stage.Setf1OverRateTxNum(speed)"
    
    def update_rotation_info(self, reset=False):
        if reset:
            self.rotation_status = {"start_angle": 0, "end_angle": 0,
                                    "start_time": 0, "end_time": 0,
                                    "nimages": 0,}
        else:
            self.rotation_status["oscillation_per_frame"] = np.abs(self.rotation_status["end_angle"] - self.rotation_status["start_angle"]) / self.rotation_status["nimages"]    
