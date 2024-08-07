import logging
import numpy as np
import multiprocessing as mp
from lmfit import Model, Parameters
from PySide6.QtCore import QObject, Signal
from line_profiler import LineProfiler

import globals

# Define a rotated 2D Gaussian function
def gaussian2d_rotated(x, y, amplitude, xo, yo, sigma_x, sigma_y, theta):
    xo = float(xo)
    yo = float(yo)    
    a = (np.cos(theta)**2)/(2*sigma_x**2) + (np.sin(theta)**2)/(2*sigma_y**2)
    b = -(np.sin(2*theta))/(4*sigma_x**2) + (np.sin(2*theta))/(4*sigma_y**2)
    c = (np.sin(theta)**2)/(2*sigma_x**2) + (np.cos(theta)**2)/(2*sigma_y**2)
    g = amplitude * np.exp( - (a * ((x-xo)**2) + 2 * b * (x-xo) * (y-yo) + c * ((y-yo)**2)))
    return g.ravel()

# @profile
def fit_2d_gaussian_roi(im, roi_start_row, roi_end_row, roi_start_col, roi_end_col):
    
    im_roi = im[roi_start_row:roi_end_row, roi_start_col:roi_end_col]
    n_columns_roi, n_rows_roi = im_roi.shape[1], im_roi.shape[0]
    diag_roi = np.sqrt(n_columns_roi*n_columns_roi+n_rows_roi*n_rows_roi)
    
    x_roi, y_roi = np.meshgrid(np.arange(n_columns_roi), np.arange(n_rows_roi))
    z_flat_roi = im_roi.ravel()
    x_flat_roi = x_roi.ravel()
    y_flat_roi = y_roi.ravel()

    # Create model and parameters for ROI fitting
    model_roi = Model(gaussian2d_rotated, independent_vars=['x','y'], nan_policy='omit')
    params_roi = Parameters()
    params_roi.add('amplitude', value=np.max(im), min=1, max=10*np.max(im))
    params_roi.add('xo', value=n_columns_roi//2, min=0, max=n_columns_roi)
    params_roi.add('yo', value=n_rows_roi//2, min=0,max=n_rows_roi)
    params_roi.add('sigma_x', value=n_columns_roi//4, min=1, max=diag_roi//2)  # Adjusted for likely ROI size
    params_roi.add('sigma_y', value=n_rows_roi//4, min=1, max=diag_roi//2)    # Adjusted for likely ROI size
    params_roi.add('theta', value=0, min=-np.pi/2, max=np.pi/2)

    result_roi = model_roi.fit(z_flat_roi, x=x_flat_roi, y=y_flat_roi, params=params_roi)
    fit_result = result_roi
    fit_result.best_values['xo'] +=  roi_start_col
    fit_result.best_values['yo'] +=  roi_start_row

    return fit_result

def _fitGaussian(input_queue, output_queue):
    while True:
        if globals.fitterWorkerReady.value:
            if input_queue.empty():
                logging.debug("Input Queue Empty !" )
                pass
            else:
                task = input_queue.get()  # Blocking call, waits for new data
            
            # if task is None: # None is used as a signal to stop the process
            #     print("/!\/!\/!\ Stopping Fitting Process!" )
            #     break
            
            logging.debug("Ongoing Fitting.......")
            image_data, roiPos, roiSize = task
            # if not image_data or not roiPos or not roiSize:
            #     logging.warning("ImageItem or ROI not set.")
            #     output_queue.put(None)
            #     continue

            roi_start_row = int(np.floor(roiPos[1]))
            roi_end_row = int(np.ceil(roiPos[1] + roiSize[1]))
            roi_start_col = int(np.floor(roiPos[0]))
            roi_end_col = int(np.ceil(roiPos[0] + roiSize[0]))
            fit_result = fit_2d_gaussian_roi(image_data, roi_start_row, roi_end_row, roi_start_col, roi_end_col)
            output_queue.put(fit_result.best_values)
            logging.debug(f"*** Output Queue is Empty: {output_queue.empty()} ***")
            globals.fitterWorkerReady.value = False

class GaussianFitter(QObject):
    finished = Signal(object)

    def __init__(self):
        super(GaussianFitter, self).__init__()
        self.input_queue = mp.Queue()
        self.output_queue = mp.Queue()
        self.fitting_process = None 

    def start(self):
        logging.info("Starting Gaussian Fitting!")
        if self.fitting_process is None or not self.fitting_process.is_alive():
            self.fitting_process = mp.Process(target=_fitGaussian, args=(self.input_queue, self.output_queue))
            self.fitting_process.start()

    def updateParams(self, imageItem, roi):
        logging.debug("Updating parameters in the processing Queue...")
        image_data = imageItem.image.copy()  # Assuming image data can be accessed and is pickleable
        roiPos = (roi.pos().x(), roi.pos().y())
        roiSize = (roi.size().x(), roi.size().y())
        self.input_queue.put((image_data, roiPos, roiSize))
        globals.fitterWorkerReady.value = True
        logging.debug(f"3.Fitter should be ready! Is it? --> {globals.fitterWorkerReady.value}")


    def check_output_queue(self):
        logging.debug("--------------Checking---------------")
        if not self.output_queue.empty():
            logging.debug("+++++++++++ Output queue not empty +++++++++++++++")
            result = self.output_queue.get()
            if result:
                self.finished.emit(result)
                logging.debug("4. Fitter finished !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")

    def stop(self):
        # self.input_queue.put(None)  # Send None to signal the process to exit
        if self.fitting_process is not None:
            self.fitting_process.terminate()
            self.fitting_process.join()
            self.fitting_process = None
        logging.info("Closing queues and joining ")
        self.input_queue.close()
        self.output_queue.close()
        self.input_queue.cancel_join_thread()
        self.output_queue.cancel_join_thread()
        logging.info("Gaussian Fitting Process Stopped")
