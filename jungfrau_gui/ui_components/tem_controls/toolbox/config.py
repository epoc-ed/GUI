import json
import logging
import pandas as pd
from importlib.resources import files

import numpy as np
import re
from scipy.interpolate import griddata

f = files('jungfrau_gui').joinpath('ui_components/tem_controls/toolbox/jfgui2_config.json')
parser = json.loads(f.read_text())

class lut:
    distance = parser['distances']
    magnification = parser['magnification'] # data measured by KT, using Au-grating grid, in Dec 2024 
    cl = parser['CL']
    sa = parser['SA']
    positions = parser['position']

    def __init__(self):
        self.array_data = np.array([list(d.values()) for d in self.distance])
        self.raw_grid = np.delete(self.array_data, [2, 4, 5], -1)[:-3,:] # remove date, unit, and mag
        self.data_grid = np.array([[int(nominal[:-2])*10, int(ht_value), float(calibrated)] for nominal, calibrated, ht_value in self.raw_grid])

    def _lookup(self, dic, key, label_search, label_get):
        df_lut = pd.json_normalize(dic)
        try:
            value = df_lut[df_lut[label_search] == key][label_get].iloc[-1]
            return value
        except (TypeError, IndexError):
            logging.warning(f'Data not in LUT: {label_search} for {key}')
            return 0

    def interpolated_distance(self, nominal, ht_value_kV):
        beam = np.array([int(nominal[:-2])*10, ht_value_kV*1e3])
        interpolated_distance = griddata(self.data_grid[:, :-1], self.data_grid[:, -1], beam, method='linear')
        if np.isnan(interpolated_distance[0]):
            logging.info('Interporation failed. Calibrated value returns instead.')
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


def pos2textlist():
    textlist = []
    for i in lut.positions:
        textlist.append(f"{i['ID']:3d}:{i['xyz'][0]:7.1f}{i['xyz'][1]:7.1f}{i['xyz'][2]:7.1f}, {i['status']}")
    return textlist
  
class others:
    ### will be removed when these are registered in the dataserver
    rotation_axis_theta = 21.8 # parser['rotation_axis_theta']
    rotation_axis_theta_lm1200x = 52.86 # hopefully be replaced with values for each mag
    pixelsize = 0.075 # parser['pixelsize']
    backlash = [100, 80, 0, 0] #x, y, z, tx [nm, deg.] undefined for z and tx