import logging
from datetime import datetime
import numpy as np 
from PySide6.QtCore import QObject, Signal, Slot
# from line_profiler import LineProfiler

from .fit_beam_intensity import fit_2d_gaussian_roi_test

class GaussianFitter(QObject):
    finished = Signal(object, object)
    updateParamsSignal = Signal(object, object, object)

    def __init__(self, imageItem = None, roi = None, il1_value = None):
        super(GaussianFitter, self).__init__()
        self.imageItem = imageItem
        self.roi = roi
        self.il1_value = il1_value
        self.updateParamsSignal.connect(self.updateParams)
    
    @Slot()
    def updateParams(self, imageItem, roi, il1_value):
        # Thread-safe update of parameters
        self.imageItem = imageItem
        self.roi = roi
        self.il1_value = il1_value

    @Slot()
    def run(self):
        if self.imageItem is None or self.roi is None:
            logging.warning("ImageItem or ROI not set.\n")
            return
        logging.info(datetime.now().strftime(" START FITTING @ %H:%M:%S.%f")[:-3])
        im = self.imageItem.image
        roi = self.roi
        fit_result = fit_2d_gaussian_roi_test(im, roi)
        logging.info(datetime.now().strftime(" END FITTING @ %H:%M:%S.%f")[:-3])
        self.finished.emit(fit_result.best_values, self.il1_value)

    def __str__(self) -> str:
        return "Gaussian Fitter"