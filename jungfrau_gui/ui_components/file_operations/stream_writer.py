import zmq
import ctypes
import logging
import numpy as np
from pathlib import Path
import multiprocessing as mp

from .hdf5_file import Hdf5File
from ... import globals

import cbor2
from ...decoder import tag_hook

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

        self.number_frames_written_jfj = mp.Value(ctypes.c_int64)
        self.number_frames_written_jfj.value = 0

        logging.info(f"Writing data as {self.dt}")

    @property
    def number_frames_witten(self):
        #TODO! Read summing value from ConfigurationClient
        # if globals.jfj:
        return self.number_frames_written_jfj.value
        # return int((self.last_frame_number.value - self.first_frame_number.value) +1)

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
                # if globals.jfj:
                msg = socket.recv()
                msg = cbor2.loads(msg, tag_hook=tag_hook)
                image = msg['data']['default'].reshape(self.image_size) # int32
                frame_nr = msg['image_id']
                
                # Conversion of JFJ stream to int32 is redundant (but safe) 
                converted_image = image.astype(globals.file_dt)
                
                f.write(converted_image, frame_nr)

                # Count for JFJ writing (or read frame_nr from zmq stream)
                self.number_frames_written_jfj.value += 1 
                
                logging.debug("Hdf5 is being written...")
                self.last_frame_number.value = frame_nr
            except zmq.error.Again:
                pass
        
        f.add_nimages()
        f.close()
