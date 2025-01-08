import ctypes
import numpy as np
import multiprocessing as mp
from epoc import ConfigurationClient

cfg = ConfigurationClient()
stream = "tcp://localhost:4545"
tem_mode = False
# jfj = False

tem_host = cfg.temserver

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
