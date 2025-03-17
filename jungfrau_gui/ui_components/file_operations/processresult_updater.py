import zmq
import json
import os
import logging
from datetime import datetime
import argparse
from pathlib import Path
# from .. import globals
from PySide6.QtCore import Signal, Slot, QObject
import time

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
    finished = Signal()

    def __init__(self, parent, host, port=3463, verbose = True, mode=0):
        super().__init__()
        self.task_name = "Processed Data Receiver"
        self.parent = parent
        self.host = host
        self.port = port
        self.verbose = verbose
        if self.verbose:
            print(f"ProcessedDataReceiver:endpoint: {self.host}:{self.port}")
        self.trial = 0
        self.mode = mode

    def _now(self):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def stop(self):
        self.trial = 0
        logging.info("Stopping receiver...")

    @Slot()
    def run(self, timeout_ms = 5000, update_interval_ms=2000, n_retry=10, verbose = True):
        context = zmq.Context()
        socket = context.socket(zmq.REQ)
        socket.setsockopt(zmq.SNDTIMEO, timeout_ms)
        socket.setsockopt(zmq.RCVTIMEO, timeout_ms)
        socket.setsockopt(zmq.LINGER, 0)
        socket.connect(f"tcp://{self.host}:{self.port}")
        self.trial = n_retry

        if self.mode == 0:
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
                        logging.info("Lattice parameters: " + " ".join(map(str, result["lattice"])))
                        self.parent.tem_controls.tem_action.trigger_updateitem.emit(result)
                        # self.parent.file_operations.add_results_in_table.emit(result)
                        break
                except zmq.ZMQError as e:
                    logging.error(f"Failed to receive processed data request: {e}")
                    time.sleep(update_interval_ms/1000)
                    self.trial -= 1
                # finally:
                #     # ensure the socket is closed no matter what
        elif self.mode == 1: # load position list
            try:
                search_path = self.parent.visualization_panel.full_fname.text()
                socket.send_string(f"Session-metadata being inquired...: {search_path}")
                result_json = socket.recv_string()
                if 'not found' in result_json:
                    logging.warning(f'No data found around {search_path}')
                else:
                    # logging.warning(json.loads(result_json))
                    for d in json.loads(result_json):
                        if 'filename' in d: continue
                        self.parent.tem_controls.tem_action.trigger_updateitem.emit(d)
                    logging.info('Succeeded in loading session-metadata')
            except zmq.ZMQError as e:
                logging.error(f"Failed to receive session-metadata request: {e}")
        elif self.mode == 2: # send position list
            try:
                list_to_send = self.parent.tem_controls.tem_action.xtallist[1:]
                list_to_send.append({'filename': self.parent.visualization_panel.full_fname.text()})
                filtered_list = [{k: v for k, v in d.items() if k not in {'gui_marker', 'gui_label'} and v not in ['recorded', 'processed']} for d in list_to_send]
                # logging.info(filtered_list)
                message_json = json.dumps(filtered_list)
                socket.send_string(message_json)
                response = socket.recv_string()
                if self.verbose:
                    print(f'[dark_orange3]{self._now()} - REP: {response}[/dark_orange3]')
            except zmq.ZMQError as e:
                logging.error(f"Failed to send position list to server: {e}")
        socket.close()
        context.destroy()                
        self.finished.emit()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-H', '--host', type=str, default="localhost", help="Host address")
    parser.add_argument('-pt', '--port', type=int, default=3463, help="Port to bind to")

    args = parser.parse_args()

    receiver = ProcessedDataReceiver(host=args.host, port=args.port)
    receiver.run(timeout_ms=2000, update_interval_ms=500, n_retry=3)