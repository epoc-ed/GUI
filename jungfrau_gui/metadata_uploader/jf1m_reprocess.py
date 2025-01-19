import h5py
import hdf5plugin
import sys
import logging
from metadata_update_server import *

with h5py.File(sys.argv[1], 'r') as f:
    img = f['entry/data/data_000001'][()][100] #, dynamic definition would be better
    beamcenter = np.array([f['entry/instrument/detector/beam_center_x'][()],
                           f['entry/instrument/detector/beam_center_y'][()]]).astype('int')

logging.info(f"Original beam center: {beamcenter[0]:d} {beamcenter[1]:d}")
beamcenter_pre = getcenter(img, center=beamcenter, bin=4, area=100)
beamcenter_refined = getcenter(img, center=beamcenter_pre[0], bin=1, area=20)[0]
logging.info(f"Refined beam center:  {beamcenter_refined[0]:d} {beamcenter_refined[1]:d}")

## XDS, without launching
myxds = XDSparams(xdstempl=sys.argv[2])
myxds.make_xds_file(sys.argv[1], os.path.join("XDS", "XDS.INP"), beamcenter_refined)

## DIALS, python-commands are based on https://github.com/huwjenkins/ed_scripts
mydials = DIALSparams(datapath=sys.argv[1], workdir='./DIALS', beamcenter=beamcenter_refined)
mydials.launch()