import logging
import time
from datetime import datetime as dt
import os
import re
import numpy as np

from PySide6.QtCore import Signal, Slot, QObject, QThread
from PySide6.QtNetwork import QTcpSocket, QAbstractSocket
import json

from task.task import Task
from task.record_task import RecordTask
from task.beam_fit_tem import BeamFitTask
from task.adjustZ import AdjustZ
from task.get_teminfo import GetInfoTask
from task.stage_centering import CenteringTask

class ControlWorker(QObject):
    connected = Signal()
    finished = Signal()
    updated = Signal()
    received = Signal(str)
    send = Signal(str)
    init = Signal()
    finished_task = Signal()
    tem_socket_status = Signal(int, str)

    trigger_record = Signal()
    trigger_shutdown = Signal()
    trigger_interactive = Signal()
    trigger_getteminfo = Signal()
    trigger_centering = Signal()

    actionFit_Beam = Signal() # originally defined with QuGui
    actionAdjustZ = Signal()

    def __init__(self): #, timeout:int=10, buffer=1024):
        super().__init__()
        self.tem_socket: QTcpSocket = None
        self.task = Task(self, "Dummy")
        self.task_thread = QThread()
        self.last_task: Task = None

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
        
        if os.name == 'nt': # test on Win-Win
            self.host = "131.130.27.31"
        else: # practice on Linux-Win
            self.host = "172.17.41.22"
        self.port = 12345
        # self.__timeout = timeout
        # self.__buffer = buffer

    @Slot()
    def _init(self):
        self.tem_socket = QTcpSocket()
        # self.tem_socket.readyRead.connect(self.readyread_check)
        self.tem_socket.readyRead.connect(self.on_tem_receive)
        self.tem_socket.stateChanged.connect(
            lambda state: self.tem_socket_status.emit(state, self.tem_socket.errorString()))
        self.tem_socket.errorOccurred.connect(
            lambda state: self.tem_socket_status.emit(self.tem_socket.state(), self.tem_socket.errorString()))        
        self.tcpconnect()

        # self.send.emit("stage.Setf1OverTateTxNum(2)")

    def start_task(self, task):
        self.last_task = self.task
        self.task = task
        self.task.finished.connect(self.on_task_finished)
        # self.task.moveToThread(self.task_thread)
        self.task.start.emit()

    @Slot()
    def on_task_finished(self):
        self.finished_task.emit()
    
    def tcpconnect(self): # renamed from 'connect' to avoid an error in PySide6
        print("connecting to", self.host, self.port)
        self.tem_socket.connectToHost(self.host, self.port)

    @Slot()
    def readyread_check(self):
        print('Readyread emitted!: ', self.tem_socket.state())

    @Slot()
    def on_tem_receive(self):
        data = str(self.tem_socket.readAll()) # bytedata as QByteArray -> str
        if len(data) == 0 or data == b'': 
            return 0
        elif not "None" in data:
            data = re.sub(r'^.*}}{(.*)}\'$', r'{\1}', data)
            # print('Data receiving...')
            try:
                response = json.loads(data)
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
                #     self.task.on_tem_reveive()
            except json.JSONDecodeError:
                # print(' Json data receiving failed...', data)
                pass
      

    @Slot()
    def shutdown(self):
        # logging.info("shutting down control")
        try:
            self.send_to_tem("#quit")
            self.tem_socket.close()
            print("disconnected")
            # self.timer.stop()
            # self.task_thread.quit()
            # self.stream_thread.quit()
        except:
            pass


    @Slot()
    def send_to_tem(self, message):
        # print(f'sending {message} to TEM...')
        # print(self.tem_socket.state())
        # if self.tem_socket.state() == QAbstractSocket.SocketState.ConnectedState:
        if self.tem_socket.state() == QAbstractSocket.SocketState.ConnectingState or self.tem_socket.state() == QAbstractSocket.SocketState.ConnectedState:
            self.tem_socket.write(message.encode())
            # self.tem_socket.flush()
            self.tem_socket.waitForBytesWritten()
            # print(f'{message} sent to TEM...')
        else:
            # logging.info("invalid socket state" + str(self.tem_socket.state()))
            pass

    # @pyqtSlot()
    def stop(self):
        self.send_to_tem('stage.Stop()')
        self.finished_task.emit()
        pass
    
    @Slot()
    def start_record(self, ):
        if self.task.running:
            self.stop()
        end_angle = 60 # dummy, should be input from GUI
        ###
#        self.task.tem_command("eos", "SetSelector", [11])
#        if os.name == 'nt': self.task.tem_command("eos", "SetSelector", [20]) # test on Win-Win
#        while True:
#            self.send_to_tem('#more')
#            time.sleep(0.10)
#            if int(self.tem_status['eos.GetMagValue'][0]) == 20000: break
        ###
        task = RecordTask(self, end_angle)
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
            print('Switches ' + str(self.tem_status['eos.GetFunctionMode'][1]) + ' to DIFF mode')
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
        ###
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

    @Slot()
    def getteminfo(self):
        # if self.task.running:
        #     self.stop()
        task = GetInfoTask(self)
        self.start_task(task)
        
    @Slot()
    def centering(self):
        if self.task.running:
            self.stop()
        x = input('Input translation vector in px, e.g. \'10, 1\'. q: quit\n')
        while True:
            if x == 'q':
                break
            elif x != '':
                pixels = np.array(x.split(sep=','), dtype=float)
                task = CenteringTask(self, pixels)
                self.start_task(task)
            x = input()        
