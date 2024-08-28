import logging
from datetime import datetime
import numpy as np 
from PySide6.QtCore import QObject, Signal, Slot
# from line_profiler import LineProfiler

from .toolbox.fit_beam_intensity import fit_2d_gaussian_roi_fast

class GaussianFitter(QObject):
    finished = Signal(object, object)
    updateParamsSignal = Signal(object, object, object)

    def __init__(self, image, roi_coords, il1_value = None):
        super(GaussianFitter, self).__init__()
        self.image = image
        self.roi_coords = roi_coords
        self.il1_value = il1_value
        self.updateParamsSignal.connect(self.updateParams)
    
    @Slot()
    def updateParams(self, image, roi_coords, il1_value):
        # Thread-safe update of parameters
        self.image = image
        self.roi_coords = roi_coords
        self.il1_value = il1_value

    @Slot()
    def run(self):
        # if self.image is None or self.roiPos is None:
        #     logging.warning("ImageItem or ROI not set.\n")
        #     return
        logging.info(datetime.now().strftime(" START FITTING @ %H:%M:%S.%f")[:-3])
        im = self.image
        roi_coords = self.roi_coords
        fit_result = fit_2d_gaussian_roi_fast(im, roi_coords)
        logging.info(datetime.now().strftime(" END FITTING @ %H:%M:%S.%f")[:-3])
        self.finished.emit(fit_result.best_values, self.il1_value)

    def __str__(self) -> str:
        return "Gaussian Fitter"