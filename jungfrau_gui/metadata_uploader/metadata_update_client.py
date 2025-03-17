import zmq
from rich import print
import json
import sys
import os
import logging
import numpy as np
from datetime import datetime
import argparse
from pathlib import Path
from .. import globals

# Handle imports correctly when running as a standalone script
if __name__ == "__main__" and __package__ is None:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.abspath(os.path.join(current_dir, os.pardir, os.pardir))
    sys.path.insert(0, parent_dir)

# Absolute import to work in both cases: as a module and as a standalone script
from jungfrau_gui.ui_components.tem_controls.toolbox import config as cfg_jf

class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer, np.int64)):
            return int(obj)
        elif isinstance(obj, (np.floating, np.float32)):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        # Add more types as needed
        return super().default(obj)

class MetadataNotifier:
    def __init__(self, host, port=3463, verbose = True):
        self.host = host
        self.port = port
        self.verbose = verbose
        if self.verbose:
            print(f"MetadataNotifier:endpoint: {self.host}:{self.port}")

    def _now(self):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def notify_metadata_update(self, filename, tem_status, beam_property, rotations_angles, jf_threshold, jf_gui_tag = globals.tag, commit_hash = globals.commit, timeout_ms = 5000):
        
        context = zmq.Context()
        socket = context.socket(zmq.REQ)
        socket.setsockopt(zmq.SNDTIMEO, timeout_ms)
        socket.setsockopt(zmq.RCVTIMEO, timeout_ms)
        socket.setsockopt(zmq.LINGER, 0)
        socket.connect(f"tcp://{self.host}:{self.port}")

        detector_distance = cfg_jf.lut().interpolated_distance(tem_status['eos.GetMagValue_DIFF'][2], tem_status["ht.GetHtValue"]/1e3)
        aperture_size_cl = cfg_jf.lut().cl_size(tem_status['apt.GetSize(1)'])
        aperture_size_sa = cfg_jf.lut().sa_size(tem_status['apt.GetSize(1)'])
        tem_status['rotation_axis'] = cfg_jf.lut().rotaxis_for_ht(tem_status["ht.GetHtValue"])

        try:
            message = {
                "filename": filename.as_posix(),
                "tem_status": tem_status,
                "beam_property": beam_property,
                "rotations_angles": rotations_angles,
                "jf_threshold": jf_threshold,
                "detector_distance": detector_distance,
                "aperture_size_cl": aperture_size_cl,
                "aperture_size_sa": aperture_size_sa,
                "jf_gui_tag": jf_gui_tag,
                "commit_hash": commit_hash
            }
            message_json = json.dumps(message, cls=CustomJSONEncoder)
            if self.verbose:
                print(f'[spring_green4]{self._now()} - REQ: Update metadata in [light_green]{filename}[light_green]')
            socket.send_string(message_json)
            response = socket.recv_string()
            if self.verbose:
                print(f'[dark_orange3]{self._now()} - REP: {response}[/dark_orange3]')
        
        except zmq.ZMQError as e:
            logging.error(f"Failed to send metadata update request: {e}")
            raise

        finally:
            socket.disconnect(f"tcp://{self.host}:{self.port}")
            context.destroy()

if __name__ == "__main__":
    from epoc import ConfigurationClient, auth_token, redis_host

    cfg = ConfigurationClient(redis_host(), token=auth_token())

    parser = argparse.ArgumentParser()
    parser.add_argument('-fp', '--filepath', type=Path, help="Path to the saved hdf5 file")
    parser.add_argument('-H', '--host', type=str, default="localhost", help="Host address")
    parser.add_argument('-pt', '--port', type=int, default=3463, help="Port to bind to")

    args = parser.parse_args()

    if args.filepath.suffix != ".h5":
        raise ValueError(f"Unknown file format: {args.filepath.suffix}")

    # Load the dictionary from the exemplar file
    with open("tem_status_exemplar.txt", 'r') as file:
        tem_status = json.load(file)

    # beamcenter = cfg.beam_center # Read from Redis DB
    beam_property = {
        "center" : cfg.beam_center, 
        "sigma_width" : [-1, -1], 
        "illumination" : {"pa_per_cm2": 0, "e_per_A2_sample": 0},
    }

    # Example data for rotation at 10deg/s
    rotations_angles = [[0.0, 0.0], [1.0, 10.0], [2.0, 19.95], [3.0, 30.12], [4.0, 40.2],[5.0, 50.05],[6.0, 60.0]]
    
    jf_threshold = 5 
    #input("Enter to continue!")

    notifier = MetadataNotifier(host=args.host, port=args.port)
    # notifier.notify_metadata_update(args.filepath, tem_status, beamcenter, rotations_angles, jf_threshold)
    notifier.notify_metadata_update(args.filepath, tem_status, beam_property, rotations_angles, jf_threshold)