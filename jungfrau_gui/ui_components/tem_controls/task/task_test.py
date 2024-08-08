import logging
import time
from datetime import datetime as dt
import traceback
import threading

from PySide6.QtCore import Signal, Slot, QObject
from PySide6.QtNetwork import QTcpSocket, QAbstractSocket

# import json

class Task(QObject):
    send_tem_command = Signal(str)
    start = Signal()
    finished = Signal()

    def __init__(self, control_worker, name):
        super().__init__()
        
        self.running = False
        self.estimated_duration_s = 1e10
        self.setObjectName(name)
        self.task_name = name
        self.control = control_worker
        self.send_tem_command.connect(control_worker.send_to_tem)
        self.start.connect(self._start)
        threading.current_thread().setName(name + "Thread")

    def run(self):
        pass

    @Slot()
    def _start(self):
        print("In _start in task.py")
        logging.info(f"Starting task {self.task_name} ...")
        self.running = True
        self.start_time = time.monotonic()
        try:
            print("Try run!")
            self.run()
        except Exception as exc:
            logging.error(f"Exception occured in task {self.task_name}: {traceback.format_exc()}")
            # ...
            print(exc)
            pass
        self.running = False
        logging.info(f"Finished task {self.task_name}")
        self.finished.emit()

    # def tem_command(self, module, cmd, args):
    #     self.send_tem_command.emit(module + "." + cmd + "(" + str(args)[1: -1] + ")")
    #     ## response = self.send_to_tem(module + "." + cmd + "(" + str(args)[1: -1] + ")")
    #     ## if len(response.split()) == 1:
    #     ##     return response
    #     ## else:
    #     ##     return re.sub('[\[\],]', '', response).split()

    def get_progress(self):
        if not self.running:
            return 0
        percentage = abs(self.start_time - time.monotonic()) / self.estimated_duration_s
        return max(0.0, min(percentage, 1.0))

    # def on_tem_receive(self):
    #     pass
        
    def tem_info(self):
        self.send_tem_command.emit("#info")

    def tem_moreinfo(self):
        self.send_tem_command.emit("#more")
        