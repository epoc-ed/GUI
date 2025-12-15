import ctypes
import numpy as np
import multiprocessing as mp
from epoc import ConfigurationClient, auth_token, redis_host
import subprocess

def get_git_info():
    defaults = ('no-tagged-version', 'noname-branch', 'no-commit-hash')
    
    try:
        # 1. Check if Git is installed
        subprocess.run(
            ['git', '--version'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )
        
        # 2. Check if in Git repo (silently)
        result = subprocess.run(
            ['git', 'rev-parse', '--is-inside-work-tree'],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,  # Silence fatal errors
            check=False  # Don't raise exception on failure
        )
        
        if result.returncode != 0:
            return defaults  # Not a Git repo
        
        # 3. Get version info
        tag = subprocess.check_output(
            ['git', 'describe', '--tags', '--abbrev=0'],
            stderr=subprocess.DEVNULL  # Silence warnings
        ).strip().decode('utf-8')
        
        branch = subprocess.check_output(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            stderr=subprocess.DEVNULL
        ).strip().decode('utf-8')
        
        commit = subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'],
            stderr=subprocess.DEVNULL
        ).strip().decode('utf-8')
        
        return tag, branch, commit
    
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Git not installed or command failed
        return defaults

cfg = ConfigurationClient(redis_host(), token=auth_token())
stream = "tcp://localhost:4545"
tem_mode = True
# jfj = False

tem_host = cfg.temserver
tem_port = 3535
dev = False
#Configuration
nrow = cfg.nrows 
ncol = cfg.ncols

dtype = np.float32
cdtype = ctypes.c_float

# fitterWorkerReady = mp.Value(ctypes.c_bool)
# fitterWorkerReady.value = False

accframes = 0
acc_image = np.zeros((nrow,ncol), dtype = dtype)

exit_flag = mp.Value(ctypes.c_bool)
exit_flag.value = False

#Data type to write to file
file_dt = np.int32

#Data type to receive from the stream
stream_dt = np.float32

# Flags for non-updated magnification values in MAG and DIFF modes
mag_value_img = [1, 'X', 'X1']
mag_value_diff = [1, 'mm', '1cm']

tag, branch, commit  = get_git_info()

# constants, presets
UM_TO_NM = 1e3
MM_TO_UM = 1e3
MS_TO_US = 1e3
S_TO_MS = 1e3
KV_TO_V = 1e3 
PIXEL = 0.075 # mm

# TEM control variables
default_HT = 200000.00 # V
backlash = [100, 80, 0, 0]

min_mag_for_mag = 1500 # border between LowMag/Mag

## safety not to hit hardware-limit
click_on_move_thresholds = {'dxy_min': 0.3, 'dxy_max': 100, 
                            'dz_min_mag': 1, 'dz_max_mag': 20,
                            'dz_min_lmag': 3, 'absz_min': -100, 'absz_max': 20}

## stage shift larger than these values will be hold in history
stage_relaxation_thresholds = [30, 30, 30, 0.2, 100] # nm, nm, nm, deg., deg. 

## software limit for GATAN holder. Smaller value (~65) may be necessary for complete safety (e.g. remote-operation).
max_stage_tilt = 72
default_roation_end = 60

## variables for autofocusing
IL1_0 = 21780 # 21819 
ILS_0 = [32920, 32776] # [32820, 32976]
WAIT_TIME_S = 0.25 # TODO: optimize value

## variables for radial integration
al_std = [2.338, 2.024, 1.431, 1.221, 1.1690, 1.0124, 0.9289, 0.9055, 0.8266]

## variabls for postprocess control
sampleinfo = {"formula": "C6H9N3O2", "elements": "CHNO"}
skipframes_spotplotter = 20

## variables for beam-centering
threshold_bc = 5 # px
wait_time_s_bc = 1.5
max_retries_bc = 3
dPLAxy0_bc = [100, 100]
max_dPLA_bc = 2500
min_defocused = 5 # pix
min_distorted = 1.5

# Frame control variables
default_polling_frequency = 1000
min_polling_frequency = 100 # safety not to inquire TEM-values too frequently
max_polling_frequency = 10000

default_frame_summed = 100
default_image_time_us = 500
min_frame_summed = 10 # safety not to save unexpectedly large datasets
max_frame_summed = 1000
detector_freq = 2000
max_duration = 3600 # sec


# Communication variables
dataserver_host = "noether"
dataserver_port = 3463

processserver_host = "gauss" # noether
processserver_port = 3467

max_retries_tagging = 3
inquiry_delay = 0.1 # sec
