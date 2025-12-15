import zmq
import json
import os
import logging
from datetime import datetime
import argparse
from PySide6.QtCore import Signal, Slot, QObject
import time
import pickle
import zlib
import base64
import numpy as np
from ... import globals

def decompress_image(compressed: bytes) -> np.ndarray:
    pickled = zlib.decompress(compressed)
    img = pickle.loads(pickled)
    return img

class DataProcessingManager(QObject):
    finished = Signal()

    def __init__(self, parent, host=globals.processserver_host, port=globals.processserver_port, verbose = True, mode=1, gui_running=False):
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
        self.gui_running = gui_running

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
        self.skipframes = globals.skipframes_spotplotter # use when reloading spots

        if self.mode == 0: # emit postprocessing
            try:
                file_path = self.parent.visualization_panel.prev_fpath
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
                        time.sleep(update_interval_ms/globals.S_TO_MS)
                        self.trial -= 1
                    else:
                        result = json.loads(result_json)
                        logging.info("Succeeded in receiving processed data request.")
                        logging.info("Lattice parameters: " + " ".join(map(str, result["lattice"])))
                        self.parent.trigger_updateitem.emit(result)
                        break
                except zmq.ZMQError as e:
                    logging.error(f"Failed to receive processed data request: {e}")
                    time.sleep(update_interval_ms/globals.S_TO_MS)
                    self.trial -= 1
                # finally:
                #     # ensure the socket is closed no matter what
        elif self.mode == 2: # load position list
            try:
                socket.send_string(f"Session-metadata being inquired... (Run-status: {self.gui_running})")
                result_json = socket.recv_string()
                if 'not found' in result_json:
                    logging.warning(f'No session data found!')
                else:
                    self.parent.postprocess_controls.ccdclist = [item for item in json.loads(result_json) if 'ccdc_id' in item]
                    for d in json.loads(result_json):
                        if 'image_supporting' in d:
                            try:
                                decompressed = zlib.decompress(base64.b64decode(d['image_supporting']))
                                images_received = pickle.loads(decompressed)
                                images_supporting = [decompress_image(img) for img in images_received]
                                for i in images_supporting:
                                    if i.shape[0] == 9600:
                                        self.parent.tem_stagectrl.lowmagimage = i
                                        logging.info('Reloaded atlas image')
                                    elif i.shape[0] == 1064:
                                        self.parent.parent.imageItem.setImage(i)
                                        logging.info('Reloaded the image previously taken')
                                    else:
                                        self.parent.tem_stagectrl.grayimage = i
                                        logging.info('Reloaded resolution-atlas image')
                                continue
                            except TypeError:
                                logging.warning('Failed to reload previous map-atlas(es)...')
                                break
                        if 'filename' in d: continue
                        if not 'ccdc_id' in d:
                            self.parent.trigger_updateitem.emit(d)
                        if self.parent.postprocess_controls.ccdc_checkbox.isChecked():
                            self.parent.postprocess_controls.update_ccdcinfo_signal.emit()
                    logging.info('Succeeded in loading session-metadata')
            except zmq.ZMQError as e:
                logging.error(f"Failed to receive session-metadata request: {e}")
        elif self.mode == 3: # send position list
            try:
                list_to_send = self.parent.xtallist[1:]
                list_to_send.append({'filename': self.parent.visualization_panel.full_fname.text()})
                filtered_list = [{k: v for k, v in d.items() if k not in {'gui_marker', 'gui_label'}} for d in list_to_send]
                filtered_list = [item for item in filtered_list if not item.get('status') in ['recorded', 'processed', 'refined']]
                logging.debug(filtered_list)
                message_json = json.dumps(filtered_list)
                socket.send_string(message_json)
                response = socket.recv_string()
                if self.verbose:
                    print(f'[dark_orange3]{self._now()} - REP: {response}[/dark_orange3]')
            except zmq.ZMQError as e:
                logging.error(f"Failed to send position list to server: {e}")
        elif self.mode == 4: # emit re-processing with user-defined parameters
            try:
                filtered_list = [item for item in self.parent.xtallist if item.get('reprocess') in ['checked']]
                list_sent = [item["dataid"] for item in filtered_list]
                list_dict = {'dataids': list_sent,
                     'cell': self.parent.cell_input.text().split(),
                     'spacegroup': self.parent.sg_input.value(),
                     'xds': self.parent.xds_checkbox.isChecked(),
                     'dials': self.parent.dials_checkbox.isChecked()}
                logging.debug(list_dict)
                message_json = json.dumps(list_dict)
                socket.send_string(message_json)
                response = socket.recv_string()
                if self.verbose:
                    print(f'[dark_orange3]{self._now()} - REP: {response}[/dark_orange3]')
            except zmq.ZMQError as e:
                logging.error(f"Failed to launch re-processing on server: {e}")
        elif self.mode == 5: # emit merging and then phasing if the quility looks sufficient
            try:
                filtered_list = [item for item in self.parent.xtallist if item.get('reprocess') in ['checked']]
                list_sent = [item["dataid"] for item in filtered_list]
                list_dict = {'dataids': list_sent,
                     'cell': self.parent.cell_input.text().split(),
                     'spacegroup': self.parent.sg_input.value(),
                     'xds': self.parent.xds_checkbox.isChecked(),
                     'dials': self.parent.dials_checkbox.isChecked(),
                     'formula': self.parent.formula_input.text(),
                }
                logging.debug(list_dict)
                message_json = json.dumps(list_dict)
                socket.send_string(message_json)
                response = socket.recv_string()
                if self.verbose:
                    print(f'[dark_orange3]{self._now()} - REP: {response}[/dark_orange3]')
            except zmq.ZMQError as e:
                logging.error(f"Failed to launch merge-and-solve on server: {e}")
        elif self.mode == 6: # emit reloading spots from the saved data with determied xtal orientation
            try:
                filtered_list = [item for item in self.parent.xtallist if item.get('reprocess') in ['checked']]
                list_dict = {'dataids': [item["dataid"] for item in filtered_list],
                             'nskip': self.skipframes}
                message_json = json.dumps(list_dict)
                socket.send_string(message_json)
                response = socket.recv_string()
                self.parent.savedspots = json.loads(response)
                if self.verbose:
                    print(f'[dark_orange3]{self._now()} - REP: {response}[/dark_orange3]')
            except zmq.ZMQError as e:
                logging.error(f"Failed to receive spots' data over server: {e}")
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
