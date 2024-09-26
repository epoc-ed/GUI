# New Receiver and Viewer of JUNGFRAU for ED, CCSA-UniWien
This document was updated on 26 Sept 2024
- [Activation](#Activation)
- [Deactivation](#Deactivation)
- [Main Function](#Main-Function)
- [Summing Receiver Controls](#Summing-Receiver-Controls)
- [TEM-control Function](#TEM-control-Function)
- [File-Operation & Redis](#File-Operation-&-Redis)
- [Data-recording workflow](#Data-recording-workflow)
- [Data-recording workflow with Testing version](#Data-recording-workflow-with-Testing-version)
- [Data-procesing notes](#Data-processing-notes,-6-7-Jun-2024)
- [Troubleshooting](#Troubleshooting)

### Activation
**\*TEM-PC, NOT needed when you ONLY use the TEM console panel**
1. Activate the TEM server
   - From the Windows Start Menu, open a Miniconda Powershell Prompt (Anaconda submenu).
   - Change directory to C:\ProgramData\SinglaGUI
   - Type ```$conda activate vjem38```
   - Type ```$ python server_tem.py```
   This must be done **before** starting the GUI below.

**\*CameraPC (hodgkin)**
1. When we login as 'psi', the environment has been setup.
1.  ```$ p config ~/jf.config```
1.  ```$ p start```
1.  ```$ cd /home/psi/software/v2/reuss/build```
1.  ```$ ./srecv -t 12``` \
    *\*Using 12 threads*
1.  ```$ cd /home/psi/software/viewer_2.0/GUI```
    <!-- *\*'PSI' version. 'Testing' version is at /home/psi/software/viewer_2.0/GUI_temctrl/viewer_2.0* \
    *\*'Testing' version will be renamed as 'Stable' version after the bug-fix* -->
1.  ```$ git switch testing``` (or ```$ git checkout testing```)
1.  ```$ git branch --contains```\
    *Confirm you are under the 'testing' branch.*
1.  ```$ python launch_gui.py```\
    *\*To use TEM control functions, ```$ python launch_gui.py -t```*
1. Start streaming in the Jungfrau_GUI, without incident beam.
1.  ```>>> r.record_pedestal(1)``` *at the terminal window where the receiver (srecv) is running\
    ****\*To be more careful of the threshold, reset the value before pedestaling as: ```r.set_threshold(-50)```****
1. 'Acquisition Interval (ms)' in GUI should be changed to '20' to reduce the dealy.


### Deactivation
**\*CameraPC (hodgkin)**
1. Stop streaming and Exit the viewer
1. Stop the receiver from the terminal window. This may take several tens of seconds.\
    ```>>> r.stop()``` 
1. ```$ p stop```

**\*TEM-PC**
1. Open another PowerShell console and kill the corresponding python process\
    ```$ Get-Process python```  
    ```$ kill [process-id]```

***
### Main Function
 - 'View Stream': Reads the stream of frames sent by the receiver.
 - 'Auto Contrast': Dynamically adjusts the contrast of the displayed frames.
 - 'Exit': Exits the GUI. The connection to TEM is disconnected before exiting.
 - ['[A]'](screenshot/ver_21Jun2024.png) at the bottom left of the viewer panel can reset the viewer scale.
 - 'Beam Gaussian Fit': Starts the gaussian fitting of the beam elliptical spot shape.
    - *only at non-tem mode. at the moment, useful as a quantifying indicator for manual-focusing.*
 - 'Magnification', 'Distance': Indicates magnification/distance value obtained at the previous recoring
<!--      - 'scale' for displaying a scale bar for imaging (1 um length) or the Debye-ring for diffraction (1 A circle) -->
    - *only at tem mode.*
 - 'Accumulate in TIFF': Save a tiff-snapshot at the defined data path in lineedit.
 - 'Write Stream in H5': Save an hdf-movie at the defined data path with prefix in lineedits. The output file ends with '_master.h5'.

#### *[Summing Receiver Controls](screenshot/ver_26Sept2024.PNG)*
**Important** The integrated controls of the Summing Receiver are only compatible with the **ReceiverServer.py** script located at **~/software/v2/reuss/python/reuss**.
*\*To run the receiver (also called 'receiver server side'), use the following command:
   ```$ python ReceiverServer.py -t 12```
 - Main operations:
    - 'Connect to Receiver': Pushbutton to establish connection with the receiver (server side).
       *The button turns GREEN when the server script (ReceiverServer.py) is running.
         **Only in this case are the rest of the controls enabled!**
       *The buttons turns RED, if the user has not started the summing receiver server script
       *Errors can be returned on the console in case of 'bad' termination of the ReceiverServer. 
    - 'Start Stream': Relays the ```r.start()``` command and starts the streaming of assembled and summed frames to be received by the viewer through a ZeroMQ socket (for details ref. **zmq_receiver.py** and **reader.py**)
    - 'Stop Receiver': Relays the ```r.stop()``` command and stops the summing receiver.
        **The Stop operation is not reliable ([#issue42 @ repo: slsdetectorgroup/reuss](https://github.com/slsdetectorgroup/reuss/issues/42))
- More operations:
    - 'Summing Factor': Spinbox that accepts an integer value
    - 'Set Frames Number': Relays the ```r.set_frames_to_sum(N)``` with N equal to the integer value in the above spinbox.
    - 'Record Full Pedestal': Relays the ```r.collect_pedestal()``` (eq to ```r.record-pedestal(1)``` in old receiver) which records the full pedestal and substracts the dark frame from each summed frame hence converting raw data into physical data (deposited energy) 
    - 'Record Gain G0': Relays the ```r.tune_pedestal()``` (eq to ```r.record-pedestal(2)``` in old receiver) to record the pedestal for gain G0.
 
#### *[TEM-control Function](screenshot/ver_16Aug2024.PNG)*
 - 'Connect to TEM': (deactivated) Starts communication with TEM.
 - 'Get TEM status': (deactivated) Updates the TEM information and shows in the terminal. If an hdf file with the defined filename exists, the information will be added to the header.
     - 'recording': (deactivated) save the TEM values in the log file in the current directory.
 - 'Click-on-Centring': (deactivated) Activates stage control by clicking the streaming image
 - 'Beam Autofocus': (**! Not ready for use!**) Sweeps IL1 and ILstig values linearly, roughly and finely 
 - 'Rotation': Starts stage rotation until the input tilt degree (in the lower box, 'Target angle'), and reports the setting parameters. When the beam is blanked, it will be unblanked on starting the rotation. When the rotation ends, the beam will be blanked. The rotation can be interrupted either by clicking this button again or touching the tilt button of the TEM console.\
     *'Start angle' only indicates the current value (not real-time) and can not be modified.'*
     - 'with Writer': The HDF writer ('Write Stream in H5') is synchronized with the rotation.
     - 'Auto reset': The stage tilt will be reset to 0 deg after the rotation.
     - 'Rotation Speed': Changes rotation speed settings and indicates the current value.\
     **The rotation speed buttion should be clicked right before starting rotation. [This will be fixed.](https://github.com/epoc-ed/GUI/issues/37)**
 - 'Stage Ctrl': Moves the stage quickly by a constant values.

#### *[File Operations & Redis](screenshot/ver_24Sept2024.PNG)*
 - Section: 'Redis Store Settings'
    - 'Experiment Class': Switch to specify for whom the data are collected. Possible inputs are UniVie, External or IP (Intellectual Property) 
    - 'User Name' **: Line Edit to enter the PI (Person of Interest)
    - 'Project Id' **: Line Edit to specify the project identifier like 'epoc' for the EPOC project
    - 'Base Data Root' **: Specifies the root directory for data saving. Path can be either (i) entered manually (+press Enter) or (ii) chosen by clicking on the "Folder button" after navigating the directory tree.
    **N.B.1** All the [Get] buttons are temporary and for degugging purposes
 - Section: 'TIFF Writer'
    - 'Tiff File name': Line Edit to enter the prefix in the filename 
    - 'index': Spin box to specify the file index in the filename
    - 'Accumulate in TIFF': Button to accumulate a number of frames specified in the neighboring spin box.
 - Section: 'HDF5 Writer'
    - 'HDF5 tag' **: Line Edit to enter the prefix in the filename. Only accepts 7-bit ASCII characters and the underscore (_). No special characters allowed. 
    - 'index' **: Spin box to specify the hdf5 file index. Initially disabled. Can be enabled by checking the "Edit" checkbox.   
    - 'H5 Output Path': Read-only field where the full path to the saved datasets is specified. Cannot be modified and reflects instantaneously any changes made to the Redis Database parameters (ref. the section 'Redis Store Settings')  

**N.B.2** all the fields annoted with the double asterisk (**) represent stored parameters in the Redis database. They are modifiable. Entries will be colored in orange meaning they are being specified i.e. not yet stored in the redis database. To save any changes, you will need to press the Enter key. The theme will then be reset to default (white text over grey background) and changes would been uploaded to the database.
 
***
### Data-recording workflow
<!-- , 21 May 2024 -->
1. Setup the beam and stage of TEM for data collection.
1. Define the data output path on the 'H5 Output Path' lineedit via a folder icon.
1. Start the stage rotation of TEM for example, and immediately click 'Write Stream in H5'
1. Click 'Stop Writing' right before the rotation ends.
<!-- 1. When 'Prepare for XDS processing' is checked, the ouput filename is end with '_master.h5' -->
<!-- 1. Modify the 'Acquisition Interval (ms)' -->

***
### Data-recording workflow with Testing version (*'-t'*)
1. Setup the beam and stage of TEM for data collection.
1. Blank the beam to avoid the sample damage.
1. Confirm/modify the data output path on the 'H5 Output Path' line-edit via a folder icon or manually (but cannot create an inexistent folder).
1. Confirm/modify the stage rotation speed and the end angle of the rotation.
1. Check the 'with Writer' box. Check/uncheck the 'Auto reset' box.
1. Click 'Rotation' button, then start the rotation and recording synchronously.
1. The rotation/recording continues until reaching the end angle or being interrupted.
1. Take a tiff image if you need. The tiff image is not tied with the HDF file at the moment.

<!-- ***
### Data-recording workflow with Development version, 4 Jul 2024
1. Setup the beam and stage of TEM for data collection.
1. Define the data output path on the 'H5 Output Path' lineedit. *a '/' at the last part of the path may cause an error.
1. Check 'Write during rotaion'
1. Define the end angle
1. Click 'Rotation/Record' to start the rotation and recording.
1. Rotation/recording can be stopped by clicking 'Stop' (the same button) or interrupption by TEM console. Otherwise the recording will continue until tilted to the end angle.
*\*The frame rate in recording is 50 ms and independent from the value at 'Aquisition Interval'. At this rate, recording with 1 deg/s means 0.05 deg/frame.*
*\*TEM information will be written in the HDF when 'Write during rotaion' is checked.* -->

***
### Data-processing notes, 6-7 Jun 2024
- Read with XDS:\
    The plugin derived from Neggia one requires '_master.h5' in the input filename, and a symbolic link with the suffix should be additionally prepared (to be corrected).\
    ```[working-directory]$ ln -s [full-path of hdffile] linked_master.h5```
- Read with DIALS:\
    [An updated Format Class](https://github.com/epoc-ed/DataProcessing/blob/main/DIALS/format/FormatHDFJungfrauVIE02.py) must be installed. Then DIALS can read the HDF directly;\
    ```dials.import [filename.h5] slow_fast_beam_center=257,515 distance=660```

<!--
#### Data-processing workflow, 21 May 2024
*\* The complete feasibility (including structure refinement) of the new data has not been established yet on 28th May 2024*
- Read with DIALS:\
    When the Format Class [https://github.com/epoc-ed/DataProcessing/blob/main/DIALS/format/FormatHDFJungfrauVIE01.py] is installed, DIALS can read the HDF directly;\
    ```dials.import ******_master.h5```
- Read with XDS:\
    XDS can read the HDF file with a plugin command 'LIB= [plugin_path]'. A modified Neggia plugin [https://github.com/epoc-ed/DataProcessing/tree/main/XDS/neggia/src/dectris/neggia/plugin] can be used.\
-->

***
### Troubleshooting
- The PowerShell console does not recover after disconnecting to the GUI.\
    *Open another PowerShell console and kill the corresponding python process*\
    ```$ Get-Process python```  
    ```$ kill [pid]```
- **[Fixed]** Hdf files are not output to the defined path.\
    *Modity the H5 Output Path via the folder icon (activates file-browser system).*
- The TEM-control button does not respond immediately.\
    *There will be a delay of a few seconds in responding, especially the first time. Please wait a few moments.*
