"""used for development, otherwise entry point in conda pkg"""
import os
os.environ['HDF5_PLUGIN_PATH']=''
from jungfrau_gui.main_ui import main
main()
