import numpy as np
from reuss import config as cfg


#Configuration
nrow = cfg.nrows()
ncol = cfg.ncols()

dtype = np.float64 # np.float32 # np.float16

accframes = 0
acc_image = np.zeros((nrow,ncol), dtype = dtype)

# write_hdf5 = False
# hdf5_im = np.zeros((nrow,ncol), dtype = dtype)
# last_frame_written = -1
# image_updated = False 