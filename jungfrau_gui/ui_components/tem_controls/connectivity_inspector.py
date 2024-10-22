import logging
from PySide6.QtCore import QObject, Signal, Slot

from simple_tem import TEMClient


class TEM_Connector(QObject):
    finished = Signal(bool)

    def __init__(self):
        super(TEM_Connector, self).__init__()
        self.task_name = "TEM Connector"
        self.client = TEMClient("temserver", 3535, verbose=True) 
    
    @Slot()
    def run(self):
        logging.info("TEM_Connector::run()")
        response = self.client.ping(timeout_ms=1000)
        self.finished.emit(response) 

    def __str__(self) -> str:
        return "TEM Connector"