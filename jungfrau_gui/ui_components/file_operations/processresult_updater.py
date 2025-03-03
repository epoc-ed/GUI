import zmq
from rich import print
import json
import sys
import os
import logging
# import numpy as np
from datetime import datetime
import argparse
from pathlib import Path
# from .. import globals
from PySide6.QtCore import Signal, Slot, QObject
import time

# Handle imports correctly when running as a standalone script
if __name__ == "__main__" and __package__ is None:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.abspath(os.path.join(current_dir, os.pardir, os.pardir))
    sys.path.insert(0, parent_dir)

# Absolute import to work in both cases: as a module and as a standalone script
# from jungfrau_gui.ui_components.tem_controls.toolbox import config as cfg_jf

# class CustomJSONEncoder(json.JSONEncoder):
#     def default(self, obj):
#         if isinstance(obj, (np.integer, np.int64)):
#             return int(obj)
#         elif isinstance(obj, (np.floating, np.float32)):
#             return float(obj)
#         elif isinstance(obj, np.ndarray):
#             return obj.tolist()
#         # Add more types as needed
#         return super().default(obj)

class ProcessedDataReceiver(QObject):
    launch_receiver_signal = Signal()

    def __init__(self, host, port=3463, verbose = True):
        super().__init__()
        self.host = host
        self.port = port
        self.verbose = verbose
        if self.verbose:
            print(f"ProcessedDataReceiver:endpoint: {self.host}:{self.port}")
        self.trial = 0
        self.launch_receiver_signal.connect(lambda: self.receive_processed_data())

    def _now(self):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def stop(self):
        self.trial = 0
        logging.info("Stopping receiver...")

    @Slot()
    def receive_processed_data(self, timeout_ms = 5000, update_interval_ms=2000, n_retry=10):
        context = zmq.Context()
        socket = context.socket(zmq.REQ)
        socket.setsockopt(zmq.SNDTIMEO, timeout_ms)
        socket.setsockopt(zmq.RCVTIMEO, timeout_ms)
        socket.setsockopt(zmq.LINGER, 0)
        socket.connect(f"tcp://{self.host}:{self.port}")
        self.trial = n_retry

        while self.trial > 0:
            try:
                socket.send_string("Results being inquired...")
                result_json = socket.recv_string()
                if 'In processing...' in result_json:
                    time.sleep(update_interval_ms/1000)
                    self.trial -= 1
                else:
                    result = json.loads(result_json)
                    logging.info("Succeeded in receiving processed data request.")
                    logging.warning(result['lattice']) ## debug line
                    break
            except zmq.ZMQError as e:
                logging.error(f"Failed to receive processed data request: {e}")
                time.sleep(update_interval_ms/1000)
                self.trial -= 1

if __name__ == "__main__":
    from epoc import ConfigurationClient, auth_token, redis_host

    cfg = ConfigurationClient(redis_host(), token=auth_token())

    parser = argparse.ArgumentParser()
    # parser.add_argument('-fp', '--filepath', type=Path, help="Path to the saved hdf5 file")
    parser.add_argument('-H', '--host', type=str, default="localhost", help="Host address")
    parser.add_argument('-pt', '--port', type=int, default=3463, help="Port to bind to")

    args = parser.parse_args()

    # if args.filepath.suffix != ".h5":
    #     raise ValueError(f"Unknown file format: {args.filepath.suffix}")

    receiver = ProcessedDataReceiver(host=args.host, port=args.port)
    receiver.receive_processed_data(timeout_ms=2000, update_interval_ms=500, n_retry=3)