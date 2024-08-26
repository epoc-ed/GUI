import logging
import numpy as np 
from ... import globals

from PySide6.QtCore import QObject, Signal, Slot


class Reader(QObject):
    finished = Signal(object, object)  # Signal to indicate completion and carry results

    def __init__(self, receiver):
        super(Reader, self).__init__()
        self.receiver = receiver
    
    # @profile
    @Slot()
    def run(self):
        image, frame_nb = self.receiver.get_frame()  # Retrieve image and header      
        if globals.accframes > 0:
            logging.info(f'{globals.accframes} frames to add ')
            tmp = np.copy(image)
            globals.acc_image += tmp
            globals.accframes -= 1            
        self.finished.emit(image, frame_nb)  # Emit signal with results

    def __str__(self) -> str:
        return "Stream Reader"
    
