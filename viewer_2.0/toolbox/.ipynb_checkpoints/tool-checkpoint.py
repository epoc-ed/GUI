import numpy as np

def d2radius_in_px(d=1, camlen=660, ht=200, pixel=0.075): # angstrom, mm, keV, mm
    h, m0, e, c = 6.62607004e-34, 9.10938356e-31, 1.6021766208e-19, 299792458.0
    voltage = ht*1e3
    wavelength = h/numpy.sqrt(2*m0*e*voltage*(1.+e*voltage/2./m0/c**2)) * 1.e10
    radius = camlen * np.tan(np.arcsin(wavelength/2/d)*2) / pixel
    return radius