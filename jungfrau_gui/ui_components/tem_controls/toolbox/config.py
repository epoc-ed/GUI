import json
import logging
import pandas as pd #how important is this?
from importlib.resources import files




f = files('jungfrau_gui').joinpath('ui_components/tem_controls/toolbox/jfgui2_config.json')
parser = json.loads(f.read_text())


class lut:
    distance = parser['distances']
    magnification = parser['magnification'] # data measured by KT, using Au-grating grid, on 4 Dec 2024
    cl = parser['CL']
    sa = parser['SA']


def lookup(dic, key, label_search, label_get):
    df_lut = pd.json_normalize(dic)
    try:
        value = df_lut[df_lut[label_search] == key][label_get].iloc[-1]
        return value
    except (TypeError, IndexError):
        logging.warning('Data not in LUT')
        return 0

class others:
    ### will be removed when these are registered in the dataserver
    rotation_axis_theta = 21.8 # parser['rotation_axis_theta']
    pixelsize = 0.075 # parser['pixelsize']
