import ctypes
import numpy as np
import multiprocessing as mp

from reuss import config as cfg

stream = "tcp://localhost:4545"

#Configuration
nrow = cfg.nrows()
ncol = cfg.ncols()

dtype = np.float32
cdtype = ctypes.c_float

accframes = 0
acc_image = np.zeros((nrow,ncol), dtype = dtype)

exit_flag = mp.Value(ctypes.c_bool)
exit_flag.value = False