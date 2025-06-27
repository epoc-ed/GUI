import logging
import numpy as np
import multiprocessing as mp
from PySide6.QtCore import QObject, Signal
from line_profiler import LineProfiler
import zmq
import cbor2
from ...decoder import tag_hook
from ... import globals

from .toolbox.fit_beam_intensity import gaussian2d_rotated, super_gaussian2d_rotated, fit_2d_gaussian_roi_NaN_fast
from datetime import datetime

# import globals

from queue import Empty  # or multiprocessing.queues.Empty

def create_roi_coord_tuple(roiPos, roiSize):
    roi_start_row = int(np.floor(roiPos[1]))                # roi_start_row = int(np.floor(roiPos.y()))
    roi_end_row = int(np.ceil(roiPos[1] + roiSize[1]))      # roi_end_row = int(np.ceil(roiPos.y() + roiSize.y()))
    roi_start_col = int(np.floor(roiPos[0]))                # roi_start_col = int(np.floor(roiPos.x()))
    roi_end_col = int(np.ceil(roiPos[0] + roiSize[0]))      # roi_end_col = int(np.ceil(roiPos.x() + roiSize.x()))

    return (roi_start_row, roi_end_row, roi_start_col, roi_end_col)

# Option A
def _fitGaussian(input_queue, output_queue):
    while True:
        # task = input_queue.get()  
        try:
            task = input_queue.get() # Blocking call, waits for new data
        except Exception as e:
            logging.error("Error retrieving task from input queue: %s", e)
            break
           
        if task is None:  # Sentinel for termination.
            logging.info("Termination signal received. Exiting _fitGaussian loop.")
            break
        
        try:
            logging.debug("Ongoing Fitting.......")
            image_data, roiPos, roiSize = task
            roi_coord = create_roi_coord_tuple(roiPos, roiSize)
            logging.info(datetime.now().strftime(" START FITTING @ %H:%M:%S.%f")[:-3])
            fit_result = fit_2d_gaussian_roi_NaN_fast(image_data, roi_coord, function=super_gaussian2d_rotated)
            logging.info(datetime.now().strftime(" END FITTING @ %H:%M:%S.%f")[:-3])
            output_queue.put(fit_result.best_values)
            logging.info("Task processed. Is output queue empty? %s", output_queue.empty())
        except Exception as e:
            logging.error("Error during the fitting process: %s", e)

# Option B
def _capture_and_fit_worker(input_queue, output_queue, zmq_endpoint, timeout_ms, hwm, image_size, dt):
    """
    Worker process that waits for a "CAPTURE_AND_FIT" command,
    then reads a frame from a ZeroMQ camera stream and performs the fit.
    """
    logging.info("Asynchronous Gaussian Fitting process starting...")
    # Set up the ZeroMQ context and subscriber socket.
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.setsockopt(zmq.RCVTIMEO, timeout_ms)
    # Next two options ensures to only deliver the most recent message avoiding any stale frames
    socket.setsockopt(zmq.RCVHWM, hwm) # hwm = 1 -> This limits the buffer to just one message
    socket.setsockopt(zmq.CONFLATE, 1) # value = 1 -> This option tells ZMQ to only deliver the most recent message and discard older ones
    socket.setsockopt(zmq.RCVBUF, hwm * image_size[0] * image_size[1] * np.dtype(dt).itemsize)
    socket.connect(zmq_endpoint)
    logging.info(f"Worker connected to ZMQ endpoint: {zmq_endpoint}")
    socket.setsockopt(zmq.SUBSCRIBE, b"")

    while True:
        try:
            command = input_queue.get()  # Blocking call for a new command.
        except Exception as e:
            logging.error("Worker: error retrieving command: %s", e)
            break

        if command is None:
            logging.info("Worker: termination signal received. Exiting loop.")
            break

        if isinstance(command, dict) and command.get("cmd") == "CAPTURE_AND_FIT":
            # Expect ROI parameters as a dictionary: {'pos': [x, y], 'size': [w, h]}
            roi_data = command.get("roi")
            if not roi_data:
                logging.error("Worker: missing ROI data in command.")
                output_queue.put(None)
                continue
            try:
                # Read a fresh frame from the ZMQ stream.
                msg = socket.recv()  # Will block up to timeout_ms
                try:
                    msg = cbor2.loads(msg, tag_hook=tag_hook)
                    # Extract the image array.
                    if msg['type'] == "image":
                        raw_data = msg['data']['default']
                        min_int32 = np.iinfo(np.int32).min
                        max_int32 = np.iinfo(np.int32).max
                        mask = (raw_data == min_int32) | (raw_data == max_int32)
                        image = raw_data.astype(dt).reshape(globals.nrow, globals.ncol)
                        image[mask] = np.nan
                        logging.info(datetime.now().strftime("FRAME CAPTURED AND MASKED @ %H:%M:%S.%f")[:-3])
                    else:
                        output_queue.put(None)
                        continue
                except Exception as decode_e:
                    logging.error("Worker: error decoding frame: %s", decode_e)
                    output_queue.put(None)
                    continue

                # Convert ROI parameters to a tuple for fitting.
                # Here, roi_data is assumed to be a dict: {"pos": [x, y], "size": [w, h]}
                roiPos = tuple(roi_data["pos"])
                roiSize = tuple(roi_data["size"])
                roi_coord = create_roi_coord_tuple(roiPos, roiSize)

                logging.info(datetime.now().strftime("WORKER START FITTING @ %H:%M:%S.%f")[:-3])
                fit_result = fit_2d_gaussian_roi_NaN_fast(image, roi_coord, function=super_gaussian2d_rotated)
                logging.info(datetime.now().strftime("WORKER END FITTING @ %H:%M:%S.%f")[:-3])
                output_queue.put(fit_result.best_values)
                logging.info(datetime.now().strftime(f"Task processed. Output queue empty? {output_queue.empty()} @ %H:%M:%S.%f")[:-3])
            except zmq.error.Again as e:
                logging.error("Worker: zmq timeout/error: %s", e)
                output_queue.put(None)
            except Exception as e:
                logging.error("Worker: error during capture and fit: %s", e)
                output_queue.put(None)
        else:
            logging.warning("Worker: unknown command received: %s", command)
    # Cleanup the ZMQ socket and context.
    socket.close()
    context.term()
    logging.info("Worker process terminated.")

class GaussianFitterMP(QObject):
    finished = Signal(object)

    def __init__(self):
        super(GaussianFitterMP, self).__init__()
        self.task_name = "GaussianFitterMP"
        self.input_queue = mp.Queue()
        self.output_queue = mp.Queue()
        self.fitting_process = None 
        # (Option B) ZMQ Parameters 
        self.zmq_endpoint = globals.stream
        self.timeout_ms = 100
        self.hwm = 1 #2
        self.image_size = (globals.nrow, globals.ncol)
        self.dt = globals.dtype

    """
    # Option A
    def start(self):
        logging.info("Starting Gaussian Fitting!")
        if self.fitting_process is None or not self.fitting_process.is_alive():
            self.fitting_process = mp.Process(target=_fitGaussian, args=(self.input_queue, self.output_queue))
            self.fitting_process.start()
 
    def updateParams(self, image, roi):
        logging.debug("Updating parameters in the processing Queue...")
        roiPos = (roi.pos().x(), roi.pos().y())
        roiSize = (roi.size().x(), roi.size().y())
        self.input_queue.put((image, roiPos, roiSize))
        logging.info(datetime.now().strftime(" UPDATED FITTER @ %H:%M:%S.%f")[:-3]) 
    """

    # Option B
    def start(self):
        logging.info("Starting Gaussian Fitting process (capture & fit)...")
        if self.fitting_process is None or not self.fitting_process.is_alive():
            self.fitting_process = mp.Process(
                target=_capture_and_fit_worker,
                args=(self.input_queue,
                      self.output_queue,
                      self.zmq_endpoint,
                      self.timeout_ms,
                      self.hwm,
                      self.image_size,
                      self.dt)
            )
            self.fitting_process.start()

    def trigger_capture(self, roi):
        '''
        Instead of passing an image, we simply send a command (with ROI parameters)
        to trigger a capture and fitting in the worker process.
        `roi` should be a dict with keys "pos" and "size", e.g.:
             {"pos": [x, y], "size": [w, h]}
        '''
        logging.debug("Triggering capture and fit with ROI: %s", roi)
        self.input_queue.put({"cmd": "CAPTURE_AND_FIT", "roi": roi})
        logging.info(datetime.now().strftime("TRIGGERED FITTER @ %H:%M:%S.%f")[:-3])

    def fetch_result(self):
        try:
            return self.output_queue.get(timeout=2.0)
        except Empty:
            logging.info(datetime.now().strftime(" FETCH RESULT is None @ %H:%M:%S.%f")[:-3])
            return None

    def stop(self):
        logging.debug("Stopping Gaussian Fitting Process")
        if self.fitting_process is not None:
            try:
                # Signal termination
                self.input_queue.put(None)  # Send sentinel value to signal the process to exit
            except Exception as e:
                logging.error("Error sending termination signal: %s", e)

            # Wait for the process to finish with a timeout.
            self.fitting_process.join(timeout=5)
            if self.fitting_process.is_alive():
                logging.warning("Fitting process did not terminate gracefully. Forcing termination.")
                self.fitting_process.terminate()
                self.fitting_process.join()

            self.fitting_process = None

        # Optionally, drain any remaining tasks in the queues:
        def drain_queue(q):
            while not q.empty():
                try:
                    q.get_nowait()
                except Exception:
                    break

        drain_queue(self.input_queue)
        drain_queue(self.output_queue)

        try:
            logging.info("Closing queues and joining ")
            self.input_queue.close()
            self.output_queue.close()
            self.input_queue.cancel_join_thread()
            self.output_queue.cancel_join_thread()
        except Exception as e:
            logging.error("Error cleaning up queues: %s", e)

        logging.info("Asynchronous Gaussian Fitting Process Stopped")

    def __str__(self) -> str:
        return "GaussianFitterMP"