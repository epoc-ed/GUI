import zmq
import logging
import numpy as np
import multiprocessing as mp

from ... import globals
# from reuss import io
import tifffile

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

    def start(self):
        self.accumulate_process = mp.Process(target=self._accumulate, args=[])
        self.accumulate_process.start()
        # self.accumulate_process.join()

    def _accumulate(self):
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
    
        while self.nframes_to_add>0:
            try:
                msgs = socket.recv_multipart() #receiver.get_frame()  
                frame_nr = np.frombuffer(msgs[0], dtype = np.int64)[0] 
                print(f"Adding frame #{frame_nr}")               
                image = np.frombuffer(msgs[1], dtype=self.dt).reshape(globals.nrow, globals.ncol)
                if image is not None:   
                    tmp = np.copy(image)
                    self.acc_image += tmp
                    self.nframes_to_add -= 1
                    # time.sleep(0.1)
            except zmq.error.Again:
                pass
                # print('Error of Connection')
        
        self.save_captures(self.fname, self.acc_image.copy())
        socket.close()
        logging.info(f'TIFF file ready!')
        
    def save_captures(self, fname, data):
        logging.info(f'Saving: {fname}')
        # io.save_tiff(fname, data)
        tifffile.imwrite(fname, data.astype(np.int32))
