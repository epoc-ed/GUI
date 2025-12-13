#!/usr/bin/env python3

import sys
import ctypes
import logging
import argparse
import numpy as np
import time
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication

from jungfrau_gui import globals
from jungfrau_gui.ui_components import palette
from jungfrau_gui.zmq_receiver import ZmqReceiver
from jungfrau_gui.ui_main_window import ApplicationWindow, get_gui_info

from pathlib import Path
from epoc import ConfigurationClient, auth_token, redis_host

import os
import datetime

def _cfg_get(cfg, name: str, default=None):
    """
    Safely read a config attribute from ConfigurationClient.

    Some properties (e.g. cfg.temserver) raise ValueError if missing.
    """
    try:
        return getattr(cfg, name)
    except (ValueError, AttributeError):
        return default


def _parse_dtype(dtype_str: str) -> np.dtype:
    s = (dtype_str or "").strip().lower()
    if s in ("float32", "f4", "np.float32"):
        return np.dtype(np.float32)
    if s in ("float64", "double", "f8", "np.float64", "np.double"):
        return np.dtype(np.float64)
    raise ValueError(f"Unknown dtype '{dtype_str}'. Use float32 or float64.")

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
    
    # ---- Command-Line Interface FIRST (no Redis-backed defaults!) ----
    parser = argparse.ArgumentParser()
    parser.add_argument("-s", "--stream", type=str, default="tcp://noether:5501", help="ZMQ stream endpoint",)
    parser.add_argument("-d", "--dtype",  type=str, default="float32", help="Data type (float32 or float64)",)
    parser.add_argument("-p", "--playmode", action="store_true", help="Activates simplified GUI",)
    parser.add_argument("-th", "--temhost", default=None, help="Host for tem-gui communication (defaults to cfg.temserver if set)",)
    parser.add_argument("--nrow", type=int, default=None, help="Override detector rows (defaults to cfg.nrows)",)
    parser.add_argument("--ncol", type=int, default=None, help="Override detector cols (defaults to cfg.ncols)",)
    parser.add_argument("-l", "--log", default="INFO", help="Set logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",)
    parser.add_argument("-f", "--logfile",  action="store_true", help="File-output of logging",)
    parser.add_argument("-e", "--dev", action="store_true", help="Activate developing function",)
    parser.add_argument("-v", "--version", action="store_true", help="Detailed version description",)

    args = parser.parse_args()

    # ---- Logger setup ----
    logger = logging.getLogger()
    log_level = getattr(logging, args.log.upper(), None)
    if log_level is None:
        raise ValueError(
            f"Invalid log level: {args.log}. Choose from DEBUG, INFO, WARNING, ERROR, CRITICAL."
        )
    logger.setLevel(log_level)

    console_handler = logging.StreamHandler()
    formatter = CustomFormatter("%(asctime)s - %(levelname)s - %(message)s")
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if args.logfile:
        launch_script_path = Path(sys.argv[0]).resolve().parent
        log_file_path = launch_script_path / f'JFGUI{time.strftime("_%Y%m%d-%H%M%S.log", time.localtime())}'
        logging.info(f"Writing console loggings to: {log_file_path}")

        file_handler = logging.FileHandler(log_file_path.as_posix())
        file_handler.setLevel(log_level)
        file_formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%H:%M:%S",
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    # ---- Resolve dtype ----
    dtype = _parse_dtype(args.dtype)
    if dtype == np.dtype(np.float32):
        cdtype = ctypes.c_float
    else:
        cdtype = ctypes.c_double

    # ---- Connect to config (Redis) AFTER parsing ----
    cfg = ConfigurationClient(redis_host(), token=auth_token())

    # Resolve TEM host safely (missing key should NOT crash)
    tem_host = args.temhost or _cfg_get(cfg, "temserver", default=None)
    if tem_host is None:
        # pick a sensible fallback; you can change this
        tem_host = "localhost"
        logging.warning("cfg.temserver not set; defaulting tem_host to 'localhost'.")

    # Resolve detector geometry safely
    nrow = args.nrow if args.nrow is not None else _cfg_get(cfg, "nrows", default=None)
    ncol = args.ncol if args.ncol is not None else _cfg_get(cfg, "ncols", default=None)

    if nrow is None or ncol is None:
        raise RuntimeError(
            "Detector geometry missing (nrows/ncols). "
            "Set cfg.nrows/cfg.ncols in Redis or pass --nrow/--ncol."
        )

    # ---- Initialize globals explicitly (NO import-time Redis reads) ----
    from jungfrau_gui import globals

    globals.init(
        stream_=args.stream,
        dtype_=dtype,
        cdtype_=cdtype,
        tem_mode_=not args.playmode,
        tem_host_=tem_host,
        dev_=args.dev,
        nrow_=nrow,
        ncol_=ncol,
    )

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
