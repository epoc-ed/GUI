import zmq
import ctypes
import logging
import numpy as np
from pathlib import Path
import multiprocessing as mp

from .hdf5_file import Hdf5File
from ... import globals

class StreamWriter:
    def __init__(self, filename, endpoint, mode='w', image_size = (512,1024), dtype = np.float32, pixel_mask = None, fformat = 'h5'):
        self.timeout_ms = 100
        self.buffer_size_in_frames = 10
        self.endpoint = endpoint
        self.dt = dtype
        self.filename = Path(filename)
        self.image_size = image_size

        self.mode = mode
        self.fformat = fformat
        self.pixel_mask = pixel_mask

        
        self.stop_requested = mp.Value(ctypes.c_bool)
        self.stop_requested.value = False

        self.first_frame_number = mp.Value(ctypes.c_int64)
        self.first_frame_number.value = -1

        self.last_frame_number = mp.Value(ctypes.c_int64)
        self.last_frame_number.value = -1

        logging.info(f"Writing data as {self.dt}")

    @property
    def number_frames_witten(self):
        #TODO! Read summing value from ConfigurationClient
        return int((self.last_frame_number.value - self.first_frame_number.value)/100 +1)

    def start(self):
        self.write_process = mp.Process(target=self._write, args=[])
        self.write_process.start()

    def stop(self):
        logging.info("Stopping write process")
        self.stop_requested.value = True
        self.write_process.join()


    def _write(self):
        logging.info("Starting write process" )
        if self.fformat in ['h5','hdf5', 'hdf']:
            f = Hdf5File(self.filename, self.mode, self.image_size, self.dt, self.pixel_mask)
        else:
            raise ValueError(f"Unknown file format: {self.fformat}")

        context = zmq.Context()
        socket = context.socket(zmq.SUB)
        socket.setsockopt(zmq.RCVTIMEO, self.timeout_ms)
        socket.setsockopt(zmq.RCVHWM, self.buffer_size_in_frames)
        socket.setsockopt(zmq.RCVBUF, self.buffer_size_in_frames*1024**2*np.dtype(self.dt).itemsize)
        socket.connect(self.endpoint)
        logging.debug(f"Connected to: {self.endpoint}")
        socket.setsockopt(zmq.SUBSCRIBE, b"")

        while not self.stop_requested.value:
            try:
                msgs = socket.recv_multipart()
                frame_nr = np.frombuffer(msgs[0], dtype = np.int64)[0]
                if self.first_frame_number.value < 0:  # Set the first frame number if it's the first message
                    self.first_frame_number.value = frame_nr
                    logging.info(f"First written frame number is  {self.first_frame_number.value}")
                image = np.frombuffer(msgs[1], dtype = globals.stream_dt).reshape(self.image_size)
                converted_image = image.astype(globals.file_dt)
                f.write(converted_image, frame_nr)
                logging.debug("Hdf5 is being written...")
                self.last_frame_number.value = frame_nr
            except zmq.error.Again:
                pass
        
        f.add_nimages()
        f.close()