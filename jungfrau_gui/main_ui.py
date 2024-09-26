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

class CustomFormatter(logging.Formatter):
    # Define color codes for different log levels
    RED = "\033[31m"
    YELLOW = "\033[33m"
    GREEN = "\033[32m"
    BLUE = "\033[34m"
    RESET = "\033[0m"
    
    # Define how each log level should be colored
    LOG_COLORS = {
        logging.DEBUG: GREEN,
        logging.INFO: BLUE,
        logging.WARNING: YELLOW,
        logging.ERROR: RED,
        logging.CRITICAL: RED,
    }

    def format(self, record):
        # Get the appropriate color for the log level
        level_color = self.LOG_COLORS.get(record.levelno, self.RESET)
        
        # Format the entire log message (timestamp + levelname + message)
        formatted_message = super().format(record)
        
        # Apply the color to the entire formatted message
        return f"{level_color}{formatted_message}{self.RESET}"

def main():
    app = QApplication(sys.argv)
    
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--stream', type=str, default="tcp://localhost:4545", help="zmq stream")
    parser.add_argument("-d", "--dtype", help="Data type", type = np.dtype, default=np.float32)
    parser.add_argument("-t", "--tem", action="store_true", help="Activate tem-control functions")
    parser.add_argument('-l', '--log', default='INFO', help='Set the logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)')

    args = parser.parse_args()

    # Initialize logger
    logger = logging.getLogger()

    # Dynamically set the log level based on args.log
    log_level = getattr(logging, args.log.upper(), None) 
    if log_level is None:
        raise ValueError(f"Invalid log level: {args.log}. Choose from DEBUG, INFO, WARNING, ERROR, CRITICAL.")

    logger.setLevel(log_level)

    # Create the handler for console output
    console_handler = logging.StreamHandler()

    # Apply the custom formatter to the handler
    formatter = CustomFormatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
    console_handler.setFormatter(formatter)

    # Add the handler to the logger
    logger.addHandler(console_handler)

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
