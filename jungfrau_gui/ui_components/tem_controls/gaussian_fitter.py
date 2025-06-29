import logging
import numpy as np 
from PySide6.QtCore import QObject, Signal, Slot
# from line_profiler import LineProfiler

from .toolbox.fit_beam_intensity import gaussian2d_rotated, super_gaussian2d_rotated, fit_2d_gaussian_roi_NaN

class GaussianFitter(QObject):
    finished = Signal(object)
    updateParamsSignal = Signal(object, object)

    def __init__(self):
        super(GaussianFitter, self).__init__()
        self.task_name = "Gaussian Fitter"
        self.imageItem = None
        self.roi = None
        self.updateParamsSignal.connect(self.updateParams)
    
    @Slot(object, object)
    def updateParams(self, imageItem, roi):
        # Thread-safe update of parameters
        self.imageItem = imageItem
        self.roi = roi

    @Slot()
    def run(self):
        if not self.imageItem or not self.roi:
            logging.warning("ImageItem or ROI not set.\nSetting now...")
            return
        im = self.imageItem.image
        roiPos = self.roi.pos()
        roiSize = self.roi.size()
        roi_start_row = int(np.floor(roiPos.y()))
        roi_end_row = int(np.ceil(roiPos.y() + roiSize.y()))
        roi_start_col = int(np.floor(roiPos.x()))
        roi_end_col = int(np.ceil(roiPos.x() + roiSize.x()))
        fit_result = fit_2d_gaussian_roi_NaN(im, roi_start_row, roi_end_row, roi_start_col, roi_end_col, function = super_gaussian2d_rotated)
        self.finished.emit(fit_result.best_values)

    def __str__(self) -> str:
        return "Gaussian Fitter"