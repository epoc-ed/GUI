from mss import mss
from mss.base import MSSBase
import numpy as np
import cv2
import time
from datetime import datetime
import threading

# time.sleep(1) # wait for starting
fps_record = 10 # 15
rec_sec = 60 # 10
binning = 1
speed = 2
fps_record = fps_record // speed ## downsizing

monitor_id = 2 # '2' for the lower-left in TEM room. 0 for the upper and 1 for the right.
img = mss(with_cursor=True)
# monitor_id = len(img.monitors) - 1
try:
    mon = img.monitors[monitor_id]
except IndexError:
    print(f'No monitor found for id={monitor_id}')
    exit()

# An area defined to cover the entire GUI window which is adjusted with the top-left corner of the monitor
capture_area = {"top": mon['top'] + 50, "left": mon['left'] + 0, "width": 1500, "height": 1000, "mon": monitor_id}

class ScreenRecorder:
    def __init__(self):
        self.frames = []
        self.running = False
        self.thread = None
        self.max_frames = 600

    def _capture_loop(self):
        with mss() as sct: # (with_cursor=True) as sct:
            while self.running:
                start = time.perf_counter()
                
                img_np = np.array(sct.grab(capture_area))

                self.frames.append(img_np)
                if len(self.frames) > self.max_frames: del self.frames[0]
                
                end = time.perf_counter()

                if end - start < 1/fps_record:
                    time.sleep(1/fps_record-(end - start))

                # for test-use or safety
                if len(self.frames) > self.max_frames*10:
                    self.running = False
    
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()
    
    def start(self):
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._capture_loop)
            self.thread.start()
            
    def save_last_frames(self):
        now = datetime.now()
        filename = f"ScreenCapture_{now.strftime('%Y%m%d_%H%M%S')}.mp4"
        fourcc = cv2.VideoWriter_fourcc('m', 'p', '4', 'v')
        out = cv2.VideoWriter(filename, fourcc, fps_record*speed, (1500//binning, 1000//binning))

        shape = (self.frames[0].shape[0]//binning, binning,
                 self.frames[0].shape[1]//binning, binning, self.frames[0].shape[2])

        for f in self.frames:
            binned = f.reshape(shape).mean(axis=(1,3)).astype(np.uint8)
            img_cv2 = cv2.cvtColor(binned, cv2.COLOR_BGRA2BGR)
            out.write(img_cv2)
        out.release()
        print(f'Capture-movie for last {rec_sec:3d} sec has been saved as {filename}')

if __name__ == "__main__":
    recorder = ScreenRecorder()
    recorder.start()

    try:
        val = input('Press any key to stop recording...')
    except EOFError: # quiet when forcibly shut-down
        recorder.stop()
        exit()

    recorder.stop()
    
    print('Start output-process...')

    if len(recorder.frames) == 0:
        print("No frames captured!!")
        exit()

    recorder.save_last_frames()