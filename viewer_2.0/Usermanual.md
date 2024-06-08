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
1.  ```$ ./viewer_2.py```\
    *\*To use TEM controling functions with Development version, ```$ ./viewer_2.py -t```*
1. Start streaming in the viewer-GUI, without incident beam.
1.  ```>>> r.record_pedestal(1)``` *at the terminal window working on the receiver (srecv)
1. 'Acquisition Interval (ms)' in GUI should be changed to '20' to reduce the dealy.

**\*TEM-PC, NOT needed when you ONLY use the TEM console**
1. Activate relay_server \
Open PowerShell console on TEMPC: C:\ProgramData\SinglaGUI, and start the relay server;
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
#### Main Function
 - 'View Stream': Reads the stream of frames sent by the receiver.
 - 'Auto Contrast': Dynamically adjusts the contrast of the displayed frames.
 - 'Beam Gaussian Fit': Starts the gaussian fitting of the beam elliptical spot shape.
 - 'Exit': Exits the GUI. The connection to TEM is disconnected before exiting.
 -
 
##### *[Function in Development version](screenshot/ver_4Jul2024.png)*

 - 'Magnification', 'Distance': Indicates the current or just previous value of magnification/distance
     - 'scale' for displaying a scale bar for imaging (1 um length) or the Debye-ring for diffraction (1 A circle)
 - 'Rotation Speed': Changes rotation speed settings and indicates the current value
 - 'Start Focus-sweeping': Sweeps IL1 and ILstig values linearly, roughly and finely
 - 'Connect to TEM': Starts communication with TEM.
 - 'Get TEM status': Updates the TEM information and shows in the console. If an hdf file with the defined filename exists, the information will be added to the header.
 - 'Click-on-Centring': Activates stage control by clicking the streaming image (now deactivated)
 - 'Rotation/Record': Starts stage rotation until the input tilt degree (value on the right), reports the setting parapemters, and resets the stage-tilt to 0 deg. when the rotation is stopped.
     - The HDF writer is synchronized when 'Write during rotation' is checked.
 - 
 
***
#### Data-recording workflow with Development version, 4 Jul 2024
1. Setup the beam and stage of TEM for data collection.
1. Define the data output path on the 'H5 Output Path' lineedit. *a '/' at the last part of the path may cause an error.
1. Check 'Write during rotaion'
1. Define the end angle
1. Click 'Rotation/Record' to start the rotation and recording.
1. Rotation/recording can be stopped by clicking 'Stop' (the same button) or interrupption by TEM console. Otherwise the recording will continue until tilted to the end angle.
*\*The frame rate in recording is 50 ms and independent from the value at 'Aquisition Interval'. At this rate, recording with 1 deg/s means 0.05 deg/frame.*
*\*TEM information will be written in the HDF when 'Write during rotaion' is checked.*

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
*\* The complete feasibility (including structure refinement) of the new data has not been established yet on 28th May 2024*
- Read with DIALS:\
    When the Format Class [https://github.com/epoc-ed/DataProcessing/blob/main/DIALS/format/FormatHDFJungfrauVIE01.py] is installed, DIALS can read the HDF directly;\
    ```dials.import ******_master.h5```
- Read with XDS:\
    XDS can read the HDF file with a plugin command 'LIB= [plugin_path]'. A modified Neggia plugin [https://github.com/epoc-ed/DataProcessing/tree/main/XDS/neggia/src/dectris/neggia/plugin] can be used.