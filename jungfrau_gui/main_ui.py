#!/usr/bin/env python3

import sys
import ctypes
import logging
import argparse
import numpy as np
import time
from PySide6.QtWidgets import QApplication

from jungfrau_gui.ui_components import palette
from jungfrau_gui.zmq_receiver import ZmqReceiver
from jungfrau_gui.ui_main_window import ApplicationWindow, get_gui_info

from pathlib import Path
from epoc import ConfigurationClient, auth_token, redis_host

import os
import datetime

import textwrap

ABOUT_TEXT = textwrap.dedent("""\
    ┌───────────────────────────────────────────────────────────────────┐
    │  Graphical User Interface for Electron Diffraction (JUNGFRAU GUI) │
    └───────────────────────────────────────────────────────────────────┘

    Project:  EPOC (Electrostatic Potential Of Compounds ─ DOI: 10.55776/I6546)
    Years:    2024–
    Version:  {version}

    Repositories:
      - https://github.com/epoc-ed/GUI
      - https://github.com/epoc-ed

    Documentation:
      - https://epoc-ed.github.io/manual/index.html

    License:
      - MIT License
        This project is distributed under the MIT License.
        See the LICENSE file for the full text.

    Authors & Acknowledgments
    Core contributors:
      - Khalil Ferjaoui — PSI
      - Kiyofumi Takaba — University of Vienna
      - Erik Fröjd — PSI
      - Tim Gruene — University of Vienna
""")

def log_version_info(version: str) -> None:
    logging.info("\n%s", ABOUT_TEXT.format(version=version))


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

    # ---- CLI ----
    parser = argparse.ArgumentParser()
    parser.add_argument("-s", "--stream",   type=str, default=None,
                        help="ZMQ stream endpoint (overrides cfg.receiver_endpoint)")
    parser.add_argument("-d", "--dtype",    type=str, default="float32",
                        help="Data type (float32 or float64)")
    parser.add_argument("-p", "--playmode", action="store_true",
                        help="Activates simplified GUI")
    parser.add_argument("-th", "--temhost", default=None,
                        help="Host for tem-gui communication (overrides cfg.temserver)")
    parser.add_argument("--nrow",           type=int, default=None,
                        help="Override detector rows (overrides cfg.nrows)")
    parser.add_argument("--ncol",           type=int, default=None,
                        help="Override detector cols (overrides cfg.ncols)")
    parser.add_argument("-l", "--log",      default="INFO",
                        help="Set logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")
    parser.add_argument("-f", "--logfile",  action="store_true",
                        help="File-output of logging")
    parser.add_argument("-e", "--dev",      action="store_true",
                        help="Activate developing function")
    parser.add_argument("-v", "--version",  action="store_true",
                        help="Detailed version description")
    args = parser.parse_args()

    # ---- Logger setup ----
    logger = logging.getLogger()
    log_level = getattr(logging, args.log.upper(), None)
    if log_level is None:
        raise ValueError(
            f"Invalid log level: {args.log}. "
            "Choose from DEBUG, INFO, WARNING, ERROR, CRITICAL."
        )
    logger.setLevel(log_level)

    console_handler = logging.StreamHandler()
    formatter = CustomFormatter("%(asctime)s - %(levelname)s - %(message)s")
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if args.logfile:
        launch_script_path = Path(sys.argv[0]).resolve().parent
        log_file_path = launch_script_path / (
            f'JFGUI{time.strftime("_%Y%m%d-%H%M%S.log", time.localtime())}'
        )
        logging.info("Writing console loggings to: %s", log_file_path)
        file_handler = logging.FileHandler(log_file_path.as_posix())
        file_handler.setLevel(log_level)
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S",
        ))
        logger.addHandler(file_handler)

    # ---- dtype ----
    dtype = _parse_dtype(args.dtype)
    cdtype = ctypes.c_float if dtype == np.dtype(np.float32) else ctypes.c_double

    # ---- Redis (mandatory) ----
    try:
        cfg = ConfigurationClient(redis_host(), token=auth_token())
    except Exception as e:
        logging.critical("Cannot connect to Redis configuration server: %s", e)
        sys.exit(1)

    logging.info("Connected to Redis configuration.")

    # ---- Resolve parameters: CLI override  Redis ----
    stream  = args.stream  or cfg.receiver_endpoint
    tem_host = args.temhost or cfg.temserver
    nrow    = args.nrow    if args.nrow is not None else cfg.nrows
    ncol    = args.ncol    if args.ncol is not None else cfg.ncols

    # ---- Initialize globals ----
    from jungfrau_gui import globals

    globals.init(
        stream_=stream,
        dtype_=dtype,
        cdtype_=cdtype,
        tem_mode_=not args.playmode,
        tem_host_=tem_host,
        dev_=args.dev,
        nrow_=nrow,
        ncol_=ncol,
    )

    info = get_gui_info()
    logging.info("%s", info)

    if args.version:
        version = info.removeprefix("Jungfrau GUI ").strip()
        log_version_info(version)
        raise SystemExit(0)

    Rcv = ZmqReceiver(endpoint=stream, dtype=dtype)

    viewer = ApplicationWindow(Rcv, app)
    viewer.setPalette(palette.get_palette("dark"))
    viewer.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
