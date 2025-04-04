import json
import logging
import pandas as pd
from importlib.resources import files

import numpy as np
import re
from scipy.interpolate import griddata

import pyqtgraph as pg
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsRectItem
from PySide6.QtCore import QRectF

from epoc import ConfigurationClient, auth_token, redis_host

f = files('jungfrau_gui').joinpath('ui_components/tem_controls/toolbox/jfgui2_config.json')
parser = json.loads(f.read_text())
cfg = ConfigurationClient(redis_host(), token=auth_token())

class lut:
    distance = parser['distances']
    magnification = parser['magnification'] # data measured by KT, using Au-grating grid, in Dec 2024 
    cl = parser['CL']
    sa = parser['SA']
    positions = parser['position']
    ht_mag_specific = parser['ht_mag_specific']
    optical_axis_center = parser['optical_axis_center']

    def __init__(self):
        self.array_data = np.array([list(d.values()) for d in self.distance])
        self.raw_grid = np.delete(self.array_data, [2, 4, 5, 6], -1)[:-3,:] # remove date, unit, mag, and brightness at the moment
        self.data_grid = np.array([[int(nominal[:-2])*10, int(ht_value), float(calibrated)] for nominal, calibrated, ht_value in self.raw_grid])

    def _lookup(self, dic, key, label_search, label_get, index=0):
        df_lut = pd.json_normalize(dic)
        try:
            value = df_lut[df_lut[label_search] == key][label_get].iloc[index]
            return value
        except (TypeError, IndexError):
            logging.warning(f'Data not in LUT: {label_search} for {key}')
            return 0

    def interpolated_distance(self, nominal, ht_value_kV):
        beam = np.array([int(nominal[:-2])*10, ht_value_kV*1e3])
        interpolated_distance = griddata(self.data_grid[:, :-1], self.data_grid[:, -1], beam, method='linear')
        if np.isnan(interpolated_distance[0]):
            logging.info('Interpolation failed. Calibrated value returns instead.')
            return self._lookup(self.distance, nominal, 'displayed', 'calibrated')
        else:
            return interpolated_distance[0]
        
    def calibrated_distance(self, key_search):
        return self._lookup(self.distance, key_search, 'displayed', 'calibrated')
        
    def calibrated_magnification(self, key_search):
        return self._lookup(self.magnification, key_search, 'displayed', 'calibrated')

    def cl_size(self, key_search):
        return self._lookup(self.cl, key_search, 'ID', 'size')

    def sa_size(self, key_search):
        return self._lookup(self.sa, key_search, 'ID', 'size')

    def shiftoverlay_for_ht(self, ht_in_V, magnification=1200):
        if magnification > 1500: # mag
            return self._lookup(self.ht_mag_specific, ht_in_V, 'ht_voltage', 'overlay_xy', index=0)
        else:
            return self._lookup(self.ht_mag_specific, ht_in_V, 'ht_voltage', 'overlay_xy', index=-1)

    def rotaxis_for_ht(self, ht_in_V, magnification=20000):
        if magnification > 1500: # mag
            return self._lookup(self.ht_mag_specific, ht_in_V, 'ht_voltage', 'axis_xds', index=0)
        else:
            return self._lookup(self.ht_mag_specific, ht_in_V, 'ht_voltage', 'axis_xds', index=-1)

    def rotaxis_for_ht_degree(self, ht_in_V, magnification=20000):
        vector = self.rotaxis_for_ht(ht_in_V, magnification)
        return np.rad2deg(np.arctan(vector[1]/vector[0])) * -1

    def overlays_for_ht(self, ht_in_V):
        x, y = self._lookup(self.ht_mag_specific, ht_in_V, 'ht_voltage', 'overlay_xy', index=0)
        r = self._lookup(self.ht_mag_specific, ht_in_V, 'ht_voltage', 'overlay_wh', index=0)[0]
        item_circle = QGraphicsEllipseItem(QRectF(x-r, y-r, 2*r, 2*r))
        item_circle.setPen(pg.mkPen('r', width=2))

        r = cfg.overlays[0]['radius']
        item_common = QGraphicsEllipseItem(QRectF(x-r, y-r, 2*r, 2*r))
        item_common.setPen(pg.mkPen('r', width=2))
        
        x, y = self._lookup(self.ht_mag_specific, ht_in_V, 'ht_voltage', 'overlay_xy', index=-1)
        w, h = self._lookup(self.ht_mag_specific, ht_in_V, 'ht_voltage', 'overlay_wh', index=-1)
        item_rect = QGraphicsRectItem(QRectF(x, y, w, h))
        item_rect.setPen(pg.mkPen('r', width=2))

        return item_circle, item_rect, item_common
    
def pos2textlist():
    textlist = []
    for i in lut.positions:
        textlist.append(f"{i['ID']:3d}:{i['xyz'][0]:7.1f}{i['xyz'][1]:7.1f}{i['xyz'][2]:7.1f}, {i['status']}")
    return textlist
  
class others:
    ### will be removed when these are registered in the dataserver
    # rotation_axis_theta = 21.8 # parser['rotation_axis_theta']
    # rotation_axis_theta_lm1200x = 52.86 # hopefully be replaced with values for each mag
    pixelsize = 0.075 # parser['pixelsize']
    backlash = [100, 80, 0, 0] #x, y, z, tx [nm, deg.] undefined for z and tx