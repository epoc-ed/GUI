import zmq
import numpy as np

# Receiver of the ZMQ stream
class ZmqReceiver:
    def __init__(self, endpoint, 
                 timeout_ms = 100, 
                 dtype = np.float32,
                 hwm = 2):

        self.dt = dtype
        self.hwm = hwm
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.SUB)
        self.socket.setsockopt(zmq.RCVTIMEO, timeout_ms)
        self.socket.setsockopt(zmq.RCVHWM, self.hwm)
        self.socket.setsockopt(zmq.RCVBUF, self.hwm*1024*1024*np.dtype(self.dt).itemsize)
        self.socket.connect(endpoint)
        self.socket.setsockopt(zmq.SUBSCRIBE, b"")

    def get_frame(self):
        msgs = self.socket.recv_multipart() # len(msgs): 8 1048576
        frame_nr = np.frombuffer(msgs[0], dtype = np.int64)[0]
        image = np.frombuffer(msgs[1], dtype = np.float16).reshape(512, 1024)
        return image, frame_nr
