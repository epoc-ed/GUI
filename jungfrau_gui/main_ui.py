#!/usr/bin/env python3

import sys
import ctypes
import logging
import argparse
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication

from . import globals
from .ui_components import palette
from .zmq_receiver import ZmqReceiver
from .ui_main_window import ApplicationWindow 

# format = "%(message)s"
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

#if __name__ == "__main__":
def main():
    app = QApplication(sys.argv)
    
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--stream', type=str, default="tcp://localhost:4545", help="zmq stream")
    parser.add_argument("-d", "--dtype", help="Data type", type = np.dtype, default=np.float32)
    parser.add_argument("-t", "--tem", action="store_true", help="Activate tem-control functions")
    parser.add_argument('-l', '--log', default='INFO', help='Set the logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)')

    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log.upper(), None), format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')

    if args.dtype == np.float32:
        globals.cdtype = ctypes.c_float
    elif args.dtype == np.double:
        cdtype = ctypes.c_double
    else:
        raise ValueError("unknown data type")

    # Update the type of global variables
    globals.stream = args.stream 
    globals.dtype = args.dtype
    globals.acc_image = np.zeros((globals.nrow,globals.ncol), dtype = args.dtype)
    globals.tem_mode = args.tem

    logging.debug(type(globals.acc_image[0,0]))

    Rcv = ZmqReceiver(endpoint=args.stream, dtype=args.dtype) 

    viewer = ApplicationWindow(Rcv, app)
    app_palette = palette.get_palette("dark")
    viewer.setPalette(app_palette)

    viewer.show()
    # QCoreApplication.processEvents()

    sys.exit(app.exec())
if __name__ == "__main__":
    main()
