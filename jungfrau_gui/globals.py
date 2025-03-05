import ctypes
import numpy as np
import multiprocessing as mp
from epoc import ConfigurationClient
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

cfg = ConfigurationClient()
stream = "tcp://localhost:4545"
tem_mode = False
# jfj = False

tem_host = cfg.temserver
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
