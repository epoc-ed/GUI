import json
import logging
import pandas as pd
from importlib.resources import files
from pathlib import Path

import numpy as np
import re
from scipy.interpolate import griddata

import pyqtgraph as pg
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsRectItem
from PySide6.QtCore import QRectF

from epoc import ConfigurationClient, auth_token, redis_host
from .... import globals
from glob import glob

f = files('jungfrau_gui').joinpath('ui_components/tem_controls/toolbox/jfgui2_config.json')
parser = json.loads(f.read_text())
cfg = ConfigurationClient(redis_host(), token=auth_token())

temvalue_files = sorted(glob('jungfrau_gui/ui_components/tem_controls/toolbox/TEMvalues_*.json'))

if len(temvalue_files) > 0:
    temvalue_f = Path(temvalue_files[-1]) # the newest one is referred
    distance_new = [item for item in json.loads(temvalue_f.read_text())]

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
        self.raw_grid = np.delete(self.array_data, [2, 5, 6, 7], -1)[:-3,:] # remove date, unit and brightness
        self.data_grid = np.array([[int(nominal[:-2])*10, int(ht_value), int(mag), float(calibrated)] for nominal, calibrated, ht_value, mag in self.raw_grid])
        try:
            self.newer_grid = np.array([list(d.values()) for d in distance_new])[:,[1,3,4,6]]
            self.data_grid = np.array([[int(nominal[:-2])*10, float(ht_value)*1e3, int(mag), float(calibrated)] for ht_value, mag, nominal, calibrated in self.newer_grid])
        except NameError:
            pass

    def _lookup(self, dic, key, label_search, label_get, index=0):
        df_lut = pd.json_normalize(dic)
        try:
            value = df_lut[df_lut[label_search] == key][label_get].iloc[index]
            return value
        except (TypeError, IndexError):
            logging.warning(f'Data not in LUT: {label_search} for {key}')
            return 0

    def interpolated_distance(self, nominal, ht_value_kV, mag=15000):
        beam = np.array([int(nominal[:-2])*10, ht_value_kV*globals.KV_TO_V, mag])
        interpolated_distance = griddata(self.data_grid[:, [0,1,2]], self.data_grid[:, -1], beam, method='linear')
        if np.isnan(interpolated_distance[0]):
            logging.info(f'Interpolation failed for {nominal}/{ht_value_kV}/{mag}. Calibrated value returns instead.')
            return self.calibrated_distance(nominal)
        else:
            return interpolated_distance[0]
        
    def calibrated_distance(self, key_search):
        calibrated = self._lookup(self.distance, key_search, 'displayed', 'calibrated')
        if calibrated != 0:
            return calibrated
        else:
            logging.warning('Unregistered value. Nominal value returns instead!')
            return int(key_search[:-2])*10

    def calibrated_magnification(self, key_search):
        return self._lookup(self.magnification, key_search, 'displayed', 'calibrated')

    def cl_size(self, key_search):
        return self._lookup(self.cl, key_search, 'ID', 'size')

    def sa_size(self, key_search):
        return self._lookup(self.sa, key_search, 'ID', 'size')

    def mag_to_selectorid(self, mag_search):
        try:
            if mag_search >= 1e4:
                key_search = f"X{mag_search/1e3:.0f}k"
            else:
                key_search = f"X{mag_search:.0f}"
        except TypeError:
            return 0
        return self._lookup(self.magnification, key_search, 'displayed', 'selector_id')

    def distance_to_selectorid(self, distance_search):
        try:
            key_search = f"{distance_search/10:.0f}cm"
        except TypeError:
            return 0
        return self._lookup(self.distance, key_search, 'displayed', 'selector_id')

    def shiftoverlay_for_ht(self, ht_in_V, magnification=1200):
        if magnification >= globals.min_mag_for_mag: # mag
            return self._lookup(self.ht_mag_specific, ht_in_V, 'ht_voltage', 'overlay_xy', index=0)
        else:
            return self._lookup(self.ht_mag_specific, ht_in_V, 'ht_voltage', 'overlay_xy', index=-1)

    def rotaxis_for_ht(self, ht_in_V, magnification=20000):
        if magnification >= globals.min_mag_for_mag: # mag
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
        item_rect.setFlag(QGraphicsEllipseItem.ItemIsMovable)
        item_rect.setFlag(QGraphicsEllipseItem.ItemIsSelectable)

        return item_circle, item_rect, item_common

    def lowmagjump_for_ht(self, ht_in_V):
        x, y = self._lookup(self.ht_mag_specific, ht_in_V, 'ht_voltage', 'overlay_xy', index=-1)
        w, h = self._lookup(self.ht_mag_specific, ht_in_V, 'ht_voltage', 'overlay_wh', index=-1)
        return x+w/2, y+h/2
    
def pos2textlist():
    textlist = []
    for i in lut.positions:
        textlist.append(f"{i['ID']:3d}:{i['xyz'][0]:7.1f}{i['xyz'][1]:7.1f}{i['xyz'][2]:7.1f}, {i['status']}")
    return textlist