# Class for reading .hdf file by JUNGFRAU-for-ED.
# This code was written based on FormatHDF5ESRFJungfrau4M.py
#  prototype on 29-Mar-2024
#  updated on 21-Jul-2024
#  updated on 16-Nov-2024 for JFJ
#  updated on  5-Dec-2024 for JFJ/JF1M
#  updated on 18-Dec-2024 for JFJ/JF1M with metadata
#  updated on  3-Feb-2025 for JFJ/JF1M for multipanel-refinement

from __future__ import annotations
import sys
import h5py
from scitbx.array_family import flex
from scitbx import matrix
from dxtbx import flumpy
from dxtbx.format.FormatHDF5 import FormatHDF5
from dxtbx.model.detector import Detector
import numpy

class FormatHDFJungfrau1MJFJVIE02_multipanel(FormatHDF5):
    # A class to understand electron diffraction images collected on a Jungfrau at University of Vienna.
    _cached_mask = None

    @staticmethod
    def understand(image_file):
        try:
            h = h5py.File(image_file, "r")
        except IOError:
            return False

        if not "/entry" in h:
            return False

        if not "/entry/instrument/optics" in h:
            return False

        keys = list(h["/entry"].keys())
#        if len(keys) > 2: return False # keys should be 'data' and 'instrument'
        d = h["/entry"]
        if "data" in d and "instrument" in d and len(d["data/data_000001"].shape) == 3:
            return True
        return False

    def _start(self):
        super()._start()
        image_file = self.get_image_file()
        self._h5_handle = h5py.File(image_file, "r")
        self.key = list(self._h5_handle.keys())[0] # 'entry'
        self.instrument_name = list(self._h5_handle[self.key]["instrument"].keys())[1] # 'detector'
        instrument = self._h5_handle[self.key]["instrument"][self.instrument_name] # /entry/insrument/detector
        optics = self._h5_handle[self.key]["instrument"]["optics"]
        # self.n_images = instrument["data"].shape[0]
        # self.data_array = self._h5_handle[self.key]["data/data_000001"]
        self.data_array = []
        [self.data_array.extend(self._h5_handle[self.key]["data"][i][()]) for i in self._h5_handle[self.key]["data"]]
        self.data_array = numpy.array(self.data_array)
        self.n_images = self.data_array.shape[0]
        self.oscillation = numpy.round(instrument["frame_time"][()] * self._h5_handle[self.key]["instrument"]["stage/stage_tx_speed_measured"][()], 5) # 0.05
#        self.oscillation = numpy.round(instrument["frame_time"][()] * self._h5_handle[self.key]["instrument"]["stage/velocity_data_collection"][()], 5)
#        self.adus_per_photon = 200 # instrument["detector_information"]["adus_per_photon"]
        self.image_size = tuple(self.data_array.shape[1:])
        h, m0, e, c = 6.62607004e-34, 9.10938356e-31, 1.6021766208e-19, 299792458.0
        voltage = optics["accelerationVoltage"][()]*1e3 # 2e5
        self.adus_per_photon = optics["accelerationVoltage"][()]
        wavelength = h/numpy.sqrt(2*m0*e*voltage*(1.+e*voltage/2./m0/c**2)) * 1.e10 #instrument["beam"]["incident_wavelength"][()]
        distance_nominal = [200, 250, 300, 400, 500, 600, 800, 1000]
        distance_calibrated = [285, 355, 430, 570, 750, 900, 1195, 1490] # extrapolated value for 200!
        x_pixel_size = (
            instrument["x_pixel_size"][()]*1e3 # 0.075 # mm
        )
        y_pixel_size = (
            instrument["y_pixel_size"][()]*1e3 # 0.075 # mm
        )
        distance = (
            distance_calibrated[distance_nominal.index(optics["distance_nominal"][()])]
#            instrument["detector_distance"][()]
        )
        distance = int(self._h5_handle[self.key]["instrument"]["detector/detector_distance"][()])
        beam_center_x = self.data_array.shape[2] / 2 # instrument["detector_information"]["beam_center_x"][()]  # in px
        beam_center_y = self.data_array.shape[1] / 2 # instrument["detector_information"]["beam_center_y"][()]  # in px

        beam_center_x *= x_pixel_size
        beam_center_y *= y_pixel_size
        trusted_range = (0, 1e6
#            instrument["detector_information"]["underload_value"][()],
#            instrument["detector_information"]["saturation_value"][()],
        )
        exposure_time = 1 #instrument["acquisition"]["exposure_time"][()]
        
        # detector definition with two panels
        fast = matrix.col((1.0, 0.0, 0.0))
        slow = matrix.col((0.0, 1.0, 0.0))
        cntr = matrix.col((0.0, 0.0, -distance))
        orig = cntr - float(beam_center_x) * fast - float(beam_center_y) * slow
        self._detector_model = Detector()
        root = self._detector_model.hierarchy()
        root.set_local_frame(fast.elems, slow.elems, orig.elems)
        self.coords = {}
        
        p1 = {"xmin":1, "xmax":1028, "ymin":1,   "ymax":512,  "xmin_mm":1*x_pixel_size, "ymin_mm":1*y_pixel_size}
        p2 = {"xmin":1, "xmax":1028, "ymin":551, "ymax":1062, "xmin_mm":1*x_pixel_size, "ymin_mm":551*y_pixel_size}
        
        for pid, pd in enumerate([p1, p2]):
            panel_name = f"Panel{pid:02d}"
            origin_panel = fast * pd['xmin_mm'] + slow * pd['ymin_mm']
            p = self._detector_model.add_panel()
            p.set_type("UNKNOWN")
            p.set_name(panel_name)
            p.set_raw_image_offset((pd['xmin'], pd['ymin']))
            p.set_image_size((pd['xmax'] - pd['xmin'], pd['ymax'] - pd['ymin']))
            p.set_trusted_range(trusted_range)
            p.set_pixel_size((x_pixel_size, y_pixel_size))
            # p.set_thickness(thickness)
            # p.set_material("Si")
            # p.set_mu(mu)
            # p.set_px_mm_strategy(ParallaxCorrectedPxMmStrategy(mu, t0))
            p.set_local_frame(fast.elems, slow.elems, origin_panel.elems)
            p.set_raw_image_offset((pd['xmin'], pd['ymin']))
            self.coords[panel_name] = (pd['xmin'], pd['ymin'], pd['xmax'], pd['ymax'])        
    
        # self._detector_model = self._detector_factory.simple(
        #     sensor="UNKNOWN",
        #     distance= distance,
        #     beam_centre=(
        #         beam_center_x,
        #         beam_center_y,
        #     ),
        #     fast_direction="+x",
        #     slow_direction="+y",
        #     pixel_size=(
        #         x_pixel_size,
        #         y_pixel_size,
        #     ),
        #     image_size=(self.image_size[1], self.image_size[0]),
        #     trusted_range=trusted_range,
        #     mask=self.get_static_mask(),
        # )
        self._beam_model = self._beam_factory.simple(wavelength)
        self._scan_model = self._scan_factory.make_scan(
            image_range=(1, self.n_images),
            exposure_times=exposure_time,
            oscillation=(0.0, self.oscillation),
            epochs=list(range(self.n_images)),
        )
        # Add a placeholder goniometer model, which has no practical effect on processing as the oscillation is 0.
        # Some dxtbx format logic assumes both or neither scan + goniometer are None for still images
#        self._goniometer_model = self._goniometer_factory.known_axis((-0.906308, 0.422618, 0.0)) # 0, 1, 0
        self._goniometer_model = self._goniometer_factory.known_axis(tuple(-1*self._h5_handle[self.key]["instrument"]["stage/stage_tx_axis"][()]))

    def get_raw_data(self, index=None):
        if index is None:
            index = 0
        # data can be int32 with adus_per_photon != 1.0 or float16 with adus_per_photon == 1.0
        data = (
            (
                # self._h5_handle[self.key]["measurement"]["data"][index]
                self.data_array[index]
                / self.adus_per_photon
            )
            if self.adus_per_photon != 1.0
            # else self._h5_handle[self.key]["measurement"]["data"][index]
            else self.data_array[index]
        )
       # return flex.double(data.astype(float))
    
        self._raw_data = []
        for panel in self.get_detector():
            xmin, ymin, xmax, ymax = self.coords[panel.get_name()]
            self._raw_data.append(flex.int(data.astype(numpy.int32))[ymin:ymax, xmin:xmax])
        return tuple(self._raw_data)

    def get_num_images(self):
        return self.n_images

    def get_beam(self, index=None):
        return self._beam(index)

    def _beam(self, index=None):
        return self._beam_model

    def get_detector(self, index=None):
        return self._detector(index)

    def get_static_mask(self):
        # if FormatHDFJungfrauVIE02._cached_mask is None:
        #     mask = self._h5_handle[self.key]["instrument"][self.instrument_name][
        #         "detector_information"
        #     ]["pixel_mask"]
        #     mask = flumpy.from_numpy(mask[()])
        #     mask_array = mask == 0
        #     FormatHDFJungfrauVIE02._cached_mask = mask_array
        return FormatHDFJungfrau1MJFJVIE02_multipanel._cached_mask

    def _detector(self, index=None):
        return self._detector_model

    def _goniometer(self):
        return self._goniometer_model

    def _scan(self):
        return self._scan_model


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        print(FormatHDFJungfrau1MJFJVIE02_multipanel.understand(arg))

