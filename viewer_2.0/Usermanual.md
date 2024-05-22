# New Receiver and Viewer of JUNGFRAU for ED, CCSA-UniWien
### Usage - This is a draft and should be updated -

#### Activation
**\*CameraPC (hodgkin)**
1. When we login as 'psi', the environment has been setup.
1.  ```$ p config ~/jf.config```
1.  ```$ p start```
1.  ```$ cd /home/psi/software/v2/reuss/build```
1.  ```$ ./srecv -t 12``` \
    *\*Using 12 threads*
1.  ```$ cd /home/psi/software/viewer_2.0/GUI/viewer_2.0```\
    *\*Stable version. Development version is /home/psi/software/viewer_2.0/GUI_temctrl/viewer_2.0*
1.  ```$ ./viewer_2.py```
1. Start streaming in the viewer-GUI, without incident beam.
1.  ```>>> r.record_pedestal(1)```
1. 'Acquisition Interval (ms)' in GUI should be changed to '20' to reduce the dealy.

**\*TEM-PC, NOT needed when you ONLY use the TEM console**
1. Activate relay_server \
Open PowerShell console on TEMPC: C:\ProgramData\SinglaGUI,
```$ python relay_server_testKT.py```  
*\*Will not correctly communicate with the previous version, 'relay_server.py'*  
*\*When the sevrver is stuck, open another PowerShell console and kill the python process*  
```$ Get-Process python```  
```$ kill [pid]```  

#### Deactivation
**\*CameraPC (hodgkin)**
1. Stop streaming and Exit the viewer
1. Stop the receiver from the terminal window. This may take several tens of seconds.\
    ```>>> r.stop()``` \
    ```>>> exit()```
1. ```$ p stop```

**\*TEM-PC**
1. When disconnected from the viewer-GUI, relay_server.py automatically terminates.

***
#### Function
 - 'View Stream': Reads the stream of frames sent by the receiver.
 - 'Auto Contrast': Dynamically adjusts the contrast of the displayed frames.
 -
##### *[Function in Development version](screenshot/ver_12May2024.png)*

 - 'Connect to TEM': Starts communication with TEM. Takes ~10 sec.
 - 'Get TEM status': Updates the TEM information and shows in the console
 - 'Click-on-Centring': Activates stage control by clicking the streaming image
 - 'Start Rotation (+60)': Starts stage rotation until +60 deg., reports the setting parapemters, and resets the stage-tilt to zero when the rotation is stopped.
 - 'Magnification', 'Distance': Indicates the current or just previous value of magnicication/distance
 - 'Rotation Speed': Changes rotation speed settings and indicates the current value
 - 'Beam Gaussian Fit': Starts the gaussian fitting of the beam elliptical spot shape.
 - 'Start Focus-sweeping': Sweeps IL1 and ILstig values linearly, roughly and finely
 - 

***
#### Data-recording workflow, 21 May 2024
1. Setup the beam and stage of TEM for data collection.
1. Define the data output path on the 'H5 Output Path' lineedit.
1. When 'Prepare for XDS processing' is checked, the ouput filename is end with '_master.h5'
1. Modify the 'Acquisition Interval (ms)'
1. Start the stage rotation of TEM for example, and immediately click 'Write Stream in H5'
1. Click 'Stop Writing' right before the rotation ends.

***
#### Data-processing workflow, 21 May 2024
- Read with DIALS:\
    When the Format Class [https://github.com/epoc-ed/DataProcessing/blob/main/DIALS/format/FormatHDFJungfrauVIE01.py] installed, dials can read the HDF directly;\
    ```dials.import ******_master.h5```
- Read with XDS:\
    To be confirmed...