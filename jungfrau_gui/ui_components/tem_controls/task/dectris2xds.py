#!/usr/bin/env python3
# https://github.com/tgruene/SinglaGUI/blob/master/dectris2xds/dectris2xds.py
import argparse
import h5py
import numpy as np
# from dectris2xds.fit2d import fitgaussian

class XDSparams:
    """
    Stores parameters for XDS and creates the template XDS.INP in the current directory
    """
    def __init__(self, xdstempl):
        self.xdstempl = xdstempl

    def update(self, orgx, orgy, templ, d_range, osc_range, dist):
        """
           replace parameters for ORGX/ORGY, TEMPLATE, OSCILLATION_RANGE,
           DATA_RANGE, SPOT_RANGE, BACKGROUND_RANGE, STARTING_ANGLE(?)
        """
        self.xdsinp = []
        with open(self.xdstempl, 'r') as f:
            for line in f:
                [keyw, rem] = self.uncomment(line)
                if "ORGX=" in keyw or "ORGY=" in keyw:
                    self.xdsinp.append(f" ORGX= {orgx:.1f} ORGY= {orgy:.1f}\n")
                    continue
                if "ROTATION_AXIS" in keyw:
                    axis = np.fromstring(keyw.split("=")[1].strip(), sep=" ")
                    axis = np.sign(osc_range) * axis
                    keyw = self.replace(keyw, "ROTATION_AXIS=", np.array2string(axis, separator=" ")[1:-1])
                keyw = self.replace(keyw, "OSCILLATION_RANGE=", abs(osc_range))
                keyw = self.replace(keyw, "DETECTOR_DISTANCE=", dist)
                keyw = self.replace(keyw, "NAME_TEMPLATE_OF_DATA_FRAMES=", templ)
                keyw = self.replace(keyw, "DATA_RANGE=", f"1 {d_range}")
                keyw = self.replace(keyw, "SPOT_RANGE=", f"1 {d_range}")
                keyw = self.replace(keyw, "BACKGROUND_RANGE=", f"1 {d_range}")

                self.xdsinp.append(keyw + ' ' + rem)

    def xdswrite(self, filepath="XDS.INP"):
        "write lines of keywords to XDS.INP in local directory"
        with open(filepath, 'w') as f:
            for l in self.xdsinp:
                f.write(l)

    def uncomment(self, line):
        "returns keyword part and comment part in line"
        if ("!" in line):
            idx = line.index("!")
            keyw = line[:idx]
            rem = line[idx:]
        else:
            keyw = line
            rem = ""
        return [keyw, rem]

    def replace(self, line, keyw, val):
        """
        checks whether keyw is present in line (including '=') and replaces the value
        with val
        """
        if (keyw in line):
            line = ' ' + keyw + ' ' + str(val)
        else:
            line = line
        return line


    def getslope(fn):
        """
        extract slope from log file provided as fn; for accurate oscillation value
        """
        print(f" ! Opening file {fn}")
        with open(fn, encoding="utf-8") as log:
            line = log.readline()
            while line.find("=======================") == -1:
                line = log.readline()
                # print (line)
                continue
            slope = log.readline()
            log.close()
        x = slope.split()
        slope = x[2]
        print(f" ! slope: {slope}")
        return float(slope)