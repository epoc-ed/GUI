import numpy as np
import time
import h5py
import hdf5plugin
import logging
from ....ui_components.tem_controls.toolbox import config as cfg_jf
from PySide6.QtCore import QObject, Signal

from epoc import ConfigurationClient, auth_token, redis_host
import zmq
from .... import globals

def create_full_mapping(info_queries, more_queries, init_queries, info_queries_client, more_queries_client, init_queries_client):
    """
    Creates a mapping between two sets of queries and their corresponding client-side equivalents.

    Parameters:
    ----------
    info_queries : list
        List of primary queries.
    more_queries : list
        List of additional queries.
    init_queries_client : list
        List of queries at starting.
    info_queries_client : list
        Client-side equivalents of primary queries.
    more_queries_client : list
        Client-side equivalents of additional queries.
    init_queries_client : list
        Client-side equivalents of queries at starting.

    Returns:
    -------
    dict
        Dictionary mapping queries to their client-side counterparts.
    """
    mapping = {}

    # Mapping for INFO_QUERIES to INFO_QUERIES_CLIENT
    for info_query, client_query in zip(info_queries, info_queries_client):
        mapping[info_query] = client_query

    # Mapping for MORE_QUERIES to MORE_QUERIES_CLIENT
    for more_query, client_query in zip(more_queries, more_queries_client):
        mapping[more_query] = client_query

    # Mapping for INIT_QUERIES to INIT_QUERIES_CLIENT
    for init_query, client_query in zip(init_queries, init_queries_client):
        mapping[init_query] = client_query
        
    return mapping

# Example usage
INFO_QUERIES = [
    "stage.GetPos", 
    "stage.GetStatus", 
    "eos.GetMagValue", 
    "eos.GetFunctionMode", 
    "defl.GetBeamBlank",
    "stage.Getf1OverRateTxNum"
]

MORE_QUERIES = [
    "stage.GetPos", 
    "stage.GetStatus", 
    "eos.GetMagValue", 
    "eos.GetFunctionMode",
    "stage.Getf1OverRateTxNum",
    "apt.GetSize(1)", 
    "apt.GetSize(4)",  # 1=CL, 4=SA
    "apt.GetKind",
    "apt.GetPosition",
    "eos.GetSpotSize", 
    "eos.GetAlpha", 
    "lens.GetCL3", 
    "lens.GetIL1", 
    "lens.GetOLf",
    "lens.GetIL3", 
    "lens.GetOLc",  # OLf = defocus(fine)
    "defl.GetILs", 
    "defl.GetPLA", 
    "defl.GetBeamBlank",
    "stage.GetMovementValueMeasurementMethod"  # 0=encoder/1=potentio
]

INIT_QUERIES = [
    "ht.GetHtValue",
]

INFO_QUERIES_CLIENT = [
    "GetStagePosition()", 
    "GetStageStatus()", 
    "GetMagValue()", 
    "GetFunctionMode()",
    "GetBeamBlank()", 
    "Getf1OverRateTxNum()"
]

MORE_QUERIES_CLIENT = [
    "GetStagePosition()", 
    "GetStageStatus()", 
    "GetMagValue()", 
    "GetFunctionMode()",
    "Getf1OverRateTxNum()",
    "_send_message(GetApertureSize_CL)", # "GetApertureSize(1)", "GetApertureSize(4)", 
    "_send_message(GetApertureSize_SA)",  # 1=CL, 4=SA
    "_send_message(GetApertureKind)", # "GetApertureKind", 
    "_send_message(GetAperturePosition)", # "GetAperturePosition", 
    "GetSpotSize()", 
    "GetAlpha()", 
    "GetCL3()", 
    "GetIL1()", 
    "GetOLf()",
    "GetIL3()", 
    "GetOLc()",  # OLf = defocus(fine)
    "GetILs()", 
    "GetPLA()", 
    "GetBeamBlank()",
    "GetMovementValueMeasurementMethod()"  # 0=encoder/1=potentio
]

INIT_QUERIES_CLIENT = [
    "_send_message(GetHtValue)", # "ht.GetHtValue", 
]

# Map of Magnification status and correspondent radio button i.e. {Mag_idx : button_idx}
mag_indices = {
    0:0, # 0=MAG     is equivalent to check button 0
    1:0, # 1=MAG2    is equivalent to check button 0
    2:2, # 2=Low MAG is equivalent to check button 2
    4:4  # 4=DIFF    is equivalent to check button 4
}

# Creating the full mapping
full_mapping = create_full_mapping(INFO_QUERIES, MORE_QUERIES, INIT_QUERIES, INFO_QUERIES_CLIENT, MORE_QUERIES_CLIENT, INIT_QUERIES_CLIENT)

def send_with_retries(client_method, *args, retries=3, delay=0.1, **kwargs):
    """
    A reusable method that attempts to call a TEMClient method with retries in case of TimeoutError.

    Parameters:
    - client_method: The TEMClient method to call (e.g., self.client.SetTiltXAngle).
    - *args: Positional arguments to pass to the client method.
    - retries (int): Number of retry attempts before giving up.
    - delay (int): Delay in seconds between retries.
    - **kwargs: Keyword arguments to pass to the client method.

    Returns:
    - The result of the client method if successful.
    
    Raises:
    - TimeoutError: If all retry attempts fail.
    - Exception: Any other exception raised by the client method.
    """
    for attempt in range(retries):
        try:
            logging.info(f"Attempting {client_method.__name__} with args {args} (Attempt {attempt + 1}/{retries})")
            # Dynamically call the method with args and kwargs
            result = client_method(*args, **kwargs)
            return result  # Exit early if successful
        except (TimeoutError, zmq.ZMQError) as e:
            logging.error(f"TimeoutError during {client_method.__name__}: {e}")
            if attempt == retries - 1:
                logging.error(f"Max retry attempts reached for {client_method.__name__}. Giving up.")
                raise
            time.sleep(delay)  # Optional delay between retries
        except Exception as e:
            logging.error(f"Error during {client_method.__name__}: {e}")
            raise  # Raise other exceptions immediately

def eV2angstrom(voltage):
    """
    Converts electron voltages to Angstroms.

    This function computes the wavelength corresponding to a given energy 
    specified in electron volts. The calculation uses fundamental constants:
    - Planck constant (h)
    - Electron mass (m0)
    - Elementary charge (e)
    - Speed of light (c)
    
    The result is returned in Angstroms, which are used to describe atomic scale lengths.
    """
    h, m0, e, c = 6.62607004e-34, 9.10938356e-31, 1.6021766208e-19, 299792458.0
    return h/np.sqrt(2*m0*e*voltage*(1.+e*voltage/2./m0/c**2)) * 1.e10

def d2radius_in_px(d=1, camlen=660, ht=200, pixel=0.075):  # d in Angstroms, camlen in mm, ht in keV, pixel in mm
    """
    Calculates the radius of an electron diffraction pattern in pixels.
    
    Inputs:
    - d: Interplanar spacing in Angstroms.
    - camlen: Camera length in millimeters.
    - ht: High tension or acceleration voltage in kiloelectron volts.
    - pixel: Pixel size in millimeters.
    
    This function first converts the high tension (acceleration voltage) to a wavelength using the 
    eV2angstrom function. It then calculates the diffraction angle and converts this to the radius 
    of the diffraction pattern in pixels using the camera's geometry.
    """
    wavelength = eV2angstrom(ht * 1e3)
    radius = camlen * np.tan(np.arcsin(wavelength / 2 / d) * 2) / pixel
    return radius

class TEMTools(QObject):
    trigger_addinfo_to_hdf5 = Signal()
    def __init__(self, tem_action):
        super().__init__()
        self.tem_action = tem_action
        self.tem_controls = self.tem_action.tem_controls
        self.cfg = ConfigurationClient(redis_host(), token=auth_token())
        self.trigger_addinfo_to_hdf5.connect(self.addinfo_to_hdf)     
 
    def addinfo_to_hdf(self, pixel=0.075):
        tem_status = self.tem_action.control.tem_status       
        filename = self.tem_action.file_operations.formatted_filename
        beamcenter = self.cfg.beam_center
        interval = self.tem_action.visualization_panel.update_interval.value()
        ht = self.tem_controls.voltage_spBx.value() #200
        wavelength = eV2angstrom(ht*1e3) # Angstrom   
        stage_rates = [10.0, 2.0, 1.0, 0.5]
        try:
            with h5py.File(filename, 'a') as f:
                try:
                    # tagname mimiced from dectris HDF
                    f.create_dataset('entry/instrument/detector/detector_name', data = 'JUNGFRAU FOR ED AT UNIVERSITY OF VIENNA')
                    f.create_dataset('entry/instrument/detector/beam_center_x', data = beamcenter[0], dtype='float') # <- FITTING
                    f.create_dataset('entry/instrument/detector/beam_center_y', data = beamcenter[1], dtype='float') # <- FITTING
                    detector_distance = cfg_jf.lookup(cfg_jf.lut.distance, tem_status['eos.GetMagValue_DIFF'][2], 'displayed', 'calibrated')
                    f.create_dataset('entry/instrument/detector/detector_distance', data = detector_distance, dtype='uint64') # <- LUT
                    f.create_dataset('entry/instrument/detector/frame_time', data = interval*1e-3, dtype='float')
                    # f.create_dataset('entry/instrument/detector/frame_time_unit', data = 's')
                    f.create_dataset('entry/instrument/detector/saturation_value', data = 2e32-1, dtype='float')
                    f.create_dataset('entry/instrument/detector/sensor_material', data = 'Si')
                    f.create_dataset('entry/instrument/detector/sensor_thickness', data = 0.32, dtype='float')
                    f.create_dataset('entry/instrument/detector/sensor_thickness_unit', data = 'mm')
                    # f.create_dataset('entry/instrument/detector/virtual_pixel_correction_applied', data = 200, dtype='float') # =GAIN?
                    # f.create_dataset('entry/instrument/detector/detectorSpecific/data_collection_date_time', data = time.strftime("%Y/%m/%d %H:%M:%S", time.localtime()))
                    f.create_dataset('entry/instrument/detector/detectorSpecific/element', data = 'Si')
                    # f.create_dataset('entry/instrument/detector/detectorSpecific/frame_count_time', data = data_shape[0], dtype='uint64')
                    # f.create_dataset('entry/instrument/detector/detectorSpecific/frame_period', data = data_shape[0], dtype='uint64') = frame_count_time in SINGLA
                    f.create_dataset('entry/instrument/detector/detectorSpecific/ntrigger', data = 1, dtype='uint64')
                    f.create_dataset('entry/instrument/detector/detectorSpecific/software_version', data = 'srecv/' + self.tem_action.version)
                    # ED-specific, some namings from https://github.com/dials/dxtbx/blob/main/src/dxtbx/format/FormatNXmxED.py
                    f.create_dataset('entry/source/probe', data = 'electron')
                    # ED-specific, optics
                    f.create_dataset('entry/instrument/optics/info_acquisition_date_time', data = time.strftime("%Y/%m/%d %H:%M:%S", time.localtime()))
                    f.create_dataset('entry/instrument/optics/microscope_name', data = 'JEOL JEM2100Plus')
                    f.create_dataset('entry/instrument/optics/accelerationVoltage', data = ht, dtype='float')
                    f.create_dataset('entry/instrument/optics/wavelength', data = wavelength, dtype='float')
                    f.create_dataset('entry/instrument/optics/magnification', data = tem_status['eos.GetMagValue_MAG'][0], dtype='uint16')
                    f.create_dataset('entry/instrument/optics/distance_nominal', data = tem_status['eos.GetMagValue_DIFF'][0], dtype='uint16')
                    f.create_dataset('entry/instrument/optics/end_tilt_angle', data = tem_status['stage.GetPos'][3], dtype='float')
                    f.create_dataset('entry/instrument/optics/spot_size', data = tem_status['eos.GetSpotSize']+1, dtype='uint16')
                    f.create_dataset('entry/instrument/optics/alpha_angle', data = tem_status['eos.GetAlpha']+1, dtype='uint16')
                    f.create_dataset('entry/instrument/optics/CL_ID', data = tem_status['apt.GetSize(1)'], dtype='uint16')
                    aperture_size = cfg_jf.lookup(cfg_jf.lut.cl, tem_status['apt.GetSize(1)'], 'ID', 'size')
                    f.create_dataset('entry/instrument/optics/CL_size', data = f'{aperture_size} um') # <- LUT
                    f.create_dataset('entry/instrument/optics/SA_ID', data = tem_status['apt.GetSize(4)'], dtype='uint16')
                    aperture_size = cfg_jf.lookup(cfg_jf.lut.sa, tem_status['apt.GetSize(4)'], 'ID', 'size')
                    f.create_dataset('entry/instrument/optics/SA_size', data = f'{aperture_size} um') # <- LUT
                    f.create_dataset('entry/instrument/optics/brightness', data = tem_status['lens.GetCL3'], dtype='uint32')
                    f.create_dataset('entry/instrument/optics/diff_focus', data = tem_status['lens.GetIL1'], dtype='uint32')
                    f.create_dataset('entry/instrument/optics/il_stigm_x', data = tem_status['defl.GetILs'][0], dtype='uint32')
                    f.create_dataset('entry/instrument/optics/il_stigm_y', data = tem_status['defl.GetILs'][1], dtype='uint32')
                    f.create_dataset('entry/instrument/optics/pl_align_x', data = tem_status['defl.GetPLA'][0], dtype='uint32')
                    f.create_dataset('entry/instrument/optics/pl_align_y', data = tem_status['defl.GetPLA'][1], dtype='uint32')
                    # ED-specific, stage
                    f.create_dataset('entry/instrument/stage/stage_x', data = tem_status['stage.GetPos'][0]/1e3, dtype='float')
                    f.create_dataset('entry/instrument/stage/stage_y', data = tem_status['stage.GetPos'][1]/1e3, dtype='float')
                    f.create_dataset('entry/instrument/stage/stage_z', data = tem_status['stage.GetPos'][2]/1e3, dtype='float')
                    f.create_dataset('entry/instrument/stage/stage_xyz_unit', data ='um')
                    # f.create_dataset('entry/instrument/stage/stage_tx_start', data = tem_status['stage.GetPos'][2], dtype='float')
                    # f.create_dataset('entry/instrument/stage/stage_tx_end', data = tem_status['stage.GetPos'][2], dtype='float')
                    f.create_dataset('entry/instrument/stage/stage_tx_speed_ID', data = tem_status['stage.Getf1OverRateTxNum'], dtype='float')
                    f.create_dataset('entry/instrument/stage/velocity_data_collection', data = stage_rates[self.cfg.rotation_speed_idx], dtype='float')
                    # f.create_dataset('entry/instrument/stage/stage_tx_speed_nominal', data = tem_status['stage.GetPos'][2], dtype='float') <- LUT
                    # f.create_dataset('entry/instrument/stage/stage_tx_speed_measured', data = tem_status['stage.GetPos'][2], dtype='float') <- LUT
                    # f.create_dataset('entry/instrument/stage/stage_tx_speed_unit', data = 'deg/s')
                    # ED-specific, crystal image
                    # f.create_dataset('entry/imagedata_endangle', data = , dtype='float32') # at the end angle
                    # f.create_dataset('entry/imagedata_zerotilt', data = , dtype='float32') # at the zero tile\
                    # for cif
                    f.create_dataset('entry/cif/_diffrn_ambient_temperature', data = '293(2)')
                    f.create_dataset('entry/cif/_diffrn_radiation_wavelength', data = f'{wavelength:8.5f}')
                    f.create_dataset('entry/cif/_diffrn_radiation_probe', data = 'electron')
                    f.create_dataset('entry/cif/_diffrn_radiation_type', data = '\'monochromatic beam\'')
                    f.create_dataset('entry/cif/_diffrn_source', data = '\'transmission electron microscope, LaB6\'')
                    f.create_dataset('entry/cif/_diffrn_source_type', data = '\'JEOL JEM2100Plus\'')
                    f.create_dataset('entry/cif/_diffrn_source_voltage', data = f'{ht:3d}')
                    f.create_dataset('entry/cif/_diffrn_measurement_device_type', data = '\'single axis tomography holder\'')
                    f.create_dataset('entry/cif/_diffrn_detector', data = '\'hybrid pixel area detector\'')
                    f.create_dataset('entry/cif/_diffrn_detector_type', data = '\'JUNGFRAU\'')
                    # f.create_dataset('entry/cif/_diffrn_detector_dtime', data = '\'single axis tomography holder\'') #20?
                    f.create_dataset('entry/cif/_diffrn_detector_area_resol_mean', data = f'{1/pixel:6.3f}') # 13.333 = 1/0.075
                    
                    logging.info(f'Information updated in {filename}')
                except ValueError:
                    pass
            
        except OSError:
            print(f'Failed to update information in {filename}!!!')

    # def get_corrected_detector_distance(self, distance, with_unit=True):
    #     for entry in self.config["distances"]:
    #         if distance == entry["displayed"]:
    #             if with_unit:
    #                 return str(entry["calibrated"]) + entry["unit"]
    #             else:
    #                 return str(entry["calibrated"])
    #         logging.warning('No distance value in LUT')
    #     return distance
