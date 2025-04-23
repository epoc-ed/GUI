import time
from rich import print
import jfjoch_client
# from jfjoch_client.models.plots import Plots

class JungfraujochWrapper:
    """
    Wrapper for the Jungfraujoch python client (jfjoch_client).
    """
    def __init__(self, host):
        # Defining the host is optional and defaults to http://localhost:5232
        # See configuration.py for a list of all supported configuration parameters.
        self.configuration = jfjoch_client.Configuration(
            host = host
        )

        self.api_client = jfjoch_client.ApiClient(self.configuration)
        self.api_instance = jfjoch_client.DefaultApi(self.api_client)
        self._image_time_us = 50000 #100x500us
        self._lots_of_images = 72000 #1h at 20Hz
        self.incident_energy_ke_v = 200

    def cancel(self) -> None:
        """
        Cancel the current data collection. 
        """
        self.api_instance.cancel_post()

    def init(self) -> None:
        """Initialize Jungfraujoch. Run once after startup or when restarting the broker"""
        self.api_instance.initialize_post()

    @property
    def image_time_us(self) -> int:
        """Total image time in microseconds"""
        return self._image_time_us

    @image_time_us.setter
    def image_time_us(self, value : int):
        self._image_time_us = value

    def status(self):
        return self.api_instance.status_get()

    def start(self, n_images : int, 
              fname="", 
              th = 0, 
              beam_x_pxl = 1,
              beam_y_pxl = 1,
              detector_distance_mm = 100,
              incident_energy_ke_v =200,
              wait = False) -> None:
        """Start a measurement.
        
        Parameters
        ----------
        n_images : int
            Number of images to collect

        fname : str
            Filename for the measurement. If empty the measurement will not be saved.

        th : int, default 0
            Threshold for the images. If the pixel value is below this in a sub image it will be set to 0.
            If the value is 0, no thresholding will be done.

        beam_x_pxl : int, default 1
            X position of the beam in pixels
        
        beam_y_pxl : int, default 1
            Y position of the beam in pixels

        detector_distance_mm : float
            Distance from the detector to the sample in mm

        incident_energy_ke_v : float, default 200
            Incident energy in keV

        wait : bool
            If True, wait for the measurement to finish before returning.
        
        
        """
        self.incident_energy_ke_v = incident_energy_ke_v # update instance for spotfinding
        
        ds = jfjoch_client.DatasetSettings(
            image_time_us = self._image_time_us,
            images_per_trigger = n_images,
            beam_x_pxl = beam_x_pxl,
            beam_y_pxl = beam_y_pxl,
            detector_distance_mm = detector_distance_mm,
            incident_energy_ke_v = self.incident_energy_ke_v,
            pixel_value_low_threshold = th,
            file_prefix = fname,
            )

        self.api_instance.start_post(dataset_settings=ds)
        if wait:
            time.sleep(0.3)
            self.wait_until_idle()

    def get_spotfind_status(self) -> bool:
        return self.api_instance.config_spot_finding_get().enable
            
    def set_spotfind(self, enable : bool, 
                signal_to_noise_threshold = 3,
                # photon_count_threshold = 200 * 3,
                max_pix_per_spot = 100,
                min_pix_per_spot = 3,
                high_resolution_limit = 0.5, # jfj limits to >=0.5?
                low_resolution_limit = 3) -> None:
        
        sf = jfjoch_client.SpotFindingSettings(
            enable = enable,
            indexing = False,
            signal_to_noise_threshold = signal_to_noise_threshold,
            photon_count_threshold = self.incident_energy_ke_v * 3,
            max_pix_per_spot = max_pix_per_spot,
            min_pix_per_spot = min_pix_per_spot,
            high_resolution_limit = high_resolution_limit,
            low_resolution_limit = low_resolution_limit,
            indexing_tolerance = 1
            )
        
        self.api_instance.config_spot_finding_put(spot_finding_settings=sf)

    def get_spotplots(self) -> list:
        spot_plots = self.api_instance.plot_spot_count_get(binning=self._lots_of_images//3600, compression=True)
        try:
            return spot_plots.plot[0].y[-1]
        except IndexError:
            return 0

    def collect_pedestal(self, wait = False):
        """Start pedestal collection
        
        Parameters
        ----------
        wait : bool
            If True, wait for the measurement to finish before returning

        """
        self.api_instance.pedestal_post()
        if wait:
            time.sleep(0.3)
            self.wait_until_idle()
            stat = self.api_instance.statistics_calibration_get()
            print(stat)

    def wait_until_idle(self, progress=False) -> None:
        """Wait in a loop until the Jungfraujoch is idle
        
        Parameters
        ----------
        progress : bool
            If True, print progress of the measurement
        
        """
        while True:
            s = self.api_instance.status_get()
            print(s)
            if s.state == 'Idle':
                if progress:
                    print(f'Progress: {100:.0f}%')
                break
            if progress:
                print(f'Progress: {100*s.progress:.0f}%', end = '\r')
            time.sleep(0.1)

    def live(self) -> None:
        """
        Start live mode. I.e. collect many images but do not save them.
        Used for live view when searching for crystals
        """
        self.start(self._lots_of_images)

    def collect(self, fname):
        """Wrapper method to do data collection from the command line.
        Waits for input to start, then records until next input.
        """
        print("Hit enter to start measuring")
        input()
        self.cancel()
        self.wait_until_idle()
        print(f"Starting to record: {fname}")
        self.start(self._lots_of_images, fname = fname)
        print("Hit enter to stop measuring")
        input()
        self.cancel()
        self.wait_until_idle()
        print("Measurement stopped")
        s = self.api_instance.statistics_data_collection_get()
        print(s)
        self.live()
