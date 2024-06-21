import ctypes
import numpy as np
import multiprocessing as mp
import ui_config.config as cfg 

stream = "tcp://localhost:4545"

#Configuration
nrow = cfg.nrows() 
ncol = cfg.ncols()

dtype = np.float32
cdtype = ctypes.c_float

fitterWorkerReady = mp.Value(ctypes.c_bool)
fitterWorkerReady.value = False

accframes = 0
acc_image = np.zeros((nrow,ncol), dtype = dtype)

exit_flag = mp.Value(ctypes.c_bool)
exit_flag.value = False