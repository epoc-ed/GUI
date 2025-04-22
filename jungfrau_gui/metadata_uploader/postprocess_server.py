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
import argparse
import shutil
# from epoc import ConfigurationClient, auth_token, redis_host
from libtbx import easy_run
# from dxtbx.serialize import load
from dxtbx.model.experiment_list import ExperimentList

VERSION = "for JF_GUI/v2025.04.xx or later"
V_DATE = "2025.04.22"

ROOT_DATA_SAVED = "/data/epoc/storage/jem2100plus/" # self.cfg.base_data_dir.as_posix()
# ROOT_DATA_SAVED = "/data/noether/jem2100plus/" # for local-test on another server
XDS_TEMPLATE = '/xtal/Integration/XDS/CCSA-templates/XDS-JF1M_JFJ_2024-12-10.INP'
XDS_EXE = '/xtal/Integration/XDS/XDS-INTEL64_Linux_x86_64/xds_par'
XSCALE_EXE = '/xtal/Integration/XDS/XDS-INTEL64_Linux_x86_64/xscale_par'
XDSCONV_EXE = '/xtal/Integration/XDS/XDS-INTEL64_Linux_x86_64/xdsconv'
SHELXT_EXE = '/xtal/Suites/Shelx/bin/shelxt'

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

def rebin(arr, bin_factor, method='mean'):
    """
    Downsample (bin) a 2D array by an integer factor.

    Parameters
    ----------
    arr : np.ndarray
        2D array to be rebinned.
    bin_factor : int
        Factor by which to downsample.
    method : str, optional
        How to combine values within each bin. 
        Options: 'mean' (default) or 'sum'.

    Returns
    -------
    np.ndarray
        Re-binned 2D array. Shape will be:
        (arr.shape[0] // bin_factor, arr.shape[1] // bin_factor).
    """
    # Check of bin_factor value to make the method generic and reusable
    if bin_factor < 1:
        raise ValueError("bin_factor must be >= 1.")
    if bin_factor == 1:
        return arr  # No change

    # Original array dimensions
    height, width = arr.shape

    # Compute the new shape, ignoring any remainder
    new_height = height // bin_factor
    new_width = width // bin_factor

    # Crop off any remainder if the image size is not perfectly divisible
    cropped_arr = arr[:new_height * bin_factor, :new_width * bin_factor]

    # Reshape to a 4D array where each bin_factor x bin_factor block is grouped
    reshaped = cropped_arr.reshape(
        new_height, bin_factor,
        new_width, bin_factor
    )

    if method == 'mean':
        # Average within each block
        return reshaped.mean(axis=(1, 3))
    elif method == 'sum':
        # Sum within each block
        return reshaped.sum(axis=(1, 3))
    else:
        raise ValueError("In rebin(), method should be either 'mean' or 'sum'.")

def getcenter(img_array, center=(515, 532), area=100, bin_factor=5, return_all_maxima=True):
    """
    Extract a region around a given center, bin it, and find the brightest spot(s).

    Parameters
    ----------
    img_array : np.ndarray
        2D image from which to find a center.
    center : tuple of int, optional
        (x, y) pixel coordinates around which to extract the region.
    area : int, optional
        Size of the square region (in pixels) to extract around `center`.
    bin_factor : int, optional
        Factor by which to downsample (bin) the extracted region.
    return_all_maxima : bool, optional
        If True, return all (x, y) locations with the same maximum value.
        If False, return only the average of all maxima (as a single (x, y)).

    Returns
    -------
    np.ndarray
        If `return_all_maxima` is True:
            Array of shape (N, 2) containing all max (x, y) coordinates.
        Otherwise:
            A single (x, y) coordinate (shape (2,)) as the average of all maxima.

    Notes
    -----
    - Be mindful of the coordinate convention:
        center=(x, y) means x->column index, y->row index.
    - This function will safely clip the extracted area if `area` is too large
      and extends beyond the image boundaries.
    """
    # Unpack center
    cx, cy = center

    # Ensure we stay within the image bounds when clipping
    height, width = img_array.shape
    half_area = area // 2

    # Compute valid boundaries
    top = max(cy - half_area, 0)
    bottom = min(cy + half_area, height)
    left = max(cx - half_area, 0)
    right = min(cx + half_area, width)

    # Extract the region
    clipped = img_array[top:bottom, left:right]

    # Edge case: if clipped is empty, return something sensible
    if clipped.size == 0:
        # Return an empty array or a special value
        return np.array([])

    # Bin the region using the improved rebin function
    binned = rebin(clipped, bin_factor, method='mean')

    # Find the brightest value in the binned region
    max_val = np.max(binned)
    # If the entire binned region is zero, fallback
    if max_val == 0:
        # Return something indicating no bright spot
        return np.array([0, 0])

    # Get indices of all maxima in the binned array
    max_y, max_x = np.where(binned == max_val)

    # Convert binned coords back to original image coords
    # (x, y) in binned -> multiply by bin_factor -> offset by top/left
    # Note: +left or +top because we clipped from the original image
    # Add 0.5*bin_factor if you want the center of the bin, not the corner.
    max_x_mapped = max_x * bin_factor + left
    max_y_mapped = max_y * bin_factor + top

    # Combine into (x, y) pairs
    bright_spots = np.column_stack((max_x_mapped, max_y_mapped))

    if return_all_maxima:
        return bright_spots
    else:
        # Return the average location (single point)
        return np.round(bright_spots.mean(axis=0)).astype(int)

class DIALSparams:
    def __init__(self, datapath, workdir, beamcenter=[515, 532]):
        self.datapath = datapath
        self.workdir=workdir
        self.beamcenter = beamcenter
        self.expt = None

    def launch(self, dmax=10, dmin=0.4, nbin=20, gain=20, suppress=False): # this gain is only used in spotfind
        os.makedirs(self.workdir, exist_ok=False)
        os.chdir(self.workdir)
        redirect = '> /dev/null' if suppress else ''
        
        r = easy_run.fully_buffered(f'dials.import {self.datapath} slow_fast_beam_centre={self.beamcenter[1]},{self.beamcenter[0]} redirect')
        if len(r.stderr_lines) > 0:
            logging.info(f'DIALS failed to import {self.datapath}!')
            return
        self.expt = self.workdir + "/imported.expt"
        r = easy_run.fully_buffered(f'dials.find_spots imported.expt gain={gain} d_max={dmax} min_spot_size=12 redirect')
        if len(r.stderr_lines) > 0:
            logging.info(f'DIALS failed to find spots of {self.datapath}!')
            return
        r = easy_run.fully_buffered(f'dials.index imported.expt strong.refl detector.fix=distance redirect')
        if len(r.stderr_lines) > 0:
            logging.info(f'DIALS failed to index {self.datapath}!')
            return
        self.expt = self.workdir + "/indexed.expt"
        # r = easy_run.fully_buffered(f'dials.refine indexed.expt indexed.refl scan_varying=true detector.fix=distance redirect')
        # if len(r.stderr_lines) > 0:
        #     logging.info(f'refinement of {self.datapath} faild!')
        #     return
        # r = easy_run.fully_buffered(f'dials.integrate refined.expt refined.refl significance_filter.enable=true redirect')
        # if len(r.stderr_lines) > 0:
        #     logging.info(f'integration of {self.datapath} faild!')
        #     return
        # r = easy_run.fully_buffered(f'dials.scale integrated.expt integrated.refl output.merging.nbins={nbin} d_min={dmin} redirect')
        # if len(r.stderr_lines) > 0:
        #     logging.info(f'scaling of {self.datapath} faild!')
        #     return
        # r = easy_run.fully_buffered(f'dials.export scaled.expt scaled.refl format="shelx" compositon="CHNO" redirect')
        # if len(r.stderr_lines) > 0:
        #     logging.info(f'exporting of {self.datapath} faild!')
        #     return

    def get_result(self): #, refl):
        """
        read lines of indexing results
        """
        expt = self.expt
        results = {}
        if expt is None: return results
        # expt_list = load.experiment_list(expt)
    
        expt_list = ExperimentList.from_file(expt)
        xtal = expt_list.crystals()[0]
        if xtal is None: return results
            
        results['cell'] = xtal.get_unit_cell().parameters()
        results['cell std'] = xtal.get_cell_parameter_sd()
        results['cell a-axis'] = xtal.get_U()[:3]
        results['cell b-axis'] = xtal.get_U()[3:6]
        results['cell c-axis'] = xtal.get_U()[6:]
        results['space group'] = str(xtal.get_space_group().info())
        # with open('dials.index.log', 'r') as f:
        #     spotinfo = f.readlines()[-4].split()
        #     results['spots'] = [spotinfo[3], spotinfo[3]+spotinfo[5]]
        #     results['spots'] = line.split()[0], line.split()[3]
        return results

class XDSparams:
    """
    Stores parameters for XDS and creates the template XDS.INP in the current directory
    """
    def __init__(self, xdstempl):
        self.xdstempl = xdstempl

    def refine(self, jobs='IDXREF DEFPIX INTEGRATE CORRECT', cell=[10,10,10,90,90,90], spacegroup=1, shells=[5,2,1,0.8,0.6,0.5], min_frac_indexed=0.3):
        if not os.path.exists(self.xdstempl):
            logging.warning(f'{self.xdstempl} is not found!!')
            return
        self.xdsinp = []
        with open(self.xdstempl, 'r') as f:
            for line in f:
                if any(command in line for command in ["SPACE_GROUP_NUMBER", "RESOLUTION_SHELLS", "MINIMUM_FRACTION_OF_INDEXED_SPOTS"]):
                    [keyw, rem] = self.uncomment(re.split('[! ]+', line)[1])  # activation
                else:
                    [keyw, rem] = self.uncomment(line)
                keyw = self.replace(keyw, "SPACE_GROUP_NUMBER=", f"{spacegroup}" + '\n')
                keyw = self.replace(keyw, "UNIT_CELL_CONSTANTS=", "  ".join(map(lambda x: str(x), cell)))
                keyw = self.replace(keyw, "MINIMUM_FRACTION_OF_INDEXED_SPOTS=", f"{min_frac_indexed:.2f}" + '\n')
                keyw = self.replace(keyw, "JOB=", jobs)
                keyw = self.replace(keyw, "RESOLUTION_SHELLS=", "  ".join(map(lambda x: str(x), shells)))
                # keyw = self.replace(keyw, "DETECTOR_DISTANCE=", dist)
                self.xdsinp.append(keyw + ' ' + rem)
        
    def update(self, orgx, orgy, templ, d_range, osc_range, dist, jobs='XYCORR INIT COLSPOT IDXREF', starting_angle=0, axis=[0.908490,-0.417907,0.0001], ht=200, beam_direction=[0,0,1]):
        """
           replace parameters for ORGX/ORGY, TEMPLATE, OSCILLATION_RANGE,
           DATA_RANGE, SPOT_RANGE, BACKGROUND_RANGE, STARTING_ANGLE(?)
        """
        self.xdsinp = []
        with open(self.xdstempl, 'r') as f:
            for line in f:
                [keyw, rem] = self.uncomment(line)
                if "ORGX=" in keyw or "ORGY=" in keyw:
                    self.xdsinp.append(f" ORGX= {orgx:.1f} ORGY= {orgy:.1f}\n")
                    continue
                if "ROTATION_AXIS" in keyw:
                    # axis = np.fromstring(keyw.split("=")[1].strip(), sep=" ")
                    axis = np.sign(osc_range) * axis
                    keyw = self.replace(keyw, "ROTATION_AXIS=", "  ".join(map(lambda x: str(x), axis)))
                if "INCIDENT_BEAM_DIRECTION" in keyw:
                    keyw = self.replace(keyw, "INCIDENT_BEAM_DIRECTION=", f"{beam_direction[0]:.5f} {beam_direction[1]:.5f} {beam_direction[2]:.2f}\n")
                keyw = self.replace(keyw, "OSCILLATION_RANGE=", abs(osc_range))
                keyw = self.replace(keyw, "DETECTOR_DISTANCE=", dist)
                keyw = self.replace(keyw, "NAME_TEMPLATE_OF_DATA_FRAMES=", templ + '\n')
                keyw = self.replace(keyw, "DATA_RANGE=", f"1 {d_range}")
                keyw = self.replace(keyw, "SPOT_RANGE=", f"1 {d_range}")
                keyw = self.replace(keyw, "BACKGROUND_RANGE=", f"1 {d_range}")
                
                keyw = self.replace(keyw, "JOB=", jobs)
                keyw = self.replace(keyw, "STARTING_ANGLE=", f"{starting_angle:.2f}")
                keyw = self.replace(keyw, "X-RAY_WAVELENGTH=", f"{eV2angstrom(ht * 1e3):.5f}")
                keyw = self.replace(keyw, "GAIN=", f"{ht:.1f}")

                self.xdsinp.append(keyw + ' ' + rem)
            
    def xdswrite(self, filepath="XDS.INP"):
        "write lines of keywords to XDS.INP in local directory"
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=False)
        except FileExistsError:
            logging.warning("Previous data will be overwritten!")
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
    
    def read_idxref(self, filepath="IDXREF.LP"):
        """
        read lines of indexing results
        """
        results = {}
        with open(filepath, 'r') as f:
            for line in reversed(f.readlines()):
                if r"COORDINATES OF UNIT CELL A-AXIS" in line:
                    results['cell a-axis'] = line.split()[-3:] #np.array(line.split()[-3:], dtype=float)
                if r"COORDINATES OF UNIT CELL B-AXIS" in line:
                    results['cell b-axis'] = line.split()[-3:] #np.array(line.split()[-3:], dtype=float)
                if r"COORDINATES OF UNIT CELL C-AXIS" in line:
                    results['cell c-axis'] = line.split()[-3:] #np.array(line.split()[-3:], dtype=float)
                if r"UNIT CELL PARAMETERS" in line:
                    results['cell'] = line.split()[3:] #np.array(line.split()[-3:], dtype=float)
                if r"SPOTS INDEXED" in line:
                    results['spots'] = line.split()[0], line.split()[3]
                    break
        return results

    def read_correct(self, filepath="CORRECT.LP"):
        """
        read lines of correction results
        """
        results = {}
        stat_table = False
        with open(filepath, 'r') as f:
            for line in reversed(f.readlines()):
                # if r"WILSON STATISTICS OF" in line:
                #     stat_table = True
                # if r"LIMIT" in line:
                #     stat_table = False
                # if stat_table:
                if r"COORDINATES OF UNIT CELL A-AXIS" in line:
                    results['cell a-axis'] = line.split()[-3:] #np.array(line.split()[-3:], dtype=float)
                if r"COORDINATES OF UNIT CELL B-AXIS" in line:
                    results['cell b-axis'] = line.split()[-3:] #np.array(line.split()[-3:], dtype=float)
                if r"COORDINATES OF UNIT CELL C-AXIS" in line:
                    results['cell c-axis'] = line.split()[-3:] #np.array(line.split()[-3:], dtype=float)
                if r"UNIT CELL PARAMETERS" in line:
                    results['cell'] = line.split()[-6:] #np.array(line.split()[-3:], dtype=float)
                if r"E.S.D. OF CELL PARAMETERS" in line:
                    results['cell esd'] = line.split()[-6:] #np.array(line.split()[-3:], dtype=float)
                if r"SPACE GROUP NUMBER" in line:
                    results['space group'] = line.split()[-1]
                if r"INDEXED SPOTS" in line:
                    results['spots_refinement'] = line.split()[-1]
                    break
        return results
    
    def make_xds_file(self, master_filepath, xds_filepath, beamcenter=[515, 532], osc_measured=False):
        master_file = h5py.File(master_filepath, 'r')
        template_filepath = master_filepath[:-9] + "??????.h5" # master_filepath.replace('master', '??????')
        frame_time = master_file['entry/instrument/detector/frame_time'][()]
        oscillation_range = np.round(frame_time * master_file['entry/instrument/stage/velocity_data_collection'][()], 5)
        if osc_measured:
            try:
                oscillation_range = np.round(frame_time * master_file['entry/instrument/stage/stage_tx_speed_measured'][()], 5)
            except KeyError:
                logging.warning(f'Measured tx_speed is missing! Instread, nominal value is referred:  {oscillation_range}')

        detector_distance = master_file['entry/instrument/detector/detector_distance'][()]
        
        for dset in master_file["entry/data"]:
            nimages_dset = master_file["entry/instrument/detector/detectorSpecific/nimages"][()]
            h = master_file['entry/data/data_000001'].shape[2]
            w = master_file['entry/data/data_000001'].shape[1]
            break

        org_x, org_y = w/2, h/2
        pixel_x_mm = master_file['entry/instrument/detector/x_pixel_size'][()]*1e3
        pixel_y_mm = master_file['entry/instrument/detector/y_pixel_size'][()]*1e3
        
        try:
            optical_x = master_file['entry/instrument/optics/optical_axis_center_x'][()]
            optical_y = master_file['entry/instrument/optics/optical_axis_center_y'][()]
            org_x, org_y = optical_x, optical_y
        except KeyError:
            logging.warning(f'Optical_axis_center_xy is missing! Instread, the center of detector is referred')

        beam_direction = [pixel_x_mm * (beamcenter[0] - org_x), pixel_y_mm * (beamcenter[1] - org_y), detector_distance]                
        self.update(org_x, org_y, template_filepath, nimages_dset, oscillation_range, detector_distance, 
                        starting_angle=master_file['entry/instrument/stage/stage_tx_start'][()],
                        axis=master_file['entry/instrument/stage/stage_tx_axis'][()], 
                        ht=master_file['entry/instrument/optics/accelerationVoltage'][()], 
                        beam_direction=beam_direction,
                   )

        margin = args.center_mask # 10
        if margin > 0:
            self.xdsinp.append(f" UNTRUSTED_ELLIPSE= {beamcenter[0]-margin:.0f} {beamcenter[0]+margin:.0f} {beamcenter[1]-margin:.0f} {beamcenter[1]+margin:.0f}\n")

        self.xdswrite(filepath=xds_filepath)

class PostprocessLauncher:
    def __init__(self, port_number = 3467):
        self.port_number = port_number
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REP)
        self.socket.bind(f"tcp://*:{port_number}")
        self.root_data_directory = ROOT_DATA_SAVED # self.cfg.base_data_dir.as_posix()
        self.results = None
        self.error_retry = 5

    def run(self):
        logging.info("Server started, waiting for launching postprocess requests...")
        logging.info(f"Args: {args}")
        while True:
            ready_postprocess = False
            try:
                message_raw = self.socket.recv_string()
                if 'Launching the postprocess...' in message_raw:
                    print(message_raw)
                    filename = self.root_data_directory + message_raw.split()[-1]
                    if not os.path.exists(filename):
                        logging.error(f"{filename} is not found!!")
                        self.socket.send_string('Saved data not found')
                    else:
                        self.socket.send_string(f'{filename} will be processed soon.')
                        ready_postprocess = True
                elif args.feedback and 'Results being inquired...' in message_raw:
                    print(message_raw)
                    if self.results is None:
                        self.socket.send_string("In processing...")
                    else:
                        logging.info("Sending results to GUI...")
                        self.socket.send_string(json.dumps(self.results))
                        self.results = None
                elif args.feedback and 'Session-metadata being inquired...' in message_raw:
                    print(message_raw)
                    search_dir = os.path.dirname(self.root_data_directory + message_raw.split()[-1])
                    if not os.path.exists(search_dir + '/process_result.jsonl'):
                        logging.info(f"Previous session-data does not exist in {search_dir}")
                        self.socket.send_string('Previous session-data not found')
                    else:
                        with open(search_dir + '/process_result.jsonl', 'r') as f:
                            prev_data = [json.loads(line) for line in f]
                        logging.info("Sending Previous session-data...")
                        self.socket.send_string(json.dumps(prev_data))
                else:
                    message = json.loads(message_raw)
                    if isinstance(message, list) and args.json:
                        process_dir = args.path_process
                        if process_dir == '.':
                            process_dir = os.path.dirname(self.root_data_directory + message[-1]["filename"])
                        with open(process_dir + '/process_result.jsonl', 'a') as f:
                            [f.write(json.dumps(i) + "\n") for i in message]
                        self.socket.send_string("Position-info added successfully")
                    else:
                        logging.error(f"Received undefined json-data: {message}")
                        logging.error(f"Otherwise, Json-writing option ('-j') is missing")
            except zmq.ZMQError as e:
                logging.error(f"Error while receiving request: {e}")
                self.error_retry -= 1
                if self.error_retry < 0: break
            except Exception as e:
                logging.error(f"Error while receiving/processing request: {e}", exc_info=True)
            #     break

            if not ready_postprocess: continue

            with h5py.File(filename, 'r') as f:
                beamcenter = f['entry/instrument/detector/beam_center_x'][()], f['entry/instrument/detector/beam_center_y'][()]
                if beamcenter[0]*beamcenter[1] != 1 and not args.refinecenter:
                    beamcenter_refined = beamcenter
                else:
                    middle_index = f["entry/data/data_000001"].shape[0] // 2
                    img = f['entry/data/data_000001'][middle_index] 
                    beamcenter_pre = getcenter(img,
                                               center=(515, 532),
                                               area=100,
                                               bin_factor=4,
                                               return_all_maxima=False)
                    beamcenter_refined = getcenter(img,
                                               center=beamcenter_pre,
                                               area=20,
                                               bin_factor=1,
                                               return_all_maxima=False)
                    logging.info(f"Refined beam center: X = {beamcenter_refined[0]:d}; Y = {beamcenter_refined[1]:d}")

            dataid = re.sub(".*/([0-9]{3})_.*_([0-9]{4})_master.h5","\\1-\\2", filename)
            logging.info(f'Subdirname: {os.path.dirname(filename)}/XDS/{dataid}')

            process_dir = args.path_process
            if process_dir == '.' :
                process_dir = os.path.dirname(filename)
                
            if 'x' in args.processor:
                xds_thread = threading.Thread(target=self.run_xds, 
                                              args=(filename, process_dir + '/XDS/' + dataid, XDS_TEMPLATE, XDS_EXE, 
                                    beamcenter_refined, args.quiet, args.exoscillation, message["tem_status"]['gui_id'], ), daemon=True)
                xds_thread.start()

            if 'd' in args.processor:
                dials_thread = threading.Thread(target=self.run_dials, 
                                                args=(filename, process_dir + '/DIALS/' + dataid, beamcenter_refined, args.quiet, ), daemon=True)
                dials_thread.start()
    
    def stop(self):
        self.running = False
        logging.info("Stopping server...")

    """
    def merge_xds(self, reference_datapath, list_dataid, xscale_exepath='xscale_par', output_name="XSCALE.HKL", cell=[10,10,10,90,90,90], spacegroup=1, resolution_range=[20, -1]):
        root = os.path.dirname(reference_datapath) # root of working_directory
        filtered_list = []
        for xdsacii in list_dataid:
            if not os.path.isfile(root + '/XDS/' + list_dataid + '/XDS_ASCII.HKL'): continue
            filtered_list.append(root + '/XDS/' + list_dataid + '/XDS_ASCII.HKL')

        try:
            os.makedirs(root + '/XSCALE', exist_ok=False)
        except FileExistsError:
            logging.warning("Previous data will be overwritten!")
            
        with open(root + '/XSCALE/XSCALE.INP', 'w') as f:
            f.write(f"OUTPUT_FILE= {output_name}\n\n")
            f.write(f"SPACE_GROUP_NUMBER= {spacegroup}\n")
            f.write(f"UNIT_CELL_CONSTANTS= " + "  ".join(map(lambda x: str(x), cell)) + "\n\n")
            for hkl in filtered_list:
                f.write(f"INPUT_FILE= {hkl}\n")
                if resolution_range[1] < 0: continue
                f.write(f"INCLUDE_RESOLUTION_RANGE= " + "  ".join(map(lambda x: str(x), resolution_range)) + "\n")

        if os.path.isfile(root + '/XSCALE/XSCALE.INP'):
            logging.info(f'XSCALE runs at {root}...')
            if suppress:
                logging.info('Quiet mode:')
                subprocess.run([xscale_exepath], stdout=subprocess.DEVNULL, cwd=root) # stderr=subprocess.DEVNULL
            else:
                subprocess.run([xscale_exepath], cwd=root)
        else:
            return 'XSCALE.INP is missing.'
        
        #### TBU: process to read results

    def run_shelxt(self, hkl_filepath, shelxt_exepath='shelxt', suppress=False, cell=[10,10,10,90,90,90], zerr=[1,0,0,0,0,0,0], options='', composition='CHNO'):
        root = os.path.dirname(hkl_filepath) # root of working_directory

        #### TBU: conversion of hkl to shelx-format
        
        try:
            os.makedirs(root + '/SHELX', exist_ok=False)
        except FileExistsError:
            logging.warning("Previous data will be overwritten!")

        with open(root + '/SHELX/crystal.ins', 'w') as f:
            f.write(f"TITL= [Z] in {spacegroup}\n")
            f.write(f"CELL" + "  ".join(map(lambda x: str(x), cell)) + "\n\n")
            f.write(f"ZERR" + "  ".join(map(lambda x: str(x), zerr)) + "\n")
            f.write(f"LATT -1\n")
            f.write(f"SYMM X, Y, Z\n")
            f.write(f"SFAC" + " ".join(map(lambda x: str(x), composition)) + "\n")
            f.write(f"UNIT" + " ".join(map(lambda x: str(0), composition)) + "\n")
            f.write(f"HKLF\nEND\n")
        
        if os.path.isfile(root + '/SHELX/shelx.ins') and os.path.isfile(hkl_filepath):
            os.symlink(hkl_filepath, root + '/SHELX/shelx.hkl')
            logging.info(f'SHELXT runs at {root}...')
            if suppress:
                logging.info('Quiet mode:')
                subprocess.run([shelxt_exepath, 'crystal'], stdout=subprocess.DEVNULL, cwd=root) # stderr=subprocess.DEVNULL
            else:
                subprocess.run([shelxt_exepath, 'crystal'], cwd=root)
        else:
            return 'crystal.ins is missing.'
        
        #### TBU: process to read results
    """

    def rerun_xds(self, prev_xds_filepath, xds_exepath='xds_par', suppress=False, jobs='IDXREF DEFPIX INTEGRATE CORRECT', cell=[10,10,10,90,90,90], spacegroup=1):
        if self.results is not None:
            results = self.results
        else:
            results = {}
        root = os.path.dirname(prev_xds_filepath) # working_directory
        shutil.copy(prev_xds_filepath, root + 'XDS.INP_IDX')
        myxds = XDSparams(xdstempl=prev_xds_filepath)
        myxds.refine(jobs=jobs, cell=cell, spacegroup=spacegroup)
        myxds.xdswrite(filepath=prev_xds_filepath)
        if os.path.isfile(root + '/XDS.INP'):
            logging.info(f'XDS runs at {root}...')
            if suppress:
                logging.info('Quiet mode:')
                subprocess.run([xds_exepath], stdout=subprocess.DEVNULL, cwd=root)
            else:
                subprocess.run([xds_exepath], cwd=root)
        else:
            return 'XDS.INP is missing.'

        results["integrate"] = "Succeeded" if os.path.isfile(root + "/INTEGRATE.LP") else "Failed"
        if os.path.isfile(root + "/CORRECT.LP"):
            logging.info('Correction succeeded.')
            results["correct"] = "Succeeded"
            results_corr = myxds.read_correct(filepath=root + "/CORRECT.LP")
            results["lattice"] = results_corr["cell"]
            results["lattice esd"] = results_corr["cell esd"]
            results["space group"] = results_corr["space group"]
            # results["spots"] = results_idx["spots"]
            results["cell axes"] = results_corr["cell a-axis"] + results_corr["cell b-axis"] + results_corr["cell c-axis"]            
        else:
            logging.info('Correction failed.')
            results["correct"] = "Failed"
        # if args.json:
        #     with open(os.path.dirname(root)[:-3] + '/process_result.jsonl', 'a') as f: #, encoding="utf-8"
        #         f.write(json.dumps(results) + "\n")
        self.results = results
        logging.info(self.results)
        
    def run_xds(self, master_filepath, working_directory, xds_template_filepath, xds_exepath='xds_par', beamcenter=[515, 532], suppress=False, osc_measured=False, gui_id=999, pos_output=True):
        root = working_directory
        myxds = XDSparams(xdstempl=xds_template_filepath)
        myxds.make_xds_file(master_filepath, os.path.join(root, "XDS.INP"), beamcenter, osc_measured=osc_measured)
        results = {
            "gui_id": gui_id,
            "dataid": os.path.basename(root),
            "filepath": master_filepath,
            "processor": "XDS",
            # "dphi": 0, # should be prepared in GUI, w/o server
            # "summary": None,
            "init": None,
            "colspot": None,
            "idxref": None,
            # "integrate": None,
            # "correct": None,
            "lattice": [1,1,1,90,90,90],
            "spots": [0, 1],
            "cell axes": [1,0,0, 0,1,0, 0,0,1],
            # "space group": 1, # from correct
            # "resolution": 999,
            # "completeness": 0,
        }
        
        if pos_output:
            master_file = h5py.File(master_filepath, 'r')            
            results["position"] = [master_file['entry/instrument/stage/stage_x'][()]*1e3, 
                                   master_file['entry/instrument/stage/stage_y'][()]*1e3,
                                   master_file['entry/instrument/stage/stage_z'][()]*1e3]
            results["status"] = "measured"

        if os.path.isfile(root + '/XDS.INP'):
            logging.info(f'XDS runs at {root}...')
            if suppress:
                logging.info('Quiet mode:')
                subprocess.run([xds_exepath], stdout=subprocess.DEVNULL, cwd=root) # stderr=subprocess.DEVNULL
            else:
                subprocess.run([xds_exepath], cwd=root)
        else:
            logging.warning('XDS.INP is missing.')
            return
        
        results["init"] = "Succeeded" if os.path.isfile(root + "/INIT.LP") else "Failed"
        results["colspot"] = "Succeeded" if os.path.isfile(root + "/COLSPOT.LP") else "Failed"
        if os.path.isfile(root + "/XPARM.XDS"):
            logging.info('Indexing succeeded.')
            results["idxref"] = "Succeeded"
            results_idx = myxds.read_idxref(filepath=root + "/IDXREF.LP")
            results["lattice"] = results_idx["cell"]
            results["spots"] = results_idx["spots"]
            results["cell axes"] = results_idx["cell a-axis"] + results_idx["cell b-axis"] + results_idx["cell c-axis"]            
        else:
            logging.info('Indexing failed.')
            results["idxref"] = "Failed"
        if args.json:
            with open(os.path.dirname(root)[:-3] + '/process_result.jsonl', 'a') as f: #, encoding="utf-8"
                f.write(json.dumps(results) + "\n")
                
        self.results = results
        logging.info(self.results)

    def run_dials(self, master_filepath, working_directory, beamcenter=[515, 532], suppress=False): # osc_measured=False
        which = subprocess.run(['which', 'dials.import'], stdout=subprocess.PIPE)
        if len(which.stdout) == 0:
            logging.warning('DIALS is not available!')
            return

        results = {
            "dataid": os.path.basename(root),
            "filepath": master_filepath,
            "subprocessor": "DIALS",
            "import": None,
            "findspots": None,
            "index": None,
            "lattice_dials": [1,1,1,90,90,90],
            "spots_dials": [0, 1],
            "cell axes_dials": [1,0,0, 0,1,0, 0,0,1],
        }

        if pos_output:
            master_file = h5py.File(master_filepath, 'r')            
            results["position"] = [master_file['entry/instrument/stage/stage_x'][()]*1e3, 
                                   master_file['entry/instrument/stage/stage_y'][()]*1e3,
                                   master_file['entry/instrument/stage/stage_z'][()]*1e3]
            results["status"] = "measured"

        root = working_directory
        mydials = DIALSparams(datapath=master_filepath, workdir=root, beamcenter=beamcenter)
        mydials.launch(suppress=suppress)
        results_dials = mydials.get_result()
        if results_dials.get('cell') is not None:
            results["lattice_dials"] = results_dials["cell"]
            results["lattice esd"] = results_dials["cell esd"]
            results["cell axes"] = results_dials["cell a-axis"] + results_corr["cell b-axis"] + results_corr["cell c-axis"]
            results["space group"] = results_dials["space group"]
            results["import"] = results["findspots"] = results["index"] = "Succeeded"
        # results["spots"] = results_dials["spots"]
        logging.info(results)
        # self.results = results

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-b", "--feedback", action="store_true", help="send post-process results to GUI")
    parser.add_argument("-c", "--center_mask", type=int, default=10, help="centre mask radius [px] in XDS.INP (10). deactivate with 0.")    
    parser.add_argument("-d", "--path_process", type=str, default='.', help="root directory path for data-processing (.). file-writing permission is necessary.")
    parser.add_argument("-j", "--json", action="store_true", help="write a summary of postprocess as a JSON'L' file (process_result.jsonl)")
    parser.add_argument("-o", "--exoscillation", action="store_true", help="use measured oscillation value for postprocess")
    # parser.add_argument("-op", "--opticalcenter", action="store_true", help="calibtate the beam direction")
    parser.add_argument("-q", "--quiet", action="store_true", help="suppress outputs of external programs")
    parser.add_argument("-r", "--refinecenter", action="store_true", help="force post-refine beamcenter position")
    parser.add_argument("-v", "--version", action="store_true", help="display version information")
    # parser.add_argument("-f", "--formula", type=str, default='C2H5NO2', help="chemical formula for ab-initio phasing with shelxt/d")
    parser.add_argument("-p", "--processor", type=str, default='x', help="enable post-processing. 'x' for XDS, 'd' for dials and 'xd' for both)

    args = parser.parse_args()

    print(f"Postprocessing-server for diffraction datasets recorded by Jungfrau / Jungfrau-joch: ver. {V_DATE} {VERSION}")

    if args.version:
        print('''
            **Detailed information of authors, years, project name, Github URL, license, contact address, etc.**
            Metadata-update-server for Electron Diffraction with JUNGFRAU (2024-)
            https://github.com/epoc-ed/GUI
            EPOC Project (2024-)
            https://github.com/epoc-ed
            https://epoc-ed.github.io/manual/index.html
        ''')
    
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

    if not os.access(args.path_process, os.W_OK):
        logging.warning("No file-writing permission!")
        exit()
    
    server = PostprocessLauncher()
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()
    logging.info("Postprocessing-server is running in the background. You can now use the command line.")
    # The server will continue to run in the background until exit() is called
