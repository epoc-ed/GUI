import ctypes
import numpy as np
import multiprocessing as mp
from epoc import ConfigurationClient

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
mag_value_diff = [0, 'mm', '0cm']

tag = 'tag_of_release'
branch = 'branch_of_development'