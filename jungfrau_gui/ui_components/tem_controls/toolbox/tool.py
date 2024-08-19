import numpy as np
import time
import h5py
import hdf5plugin
import logging
from ....ui_components.tem_controls.toolbox import config as cfg_jf
from PySide6.QtCore import QObject, Signal

def ev2angstrom(voltage): # in ev
    h, m0, e, c = 6.62607004e-34, 9.10938356e-31, 1.6021766208e-19, 299792458.0
    return h/np.sqrt(2*m0*e*voltage*(1.+e*voltage/2./m0/c**2)) * 1.e10

def d2radius_in_px(d=1, camlen=660, ht=200, pixel=0.075): # angstrom, mm, keV, mm
    wavelength = ev2angstrom(ht*1e3)
    radius = camlen * np.tan(np.arcsin(wavelength/2/d)*2) / pixel
    return radius

class TEMTools(QObject):
    trigger_addinfo_to_hdf5 = Signal()
    def __init__(self, tem_action):
        super().__init__()
        self.tem_action = tem_action
        self.ht = 200 # keV  # <- HT3
        self.wavelength = ev2angstrom(self.ht*1e3) # Angstrom   
        self.trigger_addinfo_to_hdf5.connect(self.addinfo_to_hdf)     
 
    def addinfo_to_hdf(self, pixel=0.075):
        self.tem_status = self.tem_action.control.tem_status
        self.filename = self.tem_action.file_operations.formatted_filename
        self.beamcenter = self.tem_action.beamcenter
        self.interval = self.tem_action.visualization_panel.update_interval.value()
        try:
            with h5py.File(self.filename, 'a') as f:
                try:
                    # tagname mimiced from dectris HDF
                    f.create_dataset('entry/instrument/detector/detector_name', data = 'JUNGFRAU FOR ED AT UNIVERSITY OF VIENNA')
                    f.create_dataset('entry/instrument/detector/beam_center_x', data = self.beamcenter[0], dtype='float') # <- FITTING
                    f.create_dataset('entry/instrument/detector/beam_center_y', data = self.beamcenter[1], dtype='float') # <- FITTING
                    detector_distance = cfg_jf.lookup(cfg_jf.lut.distance, self.tem_status['eos.GetMagValue_DIFF'][2], 'displayed', 'calibrated')
                    f.create_dataset('entry/instrument/detector/detector_distance', data = detector_distance, dtype='uint64') # <- LUT
                    f.create_dataset('entry/instrument/detector/frame_time', data = self.interval*1e-3, dtype='float')
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
                    f.create_dataset('entry/instrument/optics/accelerationVoltage', data = self.ht, dtype='float')
                    f.create_dataset('entry/instrument/optics/wavelength', data = self.wavelength, dtype='float')
                    f.create_dataset('entry/instrument/optics/magnification', data = self.tem_status['eos.GetMagValue_MAG'][0], dtype='uint16')
                    f.create_dataset('entry/instrument/optics/distance_nominal', data = self.tem_status['eos.GetMagValue_DIFF'][0], dtype='uint16')
                    f.create_dataset('entry/instrument/optics/end_tilt_angle', data = self.tem_status['stage.GetPos'][3], dtype='float')
                    f.create_dataset('entry/instrument/optics/spot_size', data = self.tem_status['eos.GetSpotSize']+1, dtype='uint16')
                    f.create_dataset('entry/instrument/optics/alpha_angle', data = self.tem_status['eos.GetAlpha']+1, dtype='uint16')
                    f.create_dataset('entry/instrument/optics/CL_ID', data = self.tem_status['apt.GetSize(1)'], dtype='uint16')
                    aperture_size = cfg_jf.lookup(cfg_jf.lut.cl, self.tem_status['apt.GetSize(1)'], 'ID', 'size')
                    f.create_dataset('entry/instrument/optics/CL_size', data = f'{aperture_size} um') # <- LUT
                    f.create_dataset('entry/instrument/optics/SA_ID', data = self.tem_status['apt.GetSize(4)'], dtype='uint16')
                    aperture_size = cfg_jf.lookup(cfg_jf.lut.sa, self.tem_status['apt.GetSize(4)'], 'ID', 'size')
                    f.create_dataset('entry/instrument/optics/SA_size', data = f'{aperture_size} um') # <- LUT
                    f.create_dataset('entry/instrument/optics/brightness', data = self.tem_status['lens.GetCL3'], dtype='uint32')
                    f.create_dataset('entry/instrument/optics/diff_focus', data = self.tem_status['lens.GetIL1'], dtype='uint32')
                    f.create_dataset('entry/instrument/optics/il_stigm_x', data = self.tem_status['defl.GetILs'][0], dtype='uint32')
                    f.create_dataset('entry/instrument/optics/il_stigm_y', data = self.tem_status['defl.GetILs'][1], dtype='uint32')
                    f.create_dataset('entry/instrument/optics/pl_align_x', data = self.tem_status['defl.GetPLA'][0], dtype='uint32')
                    f.create_dataset('entry/instrument/optics/pl_align_y', data = self.tem_status['defl.GetPLA'][1], dtype='uint32')
                    # ED-specific, stage
                    f.create_dataset('entry/instrument/stage/stage_x', data = self.tem_status['stage.GetPos'][0]/1e3, dtype='float')
                    f.create_dataset('entry/instrument/stage/stage_y', data = self.tem_status['stage.GetPos'][1]/1e3, dtype='float')
                    f.create_dataset('entry/instrument/stage/stage_z', data = self.tem_status['stage.GetPos'][2], dtype='float')
                    f.create_dataset('entry/instrument/stage/stage_xyz_unit', data ='um')
                    # f.create_dataset('entry/instrument/stage/stage_tx_start', data = self.tem_status['stage.GetPos'][2], dtype='float')
                    # f.create_dataset('entry/instrument/stage/stage_tx_end', data = self.tem_status['stage.GetPos'][2], dtype='float')
                    f.create_dataset('entry/instrument/stage/stage_tx_speed_ID', data = self.tem_status['stage.Getf1OverRateTxNum'], dtype='float')
                    # f.create_dataset('entry/instrument/stage/stage_tx_speed_nominal', data = self.tem_status['stage.GetPos'][2], dtype='float') <- LUT
                    # f.create_dataset('entry/instrument/stage/stage_tx_speed_measured', data = self.tem_status['stage.GetPos'][2], dtype='float') <- LUT
                    # f.create_dataset('entry/instrument/stage/stage_tx_speed_unit', data = 'deg/s')
                    # ED-specific, crystal image
                    # f.create_dataset('entry/imagedata_endangle', data = , dtype='float32') # at the end angle
                    # f.create_dataset('entry/imagedata_zerotilt', data = , dtype='float32') # at the zero tile\
                    # for cif
                    # f.create_dataset('entry/cif/_diffrn_ambient_temperature', data = '293(2)')
                    # f.create_dataset('entry/cif/_diffrn_radiation_wavelength', data = f'{self.wavelength:8.5f}')
                    # f.create_dataset('entry/cif/_diffrn_radiation_probe', data = 'electron')
                    # f.create_dataset('entry/cif/_diffrn_radiation_type', data = '\'monochromatic beam\'')
                    # f.create_dataset('entry/cif/_diffrn_source', data = '\'transmission electron microscope, LaB6\'')
                    # f.create_dataset('entry/cif/_diffrn_source_type', data = '\'JEOL JEM2100Plus\'')
                    # f.create_dataset('entry/cif/_diffrn_source_voltage', data = f'{self.ht:3d}')
                    # f.create_dataset('entry/cif/_diffrn_measurement_device_type', data = '\'single axis tomography holder\'')
                    # f.create_dataset('entry/cif/_diffrn_detector', data = '\'hybrid pixel area detector\'')
                    # f.create_dataset('entry/cif/_diffrn_detector_type', data = '\'JUNGFRAU\'')
                    # # f.create_dataset('entry/cif/_diffrn_detector_dtime', data = '\'single axis tomography holder\'') #20?
                    # f.create_dataset('entry/cif/_diffrn_detector_area_resol_mean', data = f'{1/pixel:6.3f}') # 13.333 = 1/0.075
                    
                    logging.info(f'Information updated in {self.filename}')
                except ValueError:
                    pass
            
        except OSError:
            print(f'Failed to update information in {self.filename}!!!')

    # def get_corrected_detector_distance(self, distance, with_unit=True):
    #     for entry in self.config["distances"]:
    #         if distance == entry["displayed"]:
    #             if with_unit:
    #                 return str(entry["calibrated"]) + entry["unit"]
    #             else:
    #                 return str(entry["calibrated"])
    #         logging.warning('No distance value in LUT')
    #     return distance
