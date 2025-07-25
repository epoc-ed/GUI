#!/usr/bin/env python3

import sys
import ctypes
import logging
import argparse
import numpy as np
import time
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication

from . import globals
from .ui_components import palette
from .zmq_receiver import ZmqReceiver
from .ui_main_window import ApplicationWindow, get_gui_info

from pathlib import Path
from epoc import ConfigurationClient, auth_token, redis_host

import os
import datetime

class CustomFormatter(logging.Formatter):
    # Define color codes for different log levels and additional styles
    # Foreground (text) colors
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    ORANGE = "\033[38;5;214m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # Bright versions (bold text colors)
    BRIGHT_BLACK = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"

    # Background colors
    BG_BLACK = "\033[40m"
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"
    BG_MAGENTA = "\033[45m"
    BG_CYAN = "\033[46m"
    BG_WHITE = "\033[47m"

    # Text formatting
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    RESET = "\033[0m"
    
    # Define how each log level should be colored
    LOG_COLORS = {
        logging.DEBUG: BLACK,
        logging.INFO: BLUE,
        logging.WARNING: f"{YELLOW}{BOLD}",
        logging.ERROR: RED,
        logging.CRITICAL: f"{RED}{BOLD}",
    }

    def formatTime(self, record, datefmt=None):
        # Convert the record's creation time to a datetime object
        dt = datetime.datetime.fromtimestamp(record.created)
        # Format the time with microseconds, then truncate to milliseconds (3 digits)
        return dt.strftime('%H:%M:%S.%f')[:-3]  # Slice to keep first 6 digits (microseconds -> milliseconds)

    def format(self, record):
        # Get the appropriate color for the log level
        level_color = self.LOG_COLORS.get(record.levelno, self.RESET)
        
        # Format the entire log message (timestamp + levelname + message)
        formatted_message = super().format(record)
        
        # Apply the color to the entire formatted message
        return f"{level_color}{formatted_message}{self.RESET}"

def main():
    os.environ["QT_LOGGING_RULES"] = "qt.core.qobject.connect=false"

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    cfg = ConfigurationClient(redis_host(), token=auth_token())

    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--stream', type=str, default="tcp://noether:5501", help="zmq stream") # default="tcp://localhost:4545"
    parser.add_argument("-d", "--dtype", help="Data type", type = np.dtype, default=np.float32)
    parser.add_argument("-p", "--playmode", action="store_true", help="Activates simplified GUI")
    parser.add_argument("-th", "--temhost", default=cfg.temserver, help="Choose host for tem-gui communication")
    parser.add_argument('-l', '--log', default='INFO', help='Set the logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)')
    parser.add_argument("-f", "--logfile", action="store_true", help="File-output of logging")
    parser.add_argument("-e", "--dev", action="store_true", help="Activate developing function")
    parser.add_argument("-v", "--version", action="store_true", help="Detailed version description")

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
    formatter = CustomFormatter('%(asctime)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)

    # Add the handler to the logger
    logger.addHandler(console_handler)

    if args.logfile:

        # Determine the directory of the script being run
        launch_script_path = Path(sys.argv[0]).resolve().parent
        log_file_path = launch_script_path / f'JFGUI{time.strftime("_%Y%m%d-%H%M%S.log", time.localtime())}'

        logging.info(f"Writing console loggings to: {log_file_path}")  # Debugging line to verify file creation
        
        file_handler = logging.FileHandler(log_file_path.as_posix())
        file_handler.setLevel(log_level)
        file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

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
    globals.tem_mode = not args.playmode
    globals.tem_host = args.temhost
    globals.dev = args.dev
    
    logging.info(f"{get_gui_info()}")

    if args.version:
        logging.info('''
            **Detailed information of authors, years, project name, Github URL, license, contact address, etc.**
            Graphical User Interface for Electron Diffraction with JUNGFRAU (2024-)
            https://github.com/epoc-ed/GUI
            EPOC Project (2024-)
            https://github.com/epoc-ed
            https://epoc-ed.github.io/manual/index.html
        ''')

    Rcv = ZmqReceiver(endpoint=args.stream, dtype=args.dtype) 

    viewer = ApplicationWindow(Rcv, app)
    app_palette = palette.get_palette("dark")
    viewer.setPalette(app_palette)

    viewer.show()
    # QCoreApplication.processEvents()

    sys.exit(app.exec())
if __name__ == "__main__":
    main()
