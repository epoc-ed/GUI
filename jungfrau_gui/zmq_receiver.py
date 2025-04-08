import zmq
import time
import logging
import numpy as np
from . import globals
import cbor2
from .decoder import tag_hook


# Receiver of the ZMQ stream
class ZmqReceiver:
    def __init__(self, endpoint, 
                 timeout_ms = 10, 
                 dtype = np.float32,
                 hwm = 2):
        self.endpoint = endpoint
        self.timeout_ms = timeout_ms
        self.dt = dtype
        self.hwm = hwm
        self.context = zmq.Context()
        self.socket = None
        self.setup_socket()

    def setup_socket(self):
        """Setup or reset the ZMQ socket."""
        if self.socket is not None:
            self.socket.close()
        self.socket = self.context.socket(zmq.SUB)
        self.socket.setsockopt(zmq.RCVTIMEO, self.timeout_ms)
        self.socket.setsockopt(zmq.RCVHWM, self.hwm)
        self.socket.setsockopt(zmq.RCVBUF, self.hwm * 1024 * 1024 * np.dtype(self.dt).itemsize)
        self.socket.connect(self.endpoint)
        self.socket.setsockopt(zmq.SUBSCRIBE, b"")

    def log_first_success(func):
        def wrapper(self, *args, **kwargs):
            if not hasattr(self, 'first_success_logged'):
                result = func(self, *args, **kwargs)
                if result:
                    if result[0] is not None:
                        logging.info("Connection successful!")
                        self.first_success_logged = True
                    return result
            return func(self, *args, **kwargs)
        return wrapper
            
    @log_first_success
    def get_frame_jfj(self):
        if not globals.exit_flag.value:
            try:
                msg = self.socket.recv()
                msg = cbor2.loads(msg, tag_hook=tag_hook)
                logging.debug(f"*********** message type is: {msg['type']} **************")
                if msg['type'] == "start":
                    # Process and log the header message
                    logging.debug(f"Received header: {msg}")
                    return None, None
                elif msg['type'] == "image": 
                    # Process data messages   
                    logging.debug(f"Got: {msg['series_id']}:{[msg['image_id']]}")
                    raw_data = msg['data']['default']
                    frame_nr = msg['image_id']
                    
                    # Identify invalid values (min_int32)
                    min_int32 = np.iinfo(np.int32).min
                    mask = (raw_data == min_int32)

                    image = raw_data.astype(self.dt).reshape(globals.nrow, globals.ncol)
                    
                    #Replace invalid values with np.nan
                    image[mask] = np.nan
                    
                    return image, frame_nr
                elif msg['type'] == "end":
                    logging.debug(f"Received End message: {msg}")
                    return None, None
                else:
                    logging.warning(f"Unindentified message type: {msg['type']}")
                    return None, None
            except zmq.error.Again:
                # self.reconnect()
                return None, None
            except Exception as e:
                logging.error(f"An unexpected error occurred: {e}")
                return None, None

    def reconnect(self):
        """Attempt to reconnect to the server."""
        max_retries = 1
        for attempt in range(max_retries):
            try:
                logging.debug(f"Attempting to reconnect ({attempt+1}/{max_retries})...")
                self.setup_socket()
                # Test the connection by attempting to receive a message
                test_msg = self.socket.recv(flags=zmq.NOBLOCK)
                logging.info("Reconnection successful !")
                return
            except zmq.ZMQError as e:
                logging.debug(f"Failed to reconnect due to a ZeroMQ error: {e}\nTrying again...")
                time.sleep(0.1)
        logging.info("Failed to reconnect after several attempts.")

if __name__ == "__main__":
    receiver = ZmqReceiver("tcp://noether:5501")
    frame, frame_nr = receiver.get_frame_jfj()
    if frame is not None:
        print("Frame received:", frame_nr)
