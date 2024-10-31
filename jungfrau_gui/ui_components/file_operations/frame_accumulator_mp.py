import zmq
import logging
import numpy as np
import multiprocessing as mp

from ... import globals
# from reuss import io
import tifffile

import time

import cbor2
from ...decoder import tag_hook

class FrameAccumulator:
    def __init__(self, endpoint, dtype, image_size, nframes, fname):
        # Messages formatting
        format = "%(message)s"
        logging.basicConfig(format=format, level=logging.INFO)
        # Socket properties
        self.endpoint = endpoint
        self.timeout_ms = 10
        self.buffer_size_in_frames = 2 
        self.dt = dtype
        self.image_size = image_size
        self.nframes_to_add = nframes
        self.acc_image = np.zeros(self.image_size, dtype=self.dt)
        self.fname = fname
        self.finish_event = mp.Event()  # Event to signal completion
        self.error_queue = mp.Queue()   # Queue to report errors
        self.timeout_duration = 5  # Allowable timeout duration in seconds

    def start(self):
        self.accumulate_process = mp.Process(target=self._accumulate, args=(self.error_queue,))
        self.accumulate_process.start()

    def _accumulate(self, error_queue):
        try:
            logging.info("Starting accumulation process" )

            context = zmq.Context()
            socket = context.socket(zmq.SUB)
            socket.setsockopt(zmq.RCVTIMEO, self.timeout_ms)
            socket.setsockopt(zmq.RCVHWM, self.buffer_size_in_frames)
            socket.setsockopt(zmq.RCVBUF, self.buffer_size_in_frames*1024**2*np.dtype(self.dt).itemsize)
            socket.connect(self.endpoint)
            logging.debug(f"Connected to: {self.endpoint}")
            socket.setsockopt(zmq.SUBSCRIBE, b"")
            logging.info(f'{self.nframes_to_add} frames to add')

            last_received_time = time.time()  # Track the last received frame time
        
            # Frame accumulation loop
            while self.nframes_to_add > 0:
                try:
                    if globals.jfj:
                        msg = socket.recv()
                        msg = cbor2.loads(msg, tag_hook=tag_hook)
                        print(f"Decoded data type: {msg['data']['default'].dtype}") # decoded as int32
                        print(f"Sample of data : {msg['data']['default'][:10]}")
                        image = msg['data']['default'].reshape(self.image_size)
                        frame_nr = None
                    else:
                        msgs = socket.recv_multipart() #receiver.get_frame()
                        frame_nr = np.frombuffer(msgs[0], dtype=np.int64)[0]
                        logging.info(f"Adding frame #{frame_nr}")
                        image = np.frombuffer(msgs[1], dtype=self.dt).reshape(globals.nrow, globals.ncol)
                    
                    if image is not None:
                        tmp = np.copy(image)
                        self.acc_image += tmp
                        self.nframes_to_add -= 1
                        last_received_time = time.time()  # Reset the timer on successful frame receipt

                except zmq.error.Again:
                    # Log and check if timeout duration has been exceeded
                    logging.debug(f"No frame received, continuing to wait...")
                    if time.time() - last_received_time > self.timeout_duration:
                        logging.warning(f"No frames received for {self.timeout_duration} seconds. Exiting.")
                        break  # Exit the loop after the timeout duration has been exceeded

            # Save the accumulated image if frames were received
            if self.nframes_to_add == 0:
                try:
                    # TODO Convert to int32 before or after summing? [here conv after accumulation]
                    # data = np.rint(self.acc_image).astype(globals.file_dt)
                    print(f"Type of accumulated frame is {self.acc_image.dtype}")
                    self.save_captures(self.fname, self.acc_image.copy())
                    logging.info(f'TIFF file ready!')  # Log only if save was successful
                except Exception as e:
                    logging.error(f"Error saving TIFF file: {e}")
                    error_queue.put(e)  # Send the error back to the main process

            socket.close()

        except Exception as e:
            # Pass the error message back to the main process via the error queue
            logging.error(f"Error occurred: {e}")
            error_queue.put(e)

    def save_captures(self, fname, data):
        logging.info(f'Saving: {fname}')
        tifffile.imwrite(fname, data.astype(globals.file_dt))
