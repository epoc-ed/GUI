import numpy as np
import time
import logging
import zmq
import pandas as pd
from scipy import signal
from scipy.optimize import least_squares

from .... import globals

def create_full_mapping(info_queries, more_queries, init_queries, info_queries_client, more_queries_client, init_queries_client):
    """
    Creates a mapping between two sets of queries and their corresponding client-side equivalents.

    # Parameters:
    info_queries : list
        List of primary queries.
    more_queries : list
        List of additional queries.
    init_queries_client : list
        List of queries at starting.
    info_queries_client : list
        Client-side equivalents of primary queries.
    more_queries_client : list
        Client-side equivalents of additional queries.
    init_queries_client : list
        Client-side equivalents of queries at starting.

    # Returns:
    dict: Dictionary mapping queries to their client-side counterparts.
    """
    mapping = {}

    # Mapping for INFO_QUERIES to INFO_QUERIES_CLIENT
    for info_query, client_query in zip(info_queries, info_queries_client):
        mapping[info_query] = client_query

    # Mapping for MORE_QUERIES to MORE_QUERIES_CLIENT
    for more_query, client_query in zip(more_queries, more_queries_client):
        mapping[more_query] = client_query

    # Mapping for INIT_QUERIES to INIT_QUERIES_CLIENT
    for init_query, client_query in zip(init_queries, init_queries_client):
        mapping[init_query] = client_query

    return mapping

# Example usage
INFO_QUERIES = [
    "stage.GetPos", 
    "stage.GetStatus", 
    "eos.GetMagValue", 
    "eos.GetFunctionMode", 
    "defl.GetBeamBlank",
    "stage.Getf1OverRateTxNum"
]

MORE_QUERIES = [
    "stage.GetPos", 
    "stage.GetStatus", 
    "eos.GetMagValue", 
    "eos.GetFunctionMode",
    "stage.Getf1OverRateTxNum",
    "apt.GetSize(1)", 
    "apt.GetSize(4)",  # 1=CL, 4=SA
    "apt.GetKind",
    "apt.GetPosition",
    "eos.GetSpotSize", 
    "eos.GetAlpha", 
    "lens.GetCL3", 
    "lens.GetIL1", 
    "lens.GetOLf",
    "lens.GetIL3", 
    "lens.GetOLc",  # OLf = defocus(fine)
    "defl.GetILs", 
    "defl.GetPLA", 
    "defl.GetBeamBlank",
    "stage.GetMovementValueMeasurementMethod"  # 0=encoder/1=potentio
]

INIT_QUERIES = [
    "ht.GetHtValue",
]

INFO_QUERIES_CLIENT = [
    "GetStagePosition()", 
    "GetStageStatus()", 
    "GetMagValue()", 
    "GetFunctionMode()",
    "GetBeamBlank()", 
    "Getf1OverRateTxNum()"
]

MORE_QUERIES_CLIENT = [
    "GetStagePosition()", 
    "GetStageStatus()", 
    "GetMagValue()", 
    "GetFunctionMode()",
    "Getf1OverRateTxNum()",
    "_send_message(GetApertureSize_CL)", # "GetApertureSize(1)", "GetApertureSize(4)", 
    "_send_message(GetApertureSize_SA)",  # 1=CL, 4=SA
    "_send_message(GetApertureKind)", # "GetApertureKind", 
    "_send_message(GetAperturePosition)", # "GetAperturePosition", 
    "GetSpotSize()", 
    "GetAlpha()", 
    "GetCL3()", 
    "GetIL1()", 
    "GetOLf()",
    "GetIL3()", 
    "GetOLc()",  # OLf = defocus(fine)
    "GetILs()", 
    "GetPLA()", 
    "GetBeamBlank()",
    "GetMovementValueMeasurementMethod()"  # 0=encoder/1=potentio
]

INIT_QUERIES_CLIENT = [
    "_send_message(GetHtValue)", # "ht.GetHtValue", 
]

# Map of Magnification status and correspondent radio button i.e. {Mag_idx : button_idx}
mag_indices = {
    0:0, # 0=MAG     is equivalent to check button 0
    1:0, # 1=MAG2    is equivalent to check button 0
    2:2, # 2=Low MAG is equivalent to check button 2
    4:4  # 4=DIFF    is equivalent to check button 4
}

# Creating the full mapping
full_mapping = create_full_mapping(INFO_QUERIES, MORE_QUERIES, INIT_QUERIES, INFO_QUERIES_CLIENT, MORE_QUERIES_CLIENT, INIT_QUERIES_CLIENT)

def send_with_retries(client_method, *args, retries=3, delay=0.1, **kwargs):
    """
    A reusable method that attempts to call a TEMClient method with retries in case of TimeoutError.

    Parameters:
    - client_method: The TEMClient method to call (e.g., self.client.SetTiltXAngle).
    - *args: Positional arguments to pass to the client method.
    - retries (int): Number of retry attempts before giving up.
    - delay (int): Delay in seconds between retries.
    - **kwargs: Keyword arguments to pass to the client method.

    Returns:
    - The result of the client method if successful.
    
    Raises:
    - TimeoutError: If all retry attempts fail.
    - Exception: Any other exception raised by the client method.
    """
    for attempt in range(retries):
        try:
            logging.info(f"Attempting {client_method.__name__} with args {args} (Attempt {attempt + 1}/{retries})")
            # Dynamically call the method with args and kwargs
            result = client_method(*args, **kwargs)
            return result  # Exit early if successful
        except (TimeoutError, zmq.ZMQError) as e:
            logging.error(f"TimeoutError during {client_method.__name__}: {e}")
            if attempt == retries - 1:
                logging.error(f"Max retry attempts reached for {client_method.__name__}. Giving up.")
                raise
            time.sleep(delay)  # Optional delay between retries
        except Exception as e:
            logging.error(f"Error during {client_method.__name__}: {e}")
            raise  # Raise other exceptions immediately

def eV2angstrom(voltage):
    """
    Converts electron voltages to Angstroms.

    This function computes the wavelength corresponding to a given energy 
    specified in electron volts. The calculation uses fundamental constants:
    - Planck constant (h)
    - Electron mass (m0)
    - Elementary charge (e)
    - Speed of light (c)
    
    The result is returned in Angstroms, which are used to describe atomic scale lengths.
    """
    h, m0, e, c = 6.62607004e-34, 9.10938356e-31, 1.6021766208e-19, 299792458.0
    return h/np.sqrt(2*m0*e*voltage*(1.+e*voltage/2./m0/c**2)) * 1.e10

def d2radius_in_px(d=1, camlen=660, ht=200, pixel=0.075):  # d in Angstroms, camlen in mm, ht in keV, pixel in mm
    """
    Calculates the radius of an electron diffraction pattern in pixels.
    
    Inputs:
    - d: Interplanar spacing in Angstroms.
    - camlen: Camera length in millimeters.
    - ht: High tension or acceleration voltage in kiloelectron volts.
    - pixel: Pixel size in millimeters.
    
    This function first converts the high tension (acceleration voltage) to a wavelength using the 
    eV2angstrom function. It then calculates the diffraction angle and converts this to the radius 
    of the diffraction pattern in pixels using the camera's geometry.
    """
    wavelength = eV2angstrom(ht * globals.KV_TO_V)
    radius = camlen * np.tan(np.arcsin(wavelength / 2 / d) * 2) / pixel
    return radius

    return radius

def radius_in_px2d(px_radius, camlen=660, wavelength=0.02508, pixel=0.075):
    d = wavelength / 2 / np.sin(np.arctan(px_radius * pixel / camlen)/2)
    return d

def estimate_resolution_from_spots(spots, center, camlen=660, wavelength=0.02508, pixel=0.075):
    if len(spots) < 5: return 99
    spots = pd.DataFrame(spots, dtype=float)
    px_radius = ((spots['x']-center[0])**2 + (spots['y']-center[1])**2)**0.5
    d = wavelength / 2 / np.sin(np.arctan(px_radius * pixel / camlen)/2)
    return np.median(np.sort(d)[:5])

def update_spots_to_df(spots, center, camlen=660, ht=200, pixel=0.075):
    wavelength = eV2angstrom(ht*lobals.KV_TO_V)
    df_spots = pd.DataFrame(spots, dtype=float)
    px_radius = ((df_spots['x']-center[0])**2 + (df_spots['y']-center[1])**2)**0.5
    df_spots['d'] = wavelength / 2 / np.sin(np.arctan(px_radius * pixel / camlen)/2)
    df_spots['theta'] = np.arctan2(df_spots['y']-center[1], df_spots['x']-center[0])
    return df_spots

def count_electrons(image, magnification, cutoff=50, bins=20, ht=200, fps=20, pixel=0.075):
    # estimate the number of incoming electrons with the most frequent bin of the histogram.    
    cutoff = cutoff / (globals.default_HT / globals.KV_TO_V) * ht
    image_deloverflow = image[np.where(image < np.iinfo('int32').max-1)]
    low_thresh, high_thresh = np.percentile(image_deloverflow, (1, 99.999))
    data_sampled = image_deloverflow[np.where((image_deloverflow < high_thresh)&(image_deloverflow > cutoff))]
    if len(data_sampled) < 1e4:
        # logging.warning('Number of sampling pixels is less than 1% (<1e4 pixels)!')
        return len(data_sampled), 0, 0, 0
    try:
        hist, bins = np.histogram(data_sampled, density=True, bins=bins)
        delta = (bins[1]-bins[0])/2
        xr = np.linspace(np.min(bins[1:])+delta,np.max(bins[1:])-delta,len(bins[1:])-1)
        approximate_average_count = xr[np.argmax(hist[1:])]
        e_per_A2 = approximate_average_count / ht * fps / ((pixel*1e7)**2) # per sec
        pa_per_cm2 = 1/6.241*e_per_A2*1e10 # per sec => ampere, OK
        return len(data_sampled), approximate_average_count, pa_per_cm2, e_per_A2 * magnification**2
    except ValueError as e:
        # logging.warning(e)
        return len(data_sampled), 0, 0, 0, e

def normalize(v):
    return v / np.linalg.norm(v)

def rotation_matrix(axis, angle_deg):
    angle_rad = np.deg2rad(angle_deg)
    axis = normalize(axis)
    x, y, z = axis
    c = np.cos(angle_rad)
    s = np.sin(angle_rad)
    C = 1 - c

    # Rodrigues' rotation matrix
    R = np.array([
        [c + x*x*C,     x*y*C - z*s, x*z*C + y*s],
        [y*x*C + z*s, c + y*y*C,     y*z*C - x*s],
        [z*x*C - y*s, z*y*C + x*s, c + z*z*C    ]
    ])
    return R

def rotate_coords(coords_with_angles, axis):
    coords_3d = np.hstack([coords_with_angles[:, :2], np.zeros((coords_with_angles.shape[0], 1))])  # (N, 3)
    angles = coords_with_angles[:, 2]

    rotated_coords = []
    for coord, angle in zip(coords_3d, angles):
        R = rotation_matrix(axis, angle)
        rotated = R @ coord
        rotated_coords.append(rotated)

    return np.array(rotated_coords)

def radial_integration(image, ellipse, roundness=0, resolution_px=40, order_peakpick=5):
    X, Y = np.meshgrid(np.arange(image.shape[1]), np.arange(image.shape[0]))
    X = X - ellipse[0][0]
    Y = Y - ellipse[0][1]
    if roundness == 1:
        radius = (X ** 2 + Y ** 2) ** 0.5
    else:
        ellipticity = np.max([ellipse[1][0] / ellipse[1][1], roundness])
        angle = np.deg2rad(ellipse[2])
        preX = X * np.cos(-angle) - Y * np.sin(-angle)
        preY = X * np.sin(-angle) + Y * np.cos(-angle)
        rotX = preX / ellipticity * np.cos(angle) - preY * np.sin(angle)
        rotY = preX / ellipticity * np.sin(angle) + preY * np.cos(angle)
        radius = (rotX ** 2 + rotY ** 2) ** 0.5

    RadInt = pd.DataFrame({'radius': np.ravel(radius), 'intensity': np.ravel(image)})
    RadInt = RadInt.sort_values('radius')

    radsize = image.shape[0]//resolution_px*image.shape[1]//resolution_px
    ulim_list = np.linspace(np.min(RadInt['radius']) - 0.1, np.max(RadInt['radius']), radsize)
    cut = pd.cut(RadInt['radius'], bins=ulim_list)
    RadInt = RadInt.groupby(cut, observed=False).mean()
    peakids = signal.argrelmax(np.array(RadInt['intensity']), order=order_peakpick)[0]
    return np.array(RadInt['radius']), np.array(RadInt['intensity']), peakids

def ellipse_residuals(params, x, y):
    x0, y0, a, b, theta = params
    return ((x - x0)*np.cos(theta) + (y - y0)*np.sin(theta))**2/a**2 + \
           ((x0 - x)*np.sin(theta) + (y - y0)*np.cos(theta))**2/b**2 - 1

def fitellipse(x, y):
    centerx, centery = np.mean(x), np.mean(y)
    r0 = np.mean(((x-centerx)**2+(y-centery)**2)**0.5)
    initial_values = [centerx, centery, r0, r0, 0]
    result = least_squares(ellipse_residuals, initial_values, args=(x, y))
    return result.x