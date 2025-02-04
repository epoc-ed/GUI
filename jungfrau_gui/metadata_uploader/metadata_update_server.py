import h5py
import logging
import json
import time
import numpy as np
import threading
import os
import subprocess
import re
import hdf5plugin
import zmq
# from epoc import ConfigurationClient, auth_token, redis_host

class DIALSparams:
    def __init__(self, datapath, workdir, beamcenter=[515, 532]):
        self.datapath = datapath
        self.workdir=workdir
        self.beamcenter = beamcenter

    def launch(self, dmax=10, dmin=0.4, nbin=20, gain=20): # this gain is only used in spotfind
        from libtbx import easy_run
        os.makedirs(self.workdir, exist_ok=False)
        os.chdir(self.workdir)

        r = easy_run.fully_buffered(f'dials.import {self.datapath} slow_fast_beam_centre={self.beamcenter[1]},{self.beamcenter[0]}')
        if len(r.stderr_lines) > 0:
            logging.info(f'import of {self.datapath} faild!')
            return
        r = easy_run.fully_buffered(f'dials.find_spots imported.expt gain={gain} d_max={dmax} min_spot_size=12')
        if len(r.stderr_lines) > 0:
            logging.info(f'spotfinding of {self.datapath} faild!')
            return
        r = easy_run.fully_buffered(f'dials.index imported.expt strong.refl detector.fix=distance')
        if len(r.stderr_lines) > 0:
            logging.info(f'indexing of {self.datapath} faild!')
            return
        r = easy_run.fully_buffered(f'dials.refine indexed.expt indexed.refl scan_varying=true detector.fix=distance')
        if len(r.stderr_lines) > 0:
            logging.info(f'refinement of {self.datapath} faild!')
            return
        r = easy_run.fully_buffered(f'dials.integrate refined.expt refined.refl significance_filter.enable=true')
        if len(r.stderr_lines) > 0:
            logging.info(f'integration of {self.datapath} faild!')
            return
        r = easy_run.fully_buffered(f'dials.scale integrated.expt integrated.refl output.merging.nbins={nbin} d_min={dmin}')
        if len(r.stderr_lines) > 0:
            logging.info(f'scaling of {self.datapath} faild!')
            return
        r = easy_run.fully_buffered(f'dials.export scaled.expt scaled.refl format="shelx" compositon="CHNO"')
        if len(r.stderr_lines) > 0:
            logging.info(f'exporting of {self.datapath} faild!')
            return    

class XDSparams:
    """
Stores parameters for XDS and creates the template XDS.INP in the current directory
"""
    def __init__(self, xdstempl):
        self.xdstempl = xdstempl

    def update(self, orgx, orgy, templ, d_range, osc_range, dist, jobs='XYCORR INIT COLSPOT IDXREF'):
        """
           replace parameters for ORGX/ORGY, TEMPLATE, OSCILLATION_RANGE,
           DATA_RANGE, SPOT_RANGE, BACKGROUND_RANGE, STARTING_ANGLE(?)
        """
        self.xdsinp = []
        gap=10
        with open(self.xdstempl, 'r') as f:
            for line in f:
                [keyw, rem] = self.uncomment(line)
                if "ORGX=" in keyw or "ORGY=" in keyw:
                    self.xdsinp.append(f" ORGX= {orgx:.1f} ORGY= {orgy:.1f}\n")
                    continue
                # if "ROTATION_AXIS" in keyw:
                #     axis = np.fromstring(keyw.split("=")[1].strip(), sep=" ")
                #     axis = np.sign(osc_range) * axis
                #     keyw = self.replace(keyw, "ROTATION_AXIS=", np.array2string(axis, separator=" ")[1:-1])
                keyw = self.replace(keyw, "OSCILLATION_RANGE=", abs(osc_range))
                keyw = self.replace(keyw, "DETECTOR_DISTANCE=", dist)
                keyw = self.replace(keyw, "NAME_TEMPLATE_OF_DATA_FRAMES=", templ + '\n')
                keyw = self.replace(keyw, "DATA_RANGE=", f"1 {d_range}")
                keyw = self.replace(keyw, "SPOT_RANGE=", f"1 {d_range}")
                keyw = self.replace(keyw, "BACKGROUND_RANGE=", f"1 {d_range}")
                
                keyw = self.replace(keyw, "JOB=", jobs)
                keyw = self.replace(keyw, "STARTING_ANGLE=", 0)

                self.xdsinp.append(keyw + ' ' + rem)

        self.xdsinp.append(f" UNTRUSTED_ELLIPSE= {orgx-10:d} {orgx+10:d} {orgy-10:d} {orgy+10:d}\n")                
            
    def xdswrite(self, filepath="XDS.INP"):
        "write lines of keywords to XDS.INP in local directory"
        os.makedirs(os.path.dirname(filepath), exist_ok=False)
        with open(filepath, 'w') as f:
            for l in self.xdsinp:
                f.write(l)

    def uncomment(self, line):
        "returns keyword part and comment part in line"
        if ("!" in line):
            idx = line.index("!")
            keyw = line[:idx]
            rem = line[idx:]
        else:
            keyw = line
            rem = ""
        return [keyw, rem]

    def replace(self, line, keyw, val):
        """
        checks whether keyw is present in line (including '=') and replaces the value
        with val
        """
        if (keyw in line):
            line = ' ' + keyw + ' ' + str(val)
        else:
            line = line
        return line
    
    def idxread(self, filepath="IDXREF.LP"):
        """
        read lines of indexing results
        """
        results = {}
        with open(filepath, 'r') as f:
            for line in reversed(f.readlines()):
                if r"UNIT CELL PARAMETERS" in line:
                    results['cell'] = np.array(line.split()[3:], dtype=float)
                if r"SPOTS INDEXED" in line:
                    results['spots'] = line.split()[0], line.split()[3]
                    break
            results_describe = '{0[0]:.1f} {0[1]:.1f} {0[2]:.1f} {0[3]:.0f} {0[4]:.0f} {0[5]:.0f}, {1[0]}/{1[1]}'.format(results['cell'], results['spots'])
        return results_describe
    
    def make_xds_file(self, master_filepath, xds_filepath, beamcenter=[515, 532], osc_measured=True):
        master_file = h5py.File(master_filepath, 'r')
        template_filepath = master_filepath[:-9] + "??????.h5" # master_filepath.replace('master', '??????')
        frame_time = master_file['entry/instrument/detector/frame_time'][()]
        oscillation_range = np.round(frame_time * master_file['entry/instrument/stage/velocity_data_collection'][()], 5)
        if osc_measured:
            try:
                oscillation_range = np.round(frame_time * master_file['entry/instrument/stage/stage_tx_speed_measured'][()], 5)
            except KeyError:
                logging.warning(f'Measured tx_speed is missing! Nominal value is referred instead {oscillation_range}')

        logging.info(f" OSCILLATION_RANGE= {oscillation_range} ! frame time {frame_time}")
        logging.info(f" NAME_TEMPLATE_OF_DATA_FRAMES= {template_filepath}")
        detector_distance = master_file['entry/instrument/detector/detector_distance'][()]
        
        for dset in master_file["entry/data"]:
            nimages_dset = master_file["entry/instrument/detector/detectorSpecific/nimages"][()]
            logging.info(f" DATA_RANGE= 300 {nimages_dset}")
            logging.info(f" BACKGROUND_RANGE= 300 {nimages_dset}")
            logging.info(f" SPOT_RANGE= 300 {nimages_dset}")
            h = master_file['entry/data/data_000001'].shape[2]
            w = master_file['entry/data/data_000001'].shape[1]
            for i in range(1):
                image = master_file['entry/data/data_000001'][i]
                # logging.info(f"   !Image dimensions: {image.shape}, 1st value: {image[0]}")
                org_x, org_y = beamcenter[0], beamcenter[1]
            break

        self.update(org_x, org_y, template_filepath, nimages_dset, oscillation_range, detector_distance)
        self.xdswrite(filepath=xds_filepath)    

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

def rebin(arr, bin_rate):
    if bin_rate == 1:
        return arr
    new_shape = np.array(arr.shape) // bin_rate
    shape = (new_shape[0], arr.shape[0] // new_shape[0],
             new_shape[1], arr.shape[1] // new_shape[1])
    return arr.reshape(shape).mean(-1).mean(1) #.astype('uint16')

def getcenter(img_array, center=[515, 532], area=100, bin=5):
    clipped = img_array[center[1]-area//2 : center[1]+area//2,
                        center[0]-area//2 : center[0]+area//2]
    scaled = clipped / np.max(clipped) * np.iinfo(np.int16).max / bin // bin
    binned = rebin(clipped, bin)
    brighty, brightx = np.where(binned == np.max(binned))
    brightx *= bin
    brighty *= bin
    brightx += center[0]-area//2 + 1
    brighty += center[1]-area//2 + 1
    bright = list(zip(brightx, brighty))
    # print(np.array(bright).mean(axis=0), np.array(bright).mean(axis=1), np.array(bright).mean(axis=-1))
    return np.array(bright) #.mean(axis=0) #, clipped

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
                self.addusermask_to_hdf(filename)
                self.socket.send_string("Metadata/Maskdata added successfully") # self.socket.send_string("Metadata added successfully")
                
                if rotations_angles is not None:
                    with h5py.File(filename, 'r') as f:
                        img = f['entry/data/data_000001'][()][100] #, dynamic definition would be better
                    beamcenter_pre = getcenter(img, center=beamcenter, bin=4, area=100)
                    beamcenter_refined = getcenter(img, center=beamcenter_pre[0], bin=1, area=20)[0]
                    logging.info(f"Refined beam center: {beamcenter_refined[0]:d} {beamcenter_refined[1]:d}")
                    # self.socket.send_string(f"Refined beam center: {beamcenter_refined[0]:d} {beamcenter_refined[1]:d}")

                    dataid = re.sub(".*/([0-9]{3})_.*_([0-9]{4})_master.h5","\\1-\\2", filename)
                    logging.info(f'Subdirname: {os.path.dirname(filename)}/XDS/{dataid}')
                    xds_thread = threading.Thread(target=self.run_xds, 
                                                  args=(filename, 
                                        os.path.dirname(filename) + '/XDS/' + dataid,
                                        '/xtal/Integration/XDS/CCSA-templates/XDS-JF1M_JFJ_2024-12-10.INP',
                                        '/xtal/Integration/XDS/XDS-INTEL64_Linux_x86_64/xds_par', 
                                        beamcenter_refined, ), daemon=True)
                    xds_thread.start()
                    # dials_thread = threading.Thread(target=self.run_dials, 
                    #                                 args=(filename, 
                    #                     os.path.dirname(filename) + '/DIALS/' + dataid,
                    #                     beamcenter_refined, ), daemon=True)
                    # dials_thread.start()
            except zmq.ZMQError as e:
                logging.error(f"Error while receiving request: {e}")
                # self.socket.send_string("Error updating metadata")
    
    def stop(self):
        self.running = False
        logging.info("Stopping server...")

    def addusermask_to_hdf(self, filename, usermask='670,670,257,314', sidemask=True, maskvalue=8):
        try:
            with h5py.File(filename, 'a') as f:
                try:
                    mask = f['entry/instrument/detector/detectorSpecific/pixel_mask'][()]
                    f.create_dataset('entry/instrument/detector/detectorSpecific/pixel_mask_original', mask.shape, dtype=mask.dtype, data=mask)
                    mask_xy = np.array(usermask.split(sep=',')).astype('int')
                    mask[mask_xy[2]:mask_xy[3]+1, mask_xy[0]:mask_xy[1]+1] = maskvalue # hot pixel streak
                    if sidemask:
                        mask[:, 0:16] = maskvalue # left-side hidden area
                        mask[:, 1019:1029] = maskvalue # right-side hidden area
                    del f['entry/instrument/detector/detectorSpecific/pixel_mask']
                    f.create_dataset('entry/instrument/detector/detectorSpecific/pixel_mask', mask.shape, dtype=mask.dtype, data=mask)

                    logging.info(f'Maskdata updated in {filename}')
                except ValueError as e:
                    logging.warning(f"ValueError while updating maskdata: {e}")
        except OSError as e:
            logging.error(f"Failed to update maskdata in {filename}: {e}")
        
    def addinfo_to_hdf(self, filename, tem_status, beamcenter, detector_distance, aperture_size_cl, aperture_size_sa, rotations_angles, jf_threshold, pixel=0.075):
        detector_framerate = 2000 # Hz for Jungfrau
        ht = 200  # keV  # <- HT3
        wavelength = eV2angstrom(ht * 1e3)  # Angstrom
        stage_rates = [10.0, 2.0, 1.0, 0.5]
        jfj_version = "1.0.0-rc.24"
        if rotations_angles is not None:
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
                    # create_or_update_dataset('entry/instrument/detector/detectorSpecific/software_version_gui', data = self.***.version)
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
                    rotation_speed_idx = tem_status['stage.Getf1OverRateTxNum']
                    create_or_update_dataset('entry/instrument/stage/stage_tx_speed_ID', data = rotation_speed_idx, dtype='float')
                    create_or_update_dataset('entry/instrument/stage/velocity_data_collection', data = stage_rates[rotation_speed_idx], dtype='float') # definition of axis is missing in the tag name 
                    if rotations_angles is not None:
                        create_or_update_dataset('entry/instrument/stage/stage_tx_start', data = rotations_angles[0][1], dtype='float')
                        create_or_update_dataset('entry/instrument/stage/stage_tx_end', data = rotations_angles[-1][1], dtype='float')
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

    def run_xds(self, master_filepath, working_directory, xds_template_filepath, xds_exepath='xds_par', beamcenter=[515, 532]):
        # self.socket.send_string("Processing with XDS")
        root = working_directory
        myxds = XDSparams(xdstempl=xds_template_filepath)
        myxds.make_xds_file(master_filepath,
                           os.path.join(root, "XDS.INP"), #""INPUT.XDS"), # why not XDS.INP?
                           beamcenter)
        
        if os.path.isfile(root + '/XDS.INP'):
            subprocess.run([xds_exepath], cwd=root)
        else:
            return 'XDS.INP is missing.'
        
        time.sleep(3)
        if os.path.isfile(root + '/XPARM.XDS'):
            logging.info('Indexing succeeded.')
            results = myxds.idxread(filepath=root + '/IDXREF.LP')
            logging.info(results)
        else:
            logging.info('Indexing failed.')
            results = 'Failed'
        # self.socket.send_string(results)
        return results

    def run_dials(self, master_filepath, working_directory, beamcenter=[515, 532]):
        # self.socket.send_string("Processing with DIALS")
        results = 'Failed'
        root = working_directory
        
        which = subprocess.run(['which', 'dials.import'], stdout=subprocess.PIPE)
        if len(which.stdout) == 0:
            logging.warning('DIALS is not available')
            return results
        
        mydials = DIALSparams(datapath=master_filepath, workdir=root, beamcenter=beamcenter)
        mydials.launch()

        if os.path.isfile(root + '/indexed.refl'):
            logging.info('Indexing succeeded.')
            with open('dials.index.log', 'r') as f:
                results['cell'] = re.sub('([0-9]*)', "", f.readlines()[-18]).split(sep='[, s]')
                spotinfo = f.readlines()[-4].split()
                results['spots'] = [spotinfo[3], spotinfo[3]+spotinfo[5]]
            results_describe = '{0[0]:.1f} {0[1]:.1f} {0[2]:.1f} {0[3]:.0f} {0[4]:.0f} {0[5]:.0f}, {1[0]}/{1[1]}'.format(results['cell'], results['spots'])
            # self.socket.send_string(results_describe)
            return results_describe
        else:
            logging.info('Indexing failed.')
        # self.socket.send_string(results)
        return results
            
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