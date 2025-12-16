import time
import numpy as np
import logging
import pyqtgraph as pg

from PySide6.QtWidgets import QGraphicsEllipseItem
from PySide6.QtCore import QRectF, Signal, Qt, QMetaObject

from simple_tem import TEMClient
from epoc import ConfigurationClient, auth_token, redis_host
from .task import Task
from .... import globals
from ...tem_controls.toolbox import config as cfg_jf

import warnings
warnings.simplefilter('error', category=RuntimeWarning)

"""
   move the identified beam center to the defined detector origin
"""

class CenterBeamTask(Task):
    def __init__(self, control_worker):
        super().__init__(control_worker, "BeamCentering")
        self.conrol = control_worker
        self.mainwindow = self.control.tem_action.parent
        self.client = TEMClient(globals.tem_host, globals.tem_port, verbose=True)
        self.cfg = ConfigurationClient(redis_host(), token=auth_token())
        self.target = np.array(cfg_jf.lut.optical_axis_center)
        self.diff_vector = np.array(self.cfg.beam_center) - self.target
        self.distance = np.linalg.norm(self.diff_vector)
        self.wait_s = globals.wait_time_s_bc
        self.threshold = globals.threshold_bc
        self.retry_n = globals.max_retries_bc
        self.init_dplaxy = np.array(globals.dPLAxy0_bc).astype(int)
        self.max_dpla = globals.max_dPLA_bc

    def center_beam_by_pla(self, dplaxy):
        wait_s = self.wait_s
        diff0 = self.diff_vector
        plax0, play0 = self.client.GetPLA()
        logging.info(f'Step of this trial is {dplaxy}')
        
        ## calc beamshift / pla_x
        self.client._send_message("SetPLA", int(plax0+dplaxy[0]), play0)
        time.sleep(wait_s)
        self.diff_vector = np.array(self.cfg.beam_center) - self.target
        dxy_dplax = (self.diff_vector - diff0) / dplaxy[0]
        
        try:
            dplax_aim = -np.dot(diff0, dxy_dplax) / np.linalg.norm(dxy_dplax)**2
        except (ZeroDivisionError, RuntimeWarning):
            dplax_aim = 0

        ## calc beamshift / pla_y
        self.client._send_message("SetPLA", plax0, int(play0+dplaxy[1]))
        time.sleep(wait_s)
        self.diff_vector = np.array(self.cfg.beam_center) - self.target
        dxy_dplay = (self.diff_vector - diff0) / dplaxy[1]
        try:
            dplay_aim = -np.dot(diff0, dxy_dplay) / np.linalg.norm(dxy_dplay)**2
        except (ZeroDivisionError, RuntimeWarning):
            dplay_aim = 0
        
        logging.info(f'Calculated dPLA: {dplax_aim:.1f}, {dplay_aim:.1f}')
        if np.abs(dplax_aim) > self.max_dpla or np.abs(dplay_aim) > self.max_dpla:
            logging.warning('Vector too large!!')
            return None
        self.client._send_message("SetPLA", int(plax0+dplax_aim), int(play0+dplay_aim))
        time.sleep(wait_s)
        self.diff_vector = np.array(self.cfg.beam_center) - self.target
        
        if np.linalg.norm(self.diff_vector) < self.threshold:
            logging.info(f'Beam is now close enough to the target (dpx < {self.diff_vector}).')
            return None
        else:
            return np.max([(self.diff_vector/diff0 * dplaxy).astype(int), np.array([30, 30])], axis=0)
    
    def run(self):
        self.mainwindow.extensions.center_button.setText("Running")
        self.mainwindow.extensions.center_button.started = True
        
        self.beamtrace_overlay = []

        # move beam to center by using plaxy
        dplaxy = self.init_dplaxy
        for i in range(self.retry_n):
            logging.info(f'Beam Centring: N=({i+1})')
            center = self.cfg.beam_center
            self.mainwindow.roi.setPos([center[0]-75, center[1]-50])
            overlay = QGraphicsEllipseItem(QRectF(center[0]-2, center[1]-2, 4, 4))
            overlay.setPen(pg.mkPen('w', width=2))
            self.mainwindow.plot.addItem(overlay)
            self.beamtrace_overlay.append(overlay)
            dplaxy = self.center_beam_by_pla(dplaxy = dplaxy)
            if dplaxy is None:
                break
        
        time.sleep(self.wait_s)
        [self.mainwindow.plot.removeItem(i) for i in self.beamtrace_overlay]

        # Restarting TEM polling
        if not self.control.tem_action.tem_tasks.connecttem_button.started:
            QMetaObject.invokeMethod(self.control.tem_action.tem_tasks.connecttem_button, "click", Qt.QueuedConnection)
        
        self.mainwindow.extensions.center_button.setText("Center")
        self.mainwindow.extensions.center_button.started = False