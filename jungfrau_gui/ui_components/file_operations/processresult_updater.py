import zmq
import json
import os
import logging
from datetime import datetime
import argparse
from pathlib import Path
from PySide6.QtCore import Signal, Slot, QObject
import time

class DataProcessingManager(QObject):
    finished = Signal()

    # def __init__(self, parent, host='noether', port=3467, verbose = True, mode=1):
    def __init__(self, parent, host='gauss', port=3467, verbose = True, mode=1):
        super().__init__()
        self.task_name = "Processing Launcher/Receiver"
        self.parent = parent # TEMAction
        self.host = host
        self.port = port
        self.verbose = verbose
        if self.verbose:
            print(f"Processing Launcher/Receiver:endpoint: {self.host}:{self.port}")
        self.trial = 0
        self.mode = mode

    def _now(self):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def stop(self):
        self.trial = 0
        logging.info("Stopping processing client...")

    @Slot()
    def run(self, timeout_ms = 5000, update_interval_ms=2000, n_retry=10, verbose = True):
        context = zmq.Context()
        socket = context.socket(zmq.REQ)
        socket.setsockopt(zmq.SNDTIMEO, timeout_ms)
        socket.setsockopt(zmq.RCVTIMEO, timeout_ms)
        socket.setsockopt(zmq.LINGER, 0)
        socket.connect(f"tcp://{self.host}:{self.port}")
        self.trial = n_retry

        if self.mode == 0: # emit postprocessing
            try:
                file_path = self.parent.visualization_panel.prev_fpath
                # gui_id = self.parent.tem_controls.tem_action.contol.tem_status["gui_id"]
                gui_id = self.parent.control.tem_status["gui_id"]
                socket.send_string(f"Launching the postprocess...: {file_path} as {gui_id}")
                result_json = socket.recv_string()
                response = socket.recv_string()
                if self.verbose:
                    print(f'[dark_orange3]{self._now()} - REP: {response}[/dark_orange3]')
            except zmq.ZMQError as e:
                logging.error(f"Failed to launch processing on server: {e}")
        elif self.mode == 1: # receive postprocess-result
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
                        # self.parent.tem_controls.tem_action.trigger_updateitem.emit(result)
                        self.parent.trigger_updateitem.emit(result)
                        # self.parent.file_operations.add_results_in_table.emit(result)
                        break
                except zmq.ZMQError as e:
                    logging.error(f"Failed to receive processed data request: {e}")
                    time.sleep(update_interval_ms/1000)
                    self.trial -= 1
                # finally:
                #     # ensure the socket is closed no matter what
        elif self.mode == 2: # load position list
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
                        # self.parent.tem_controls.tem_action.trigger_updateitem.emit(d)
                        self.parent.trigger_updateitem.emit(d)
                    logging.info('Succeeded in loading session-metadata')
            except zmq.ZMQError as e:
                logging.error(f"Failed to receive session-metadata request: {e}")
        elif self.mode == 3: # send position list
            try:
                # list_to_send = self.parent.tem_controls.tem_action.xtallist[1:]
                list_to_send = self.parent.xtallist[1:]
                list_to_send.append({'filename': self.parent.visualization_panel.full_fname.text()})
                filtered_list = [{k: v for k, v in d.items() if k not in {'gui_marker', 'gui_label'}} for d in list_to_send]
                filtered_list = [item for item in filtered_list if not item.get('status') in ['recorded', 'processed']]
                logging.debug(filtered_list)
                message_json = json.dumps(filtered_list)
                socket.send_string(message_json)
                response = socket.recv_string()
                if self.verbose:
                    print(f'[dark_orange3]{self._now()} - REP: {response}[/dark_orange3]')
            except zmq.ZMQError as e:
                logging.error(f"Failed to send position list to server: {e}")
        # elif self.mode == 4: # emit re-processing with user-defined parameters
        #     try:
        #         list_of_dataid = self.parent.xtallist[1:]
        #         filtered_list = list_of_dataid # something filtering, e.g. by status, spots, etc.
        #         # logging.info(filtered_list)
        #         filtered_list.append(
        #             {'cell': self.parent.visualization_panel.full_fname.text(),
        #              'spacegroup': self.parent.visualization_panel.full_fname.text()})
        #         message_json = json.dumps(filtered_list)
        #         socket.send_string(message_json)
        #         response = socket.recv_string()
        #         if self.verbose:
        #             print(f'[dark_orange3]{self._now()} - REP: {response}[/dark_orange3]')
        #     except zmq.ZMQError as e:
        #         logging.error(f"Failed to launch re-processing on server: {e}")
        socket.close()
        context.destroy()                
        self.finished.emit()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-H', '--host', type=str, default="localhost", help="Host address")
    parser.add_argument('-pt', '--port', type=int, default=3467, help="Port to bind to")

    args = parser.parse_args()

    receiver = DataProcessingManager(host=args.host, port=args.port)
    receiver.run(timeout_ms=2000, update_interval_ms=500, n_retry=3)