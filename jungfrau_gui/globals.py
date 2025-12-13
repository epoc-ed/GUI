import ctypes
import numpy as np
import multiprocessing as mp
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

# ----------------------------
# Runtime-configurable globals
# ----------------------------
stream = "tcp://localhost:4545"
tem_mode = True
tem_host = "localhost"
dev = False

nrow = 0
ncol = 0

dtype = np.float32
cdtype = ctypes.c_float

accframes = 0
acc_image = np.zeros((0, 0), dtype=dtype)  # allocated properly in init()

exit_flag = mp.Value(ctypes.c_bool)
exit_flag.value = False

# Data type to write to file
file_dt = np.int32

# Data type to receive from the stream
stream_dt = np.float32

# Flags for non-updated magnification values in MAG and DIFF modes
mag_value_img = [1, "X", "X1"]
mag_value_diff = [1, "mm", "1cm"]

# Version info (safe at import; no Redis!)
tag, branch, commit = get_git_info()

# constants, presets
UM_TO_NM = 1e3
MM_TO_UM = 1e3
KV_TO_V = 1e3
PIXEL = 0.075  # mm

default_HT = 200000.00  # V
backlash = [100, 80, 0, 0]


def init(*, stream_, dtype_, cdtype_, tem_mode_, tem_host_, dev_, nrow_, ncol_):
    """
    Initialize globals that previously depended on Redis at import-time.

    Call this exactly once in launch_gui.py *before* importing modules that use globals.
    """
    global stream, dtype, cdtype, tem_mode, tem_host, dev, nrow, ncol, acc_image

    stream = stream_
    dtype = np.dtype(dtype_)
    cdtype = cdtype_

    tem_mode = bool(tem_mode_)
    tem_host = str(tem_host_)
    dev = bool(dev_)

    nrow = int(nrow_)
    ncol = int(ncol_)

    if nrow <= 0 or ncol <= 0:
        raise ValueError(f"Invalid detector geometry: nrow={nrow}, ncol={ncol}")

    acc_image = np.zeros((nrow, ncol), dtype=dtype)