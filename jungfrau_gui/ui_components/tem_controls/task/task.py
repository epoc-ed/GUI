import logging
import time
import traceback
import threading

from PySide6.QtCore import Signal, Slot, QObject

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
        self.send_tem_command.connect(self.control.send_to_tem)
        self.start.connect(self._start)
        threading.current_thread().setName(name + "Thread")

    def run(self):
        logging.debug("Empty run in Task.py")
        pass

    @Slot()
    def _start(self):
        logging.debug("In _start in task.py")
        logging.info(f"Starting - {self.task_name} task...")
        self.running = True
        self.start_time = time.monotonic()
        try:
            self.run()
        except Exception as exc:
            logging.error(f"Exception occured in task {self.task_name}: {traceback.format_exc()}")
            pass
        self.running = False
        self.finished.emit()

    def get_progress(self):
        if not self.running:
            return 0
        percentage = abs(self.start_time - time.monotonic()) / self.estimated_duration_s
        return max(0.0, min(percentage, 1.0))

    # def on_tem_receive(self):
    #     pass
        
    def tem_info(self):
        logging.debug(f"{self.task_name} has asked for #info")
        self.send_tem_command.emit("#info")

    def tem_moreinfo(self):
        logging.debug(f"{self.task_name} has asked for #more")
        self.send_tem_command.emit("#more")
        