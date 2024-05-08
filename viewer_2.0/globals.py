import numpy as np
from reuss import config as cfg
import multiprocessing as mp
import ctypes


#Configuration
nrow = cfg.nrows()
ncol = cfg.ncols()

dtype = np.float32

accframes = 0
acc_image = np.zeros((nrow,ncol), dtype = dtype)

exit_flag = mp.Value(ctypes.c_bool)
exit_flag.value = False