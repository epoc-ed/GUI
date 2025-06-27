import numpy as np
import time
import logging
import zmq

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
    wavelength = eV2angstrom(ht * 1e3)
    radius = camlen * np.tan(np.arcsin(wavelength / 2 / d) * 2) / pixel
    return radius