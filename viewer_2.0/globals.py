import numpy as np
from reuss import config as cfg
import multiprocessing as mp
import ctypes


#Configuration
nrow = cfg.nrows()
ncol = cfg.ncols()

dtype = np.float32 # np.float32 # np.float16

accframes = 0
acc_image = np.zeros((nrow,ncol), dtype = dtype)

exit_flag = mp.Value(ctypes.c_bool)
exit_flag.value = False

# write_hdf5 = False
# hdf5_im = np.zeros((nrow,ncol), dtype = dtype)
# last_frame_written = -1
# image_updated = False 