import time
import logging
import numpy as np 
from ZmqReceiver import *
from Hdf5File import Hdf5File
from fit_beam_intensity import fit_2d_gaussian_roi
from PySide6.QtCore import (QObject, Signal, Slot)
import globals
from line_profiler import LineProfiler



class Reader(QObject):
    finished = Signal(object, object)  # Signal to indicate completion and carry results

    def __init__(self, receiver):
        super(Reader, self).__init__()
        self.receiver = receiver
    
    # @profile
    @Slot()
    def run(self):
        image, frame_nb = self.receiver.get_frame()  # Retrieve image and header      
        # if globals.write_hdf5:
        #     logging.debug("In Reader")
        #     np.copyto(globals.hdf5_im, image)
        #     globals.last_frame_written = frame_nb
        #     globals.image_updated = True
        if globals.accframes > 0:
            logging.info(f'{globals.accframes} frames to add ')
            tmp = np.copy(image)
            globals.acc_image += tmp
            globals.accframes -= 1  
        # Emit signal at end of run & carry (image, frame) for connected slot           
        self.finished.emit(image, frame_nb)  # Emit signal with results

    def __str__(self) -> str:
        return "Stream Reader"



class Frame_Accumulator(QObject):
    finished = Signal(object)

    def __init__(self, nframes):
        super(Frame_Accumulator, self).__init__()
        self.nframes_to_capture = nframes

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



# class Hdf5_Writer(QObject):
#     finished = Signal(object)

#     def __init__(self, filename, mode = 'w', image_size = (512, 1024), dt = np.float32, 
#                  pixel_mask = None, fformat = 'h5'):
#         super(Hdf5_Writer, self).__init__()
#         self.filename = filename
#         self.mode = mode
#         self.image_size = image_size
#         self.dt = dt
#         self.fformat = fformat
#         self.pixel_mask = pixel_mask
#         self.write_hdf5 = False

#     def run(self):
#         logging.info("Starting write process of HDF5" )
#         globals.hdf5_im[:] = 0 
#         if self.fformat in ['h5','hdf5', 'hdf']:
#             f = Hdf5File(self.filename, self.mode, self.image_size, self.dt, self.pixel_mask)
#         else:
#             raise ValueError(f"Unknown file format: {self.fformat}")
        
#         globals.write_hdf5 = True
#         self.write_hdf5 = globals.write_hdf5
#         while self.write_hdf5:
#             if globals.image_updated:
#                 f.write(globals.hdf5_im)
#                 globals.image_updated  = False
#                 logging.debug("In Writer")
#             self.write_hdf5 = globals.write_hdf5
#         logging.debug("OUT")
#         f.close()
#         self.finished.emit(globals.last_frame_written)

#     def __str__(self) -> str:
#         return "Hdf5 Stream Writer"



class Gaussian_Fitter(QObject):
    finished = Signal(object)
    updateParamsSignal = Signal(object, object)

    def __init__(self):
        super(Gaussian_Fitter, self).__init__()
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
            logging.warning("ImageItem or ROI not set.")
            return
        im = self.imageItem.image
        roiPos = self.roi.pos()
        roiSize = self.roi.size()
        roi_start_row = int(np.floor(roiPos.y()))
        roi_end_row = int(np.ceil(roiPos.y() + roiSize.y()))
        roi_start_col = int(np.floor(roiPos.x()))
        roi_end_col = int(np.ceil(roiPos.x() + roiSize.x()))
        fit_result = fit_2d_gaussian_roi(im, roi_start_row, roi_end_row, roi_start_col, roi_end_col)
        self.finished.emit(fit_result.best_values)

    def __str__(self) -> str:
        return "Gaussian Fitter"