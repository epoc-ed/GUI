import json
import logging
# import os.path
from pathlib import Path
import pandas as pd
from pathlib import Path
from importlib_resources import files
# def load_config_files():
#     config = {}
#     _override(config, _load_config("etc/singlaui_config.json"))
#     _override(config, _load_config(os.path.expanduser("~/.config/singlaui_config.json")))
#     return config


def _load_config(path):
    try:
        with open(path) as file:
            config = json.load(file)
            return config
    except FileNotFoundError:
        logging.warning("Could not find config file " + path)
    except PermissionError:
        logging.error("Cannot read config file " + path)
    except json.JSONDecodeError:
        logging.error("Invalid JSON in config file" + path)
    return {}

#TODO! Error handling
f = files('jungfrau_gui').joinpath('ui_components/tem_controls/toolbox/jfgui2_config.json')
parser = json.loads(f.read_text())
#parser = _load_config(Path(__file__).parent/'jfgui2_config.json')

class lut:
    distance = parser['distances']
    magnification = parser['magnification'] # data measured by TG, using Au-grating grid, on 26 Oct 2023
    cl = parser['CL']
    sa = parser['SA']

class path:
    data = Path(parser['data_root'])
    work = Path(parser['work_dir_root'])
    xds  = Path(parser['XDS_template'])
    
def lookup(dic, key, label_search, label_get):
    df_lut = pd.json_normalize(dic)
    try:
        value = df_lut[df_lut[label_search] == key][label_get].iloc[-1]
        return value
    except (TypeError, IndexError):
        logging.warning('Data not in LUT')
        return 0
    
# def _override(destination, source):
#     for key in source.keys():
#         destination[key] = source[key]