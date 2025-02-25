import time
import logging
from PySide6.QtCore import QObject, Signal

import globals

class FrameAccumulator(QObject):
    finished = Signal(object)

    def __init__(self, nframes):
        super(FrameAccumulator, self).__init__()
        self.nframes_to_capture = nframes
        self.task_name = "Tiff Frame Accumulator"

    def run(self):
        logging.info("Starting write process of TIFF")
        globals.acc_image[:] = 0
        globals.accframes = self.nframes_to_capture
        while globals.accframes > 0: 
            time.sleep(0.01) 

        logging.info(f'TIFF file ready!')
        self.finished.emit(globals.acc_image.copy()) 

    def __str__(self) -> str:
        return "Tiff Frame Accumulator"
