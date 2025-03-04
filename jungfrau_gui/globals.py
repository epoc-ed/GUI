import ctypes
import numpy as np
import multiprocessing as mp
from epoc import ConfigurationClient
import subprocess
import os

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

if os.path.isfile('.git'):
    try:
        tag = subprocess.check_output(['git', 'describe', '--tags']).strip().decode('utf-8').split('-')[0]
        branch = subprocess.check_output(['git', 'branch', '--show-current']).strip().decode('utf-8').split()[-1]
        commit = subprocess.check_output(["git", "rev-parse", branch]).strip().decode("utf-8")
    except subprocess.CalledProcessError: # for developers' local testing
        tag, branch, commit  = 'no-tagged-version', 'noname-branch', 'no-commit-hash'
else:
    tag, branch, commit  = 'no-tagged-version', 'noname-branch', 'no-commit-hash'

'''
def in_git_repo():
    """
    Returns True if the current directory is inside a Git repository.
    Otherwise, returns False.
    """
    try:
        # We redirect stderr and stdout to DEVNULL so Git doesn't print error messages:
        with open(os.devnull, 'wb') as devnull:
            subprocess.check_call(
                ['git', 'rev-parse', '--is-inside-work-tree'],
                stdout=devnull, stderr=devnull
            )
        return True
    except subprocess.CalledProcessError:
        return False

# Default fallback values
tag, branch, commit = 'no-tagged-version', 'noname-branch', 'no-commit-hash'

if in_git_repo():
    try:
        tag_output = subprocess.check_output(
            ['git', 'describe', '--tags'],
            stderr=subprocess.DEVNULL
        ).strip().decode('utf-8')
        tag = tag_output.split('-')[0] if tag_output else tag

        branch_output = subprocess.check_output(
            ['git', 'branch', '--show-current'],
            stderr=subprocess.DEVNULL
        ).strip().decode('utf-8')
        branch = branch_output if branch_output else branch

        commit_output = subprocess.check_output(
            ['git', 'rev-parse', branch],
            stderr=subprocess.DEVNULL
        ).strip().decode('utf-8')
        commit = commit_output if commit_output else commit

    except subprocess.CalledProcessError:
        # Fall back to defaults if Git calls fail for any reason
        pass
'''
