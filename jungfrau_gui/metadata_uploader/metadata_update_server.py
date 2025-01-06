import zmq
import h5py
import logging
import json
import time
import numpy as np
import threading
# from epoc import ConfigurationClient, auth_token, redis_host

class CustomFormatter(logging.Formatter):
    # Define color codes for different log levels and additional styles
    # Foreground (text) colors
    BLACK = "\033[30m"
    RED = "\033[31m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"

    # Text formatting
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    RESET = "\033[0m"
    
    # Define how each log level should be colored
    LOG_COLORS = {
        logging.DEBUG: BLACK,
        logging.INFO: BLUE,
        logging.WARNING: f"{YELLOW}{BOLD}",
        logging.ERROR: RED,
        logging.CRITICAL: f"{RED}{BOLD}",
    }

    def format(self, record):
        # Get the appropriate color for the log level
        level_color = self.LOG_COLORS.get(record.levelno, self.RESET)
        
        # Format the entire log message (timestamp + levelname + message)
        formatted_message = super().format(record)
        
        # Apply the color to the entire formatted message
        return f"{level_color}{formatted_message}{self.RESET}"

def eV2angstrom(voltage):
    h, m0, e, c = 6.62607004e-34, 9.10938356e-31, 1.6021766208e-19, 299792458.0
    return h/np.sqrt(2*m0*e*voltage*(1.+e*voltage/2./m0/c**2)) * 1.e10

class Hdf5MetadataUpdater:
    def __init__(self, port_number = 3463):
        self.port_number = port_number
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REP)
        self.socket.bind(f"tcp://*:{port_number}")
        # self.cfg = ConfigurationClient(redis_host(), token=auth_token())
        self.root_data_directory = "/data/epoc/storage/jem2100plus/" # jfjoch_test/ # self.cfg.base_data_dir.as_posix()

    def run(self):
        logging.info("Server started, waiting for metadata update requests...")
        while True:
            try:
                message_json = self.socket.recv_string()
                message = json.loads(message_json)
                filename = self.root_data_directory + message["filename"]
                tem_status = message["tem_status"]
                beamcenter = message["beamcenter"]
                rotations_angles = message["rotations_angles"]
                jf_threshold = message["jf_threshold"]
                detector_distance = message["detector_distance"]
                aperture_size_cl = message["aperture_size_cl"]
                aperture_size_sa = message["aperture_size_sa"]
                self.addinfo_to_hdf(filename, tem_status, beamcenter, detector_distance, aperture_size_cl, aperture_size_sa, rotations_angles, jf_threshold)
                self.socket.send_string("Metadata added successfully")
            except zmq.ZMQError as e:
                logging.error(f"Error while receiving request: {e}")
                self.socket.send_string("Error updating metadata")
    
    def stop(self):
        self.running = False
        logging.info("Stopping server...")

    def addinfo_to_hdf(self, filename, tem_status, beamcenter, detector_distance, aperture_size_cl, aperture_size_sa, rotations_angles, jf_threshold, pixel=0.075):
        detector_framerate = 2000 # Hz for Jungfrau
        ht = 200  # keV  # <- HT3
        wavelength = eV2angstrom(ht * 1e3)  # Angstrom
        stage_rates = [10.0, 2.0, 1.0, 0.5]
        jfj_version = "1.0.0-rc.24"
        del_rotations_angles = np.diff(np.array(rotations_angles, dtype='float').T)
        rotation_mean, rotation_std = np.mean(del_rotations_angles[1] / del_rotations_angles[0]), np.std(del_rotations_angles[1] / del_rotations_angles[0])
        try:
            with h5py.File(filename, 'a') as f:
                try:
                    def create_or_update_dataset(name, data, dtype=None):
                        if name in f:
                            del f[name]
                        f.create_dataset(name, data=data, dtype=dtype)
                    
                    # tagname mimicked from dectris HDF
                    create_or_update_dataset('entry/instrument/detector/detector_name', data = 'JUNGFRAU-1M FOR ED AT UNIVERSITY OF VIENNA')
                    create_or_update_dataset('entry/instrument/detector/beam_center_x', data = beamcenter[0], dtype='float') # <- FITTING
                    create_or_update_dataset('entry/instrument/detector/beam_center_y', data = beamcenter[1], dtype='float') # <- FITTING
                    create_or_update_dataset('entry/instrument/detector/detector_distance', data = detector_distance, dtype='uint64') # <- LUT
                    create_or_update_dataset('entry/instrument/detector/framerate', data = detector_framerate, dtype='uint64')
                    # create_or_update_dataset('entry/instrument/detector/virtual_pixel_correction_applied', data = 200, dtype='float') # =GAIN?
                    # create_or_update_dataset('entry/instrument/detector/detectorSpecific/data_collection_date_time', data = time.strftime("%Y/%m/%d %H:%M:%S", time.localtime())) <- sent with tem_update_times
                    create_or_update_dataset('entry/instrument/detector/detectorSpecific/element', data = 'Si')
                    # create_or_update_dataset('entry/instrument/detector/detectorSpecific/frame_count_time', data = data_shape[0], dtype='uint64')
                    # create_or_update_dataset('entry/instrument/detector/detectorSpecific/frame_period', data = data_shape[0], dtype='uint64') = frame_count_time in SINGLA
                    create_or_update_dataset('entry/instrument/detector/detectorSpecific/software_version', data = 'Jungfraujoch/' + jfj_version)
                    create_or_update_dataset('entry/instrument/detector/count_threshold_in_keV', data = jf_threshold, dtype='uint64')
                    # ED-specific, some namings from https://github.com/dials/dxtbx/blob/main/src/dxtbx/format/FormatNXmxED.py
                    create_or_update_dataset('entry/source/probe', data = 'electron')
                    # already implemented with the identical names in JFJ
                    # create_or_update_dataset('entry/instrument/detector/saturation_value', data = np.iinfo('int32').max, dtype='uint32')
                    # create_or_update_dataset('entry/instrument/detector/sensor_material', data = 'Si')
                    # create_or_update_dataset('entry/instrument/detector/sensor_thickness', data = 0.32, dtype='float')
                    # create_or_update_dataset('entry/instrument/detector/sensor_thickness_unit', data = 'mm')
                    # create_or_update_dataset('entry/instrument/detector/frame_time', data = interval, dtype='float')
                    # create_or_update_dataset('entry/instrument/detector/frame_time_unit', data = 's')
                    # create_or_update_dataset('entry/instrument/detector/detectorSpecific/ntrigger', data = 1, dtype='uint64')
                    # ED-specific, optics
                    create_or_update_dataset('entry/instrument/optics/info_acquisition_date_time', data = time.strftime("%Y/%m/%d %H:%M:%S", time.localtime()))
                    create_or_update_dataset('entry/instrument/optics/microscope_name', data = 'JEOL JEM2100Plus')
                    create_or_update_dataset('entry/instrument/optics/accelerationVoltage', data = ht, dtype='float')
                    create_or_update_dataset('entry/instrument/optics/wavelength', data = wavelength, dtype='float')
                    create_or_update_dataset('entry/instrument/optics/magnification', data = tem_status['eos.GetMagValue_MAG'][0], dtype='uint16')
                    create_or_update_dataset('entry/instrument/optics/distance_nominal', data = tem_status['eos.GetMagValue_DIFF'][0], dtype='uint16')
                    create_or_update_dataset('entry/instrument/optics/end_tilt_angle', data = tem_status['stage.GetPos'][3], dtype='float')
                    create_or_update_dataset('entry/instrument/optics/spot_size', data = tem_status['eos.GetSpotSize']+1, dtype='uint16')
                    create_or_update_dataset('entry/instrument/optics/alpha_angle', data = tem_status['eos.GetAlpha']+1, dtype='uint16')
                    create_or_update_dataset('entry/instrument/optics/CL_ID', data = tem_status['apt.GetSize(1)'], dtype='uint16')
                    create_or_update_dataset('entry/instrument/optics/CL_size', data = f'{aperture_size_cl} um') # <- LUT
                    create_or_update_dataset('entry/instrument/optics/SA_ID', data = tem_status['apt.GetSize(4)'], dtype='uint16')
                    create_or_update_dataset('entry/instrument/optics/SA_size', data = f'{aperture_size_sa} um') # <- LUT
                    create_or_update_dataset('entry/instrument/optics/brightness', data = tem_status['lens.GetCL3'], dtype='uint32')
                    create_or_update_dataset('entry/instrument/optics/diff_focus', data = tem_status['lens.GetIL1'], dtype='uint32')
                    create_or_update_dataset('entry/instrument/optics/il_stigm_x', data = tem_status['defl.GetILs'][0], dtype='uint32')
                    create_or_update_dataset('entry/instrument/optics/il_stigm_y', data = tem_status['defl.GetILs'][1], dtype='uint32')
                    create_or_update_dataset('entry/instrument/optics/pl_align_x', data = tem_status['defl.GetPLA'][0], dtype='uint32')
                    create_or_update_dataset('entry/instrument/optics/pl_align_y', data = tem_status['defl.GetPLA'][1], dtype='uint32')
                    
                    # ED-specific, stage
                    create_or_update_dataset('entry/instrument/stage/stage_x', data = tem_status['stage.GetPos'][0]/1e3, dtype='float')
                    create_or_update_dataset('entry/instrument/stage/stage_y', data = tem_status['stage.GetPos'][1]/1e3, dtype='float')
                    create_or_update_dataset('entry/instrument/stage/stage_z', data = tem_status['stage.GetPos'][2]/1e3, dtype='float')
                    create_or_update_dataset('entry/instrument/stage/stage_xyz_unit', data ='um')
                    create_or_update_dataset('entry/instrument/stage/stage_tx_start', data = rotations_angles[0][1], dtype='float')
                    create_or_update_dataset('entry/instrument/stage/stage_tx_end', data = rotations_angles[-1][1], dtype='float')
                    rotation_speed_idx = tem_status['stage.Getf1OverRateTxNum']
                    create_or_update_dataset('entry/instrument/stage/stage_tx_speed_ID', data = rotation_speed_idx, dtype='float')
                    create_or_update_dataset('entry/instrument/stage/velocity_data_collection', data = stage_rates[rotation_speed_idx], dtype='float') # definition of axis is missing in the tag name 
                    # create_or_update_dataset('entry/instrument/stage/stage_tx_speed_nominal', data = tem_status['stage.GetPos'][2], dtype='float') <- LUT
                    create_or_update_dataset('entry/instrument/stage/stage_tx_speed_measured', data = rotation_mean, dtype='float')
                    create_or_update_dataset('entry/instrument/stage/stage_tx_speed_measured_std', data = rotation_std, dtype='float')
                    create_or_update_dataset('entry/instrument/stage/stage_tx_speed_unit', data = 'deg/s')                    
                    create_or_update_dataset('entry/instrument/stage/stage_tx_record', data = rotations_angles)
                    # ED-specific, crystal image
                    # create_or_update_dataset('entry/imagedata_endangle', data = , dtype='float32') # at the end angle
                    # create_or_update_dataset('entry/imagedata_zerotilt', data = , dtype='float32') # at the zero tile\
                    # for cif
                    create_or_update_dataset('entry/cif/_diffrn_ambient_temperature', data = '293(2)')
                    create_or_update_dataset('entry/cif/_diffrn_radiation_wavelength', data = f'{wavelength:8.5f}')
                    create_or_update_dataset('entry/cif/_diffrn_radiation_probe', data = 'electron')
                    create_or_update_dataset('entry/cif/_diffrn_radiation_type', data = '\'monochromatic beam\'')
                    create_or_update_dataset('entry/cif/_diffrn_source', data = '\'transmission electron microscope, LaB6\'')
                    create_or_update_dataset('entry/cif/_diffrn_source_type', data = '\'JEOL JEM2100Plus\'')
                    create_or_update_dataset('entry/cif/_diffrn_source_voltage', data = f'{ht:3d}')
                    create_or_update_dataset('entry/cif/_diffrn_measurement_device_type', data = '\'single axis tomography holder\'')
                    create_or_update_dataset('entry/cif/_diffrn_detector', data = '\'hybrid pixel area detector\'')
                    create_or_update_dataset('entry/cif/_diffrn_detector_type', data = '\'JUNGFRAU\'')
                    # create_or_update_dataset('entry/cif/_diffrn_detector_dtime', data = '\'single axis tomography holder\'') #20?
                    create_or_update_dataset('entry/cif/_diffrn_detector_area_resol_mean', data = f'{1/pixel:6.3f}') # 13.333 = 1/0.075

                    logging.info(f'Information updated in {filename}')
                except ValueError as e:
                    logging.warning(f"ValueError while updating metadata: {e}")
        except OSError as e:
            logging.error(f"Failed to update information in {filename}: {e}")

# Example server execution
if __name__ == "__main__":
    # Initialize logger
    logger = logging.getLogger()

    logger.setLevel("INFO")

    # Create the handler for console output
    console_handler = logging.StreamHandler()

    # Apply the custom formatter to the handler
    formatter = CustomFormatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
    console_handler.setFormatter(formatter)

    # Add the handler to the logger
    logger.addHandler(console_handler)

    server = Hdf5MetadataUpdater()
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()
    logging.info("Server is running in the background. You can now use the command line.")
    # The server will continue to run in the background until exit() is called.