# New Receiver and Viewer of JUNGFRAU for ED, CCSA-UniWien
This document was updated on 14 Oct 2024

## Table of Contents
- [TEM control activation](#tem-control-activation)
- [Starting the receiver](#starting-the-receiver)
- [Deactivation](#deactivation)
- [Main Functionalities](#main-functionalities)
- [Summing Receiver Controls](#summing-receiver-controls)
- [TEM-control Function](#tem-control-function)
- [File Operation and Redis](#file-operation-and-redis)
- [Data-recording workflow](#data-recording-workflow)
- [Data-recording workflow with Testing version](#data-recording-workflow-with-testing-version)
- [Data-processing notes](#data-processing-notes)
- [Troubleshooting](#troubleshooting)
    - [Launching previous system](#Launching-previous-system)

## TEM Control Activation

### TEM-PC (not needed when you ONLY use the TEM console panel)
1. Activate the TEM server:
   - Open a Miniconda PowerShell Prompt (Anaconda submenu) from the Windows Start Menu.\
      <small>
      > Preferably disable the Quick Edit mode of the command prompt:
       - Right-click on the title bar 
       - Select `Properties` from the dropdown menu.
       - In the `Options` tab, uncheck the box for `Quick Edit Mode`
       - Click `OK`.

      </small>
   - Navigate to `C:\ProgramData\EPOC`
   - Activate the environment:
     ```bash
     conda activate vjem38
     ```
   - Start the TEM server:
     ```bash
     python server_tem.py
     ```
   This must be done **before** starting the GUI below.
2. Follow the below steps depending on the receiver in use:
   
## Starting the Receiver

### A. JUNGFRAUJOCH

#### Server (noether)
1. Login as ```psi``` and switch to the Root User.
2. Start the Jungfraujoch broker:
    ```/opt/jfjoch/bin# ./jfjoch_broker /opt/etc/broker_jf500k.json```
3. For data collection, open a separate terminal and start the Jungfraujoch writer:
   ```/opt/jfjoch/bin/jfjoch_writer -R /data/epoc/storage/jfjoch_test/ tcp://127.0.0.1:5500```

#### CameraPC (hodgkin)
1. To open the JFJ web interface, open the web browser (firefox on hodgkin) and enter ```http://noether:5232/``` in the address bar.
   > This assumes that connection between HODGKIN and NOETHER is up and running.
2. When logged in as `jem2100plus`, ensure that the envireonment is activated, if not run:
   ```mamba activate dev```
3. Configure the detector:
   ```bash
   p config ~/jf.config
   ```
4. Change to the GUI directory:
   ```bash
   cd /home/instruments/jem2100plus/GUI
   ```
5. Confirm you are on the `testing` branch, otherwise switch:
   ```bash
   git branch --contains
   git switch testing
   ```
6. Start the GUI:
   ```bash
   python launch_gui.py -jfj -t -s tcp://noether:5501
   ```
7. To start streaming:
    > Starting the decoding of the streamed data -> Push ```View Stream```
    > Ensure good connection to JFJ -> Push ```Connection to Jungfraujoch```
    > Record the dark frame -> ```Record Full Pedestal``` (Blocking operation so wait until the end)
    > Display decoded frames -> ```Live Stream```

8. To collect data when TEM controls are OFF:
   > Push the button ```Collect``` and stop collection with ```Cancel```

### B. REUSS

#### CameraPC (hodgkin)
1. When logged in as `psi`, the environment has been set up.
2. Configure the detector:
   ```bash
   p config ~/jf.config
   ```
3. Start detector acquisition:
   ```bash
   p start
   ```
4. Change to the receiver directory:
   ```bash
   cd /home/psi/software/v2/reuss/python/reuss
   ```
5. Start the receiver server using 12 threads for e.g.:
   ```bash
   python ReceiverServer.py -t 12
   ```
6. Change to the GUI directory:
   ```bash
   cd /home/psi/software/viewer_2.0/GUI
   ```
7. Switch to the correct branch:
   ```bash
   git switch testing
   ```
   or
   ```bash
   git checkout testing
   ```
8. Confirm you are on the `testing` branch:
   ```bash
   git branch --contains
   ```
9. Start the GUI:
   ```bash
   python launch_gui.py
   ```
   To use TEM control functions, run:
   ```bash
   python launch_gui.py -t
   ```
10. In the Jungfrau_GUI, start streaming without the incident beam by clicking on `View Stream`.
11. Click on `Connect to Receiver`. Once the button turns green, all controls are enabled.
12. Click `Start Stream` to start receiving frames.
13. Adjust the `Acquisition Interval (ms)` in the spinbox. To reduce the delay, set it to `20`. For less logging, increase the value to `50` or `60`.
14. Click `Record Full Pedestal` to subtract dark frames.

   > More details on the receiver controls are in the [Summing Receiver Controls](#summing-receiver-controls) section.

## Deactivation

### CameraPC (hodgkin)
1. Stop the receiver by clicking the `Stop Receiver` pushbutton. This may take several seconds.\
   > If the stop operation fails, open another terminal and kill the process manually:
   ```bash
   ps aux | grep ReceiverServer
   kill -9 [process-id]
   ```
2. Stop streaming and exit the viewer.
3. Abort detector acquistion:
   ```bash
   p stop
   ```

### TEM-PC
1. Open another PowerShell console and kill the corresponding python process:
   ```bash
   Get-Process python
   kill [process-id]
   ```

## Main Functionalities

- `View Stream`: Reads the stream of frames published by the receiver.
- `Apply Auto Contrast`: Dynamically adjusts the contrast of displayed frames.
- `Reset Contrast`: Turn off the auto-contrast and reload preset contrast values (from Redis)
- `Exit`: Disconnects the TEM and exits the GUI.
- `Beam Gaussian Fit`: Starts fitting the beam's elliptical spot shape (non-TEM mode only, useful for manual focusing).
- `Magnification`, `Distance`: Displays the magnification and distance values from the previous recording (TEM mode only). `scale` checkbox displays the scale bar/ring (not works correctly at the moment).
- `Accumulate in TIFF`: Saves a TIFF snapshot to the specified data path.
- `Write Stream in H5`: Saves an HDF movie to the specified data path.

### [Summing Receiver Controls](../jungfrau_gui/screenshot/ver_26Sept2024.PNG.png)
**Important:** The below controls are compatible with the new receiver `~/software/v2/reuss/python/reuss/ReceiverServer.py`.

Main operations:\
- `Connect to Receiver`: Establishes a connection with the receiver. The button turns green if the server script is running.\
- `Start Stream`: Starts streaming assembled and summed frames via ZeroMQ.\
- `Stop Receiver`: Stops the summing receiver. (Note: the stop operation is not always reliable. See [issue #42](https://github.com/slsdetectorgroup/reuss/issues/42).)

More:\
- `Summing Factor`: Set the number of frames to sum.\
- `Set Frames Number`: Sets the number of frames to sum using the summing factor.\
- `Record Full Pedestal`: Records and subtracts the dark frames (equivalent to `r.record_pedestal(1)` in the old receiver).\
- `Record Gain G0`: Records the pedestal for gain G0 (equivalent to `r.record_pedestal(2)`).

### [TEM-control Function](../jungfrau_gui/screenshot/ver_16Aug2024.PNG)

- `Check TEM connection`: Starts communication with TEM. After the connection can be confirmed, **click again** to stop pinging.
- `Get TEM status`: Displays the TEM status in the terminal [with the option of writing status in .log file]
   -`recording`: When checked, allows to save the TEM status in a .log file
- `Click-on-Centring`: (deactivated) Activates stage control by clicking the image.
- `Beam Autofocus`: (Not ready for use) Sweeps IL1 and ILstig values.
- `Rotation`: Starts stage rotation to the target angle. The beam is unblanked during rotation and blanked when rotation ends.
- `with Writer`: Synchronizes the HDF writer with rotation.
- `Auto reset`: Resets the tilt to 0 degrees after rotation.
- `Rotation Speed`: Adjusts rotation speed before starting the rotation. Also updates the `rotation_speed_idx` variable of the Configuration Manager in the data base.
- `Stage Ctrl`: moves the stage in specific direction. \*Rotations are not automatically quicken.

### [File Operation and Redis](../jungfrau_gui/screenshot/ver_24Sept2024.png)

#### Redis Store Settings
- `Experiment Class`: Specifies for whom the data is collected (e.g., UniVie, External, IP).
- `User Name`*: Enter the PI (Person of Interest).
- `Project ID`*: Enter the project identifier.
- `Base Data Directory`: Specifies the root directory for data saving.

**Note:** The [Get] buttons were coded for debugging purposes. They will be removed for the stable version.

#### TIFF Writer
- `Tiff File Name`: Area to define the name of the TIFF file and its index. It contains:\
   <small>
   - First line-edit is read-only and displays the folder where TIFF files are saved.
   - Second line-edit is modifiable (ASCII characters and underscores only) and is meant for the file name.
   - Spinbox is modifiable, is incremented after each writing and represents the index of the written TIFF.

   </small>
- `index`: Set the file index for the TIFF file.
- `Accumulate in TIFF`: Accumulates a specified number of frames in the TIFF file.

#### HDF5 Writer
- `HDF5 Tag`*: Enter the file prefix (ASCII characters and underscores only).
- `index`*: Set the file index for the HDF5 file.
- `H5 Output Path`: Read-only field showing the path where datasets are saved.

**Important:** All the fields with (*) are manually editable. During edition, the entered values/text will be displayed in orange i.e. temporary values. By pressing the [ENTER] key, modifications are confirmed and new values uploaded to the data base.

## Data-recording workflow

1. Set up the beam and stage of TEM.
2. Confirm the data output path on the `H5 Output Path` line-edit.
3. Start stage rotation and immediately click `Write Stream in H5`.
4. Stop writing by pressing ```Stop Writing``` just before the rotation ends.
<!-- 5. When 'Prepare for XDS processing' is checked, the ouput filename is end with '_master.h5' -->
<!-- 6. Modify the 'Acquisition Interval (ms)' -->

## Data-recording workflow with Testing version

1. Set up the beam and stage of TEM.
2. Blank the beam to avoid sample damage.
3. Confirm the data output path on the `H5 Output Path` line-edit.
4. Modify the stage rotation speed and end angle.
5. Check the `with Writer` box.
6. Click `Rotation` to start the rotation and recording.
7. Continue until the end angle is reached or interrupted.
8. Take a TIFF image if needed.

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

## Data-processing notes

- **XDS**:  
    - [Version before 20.Aug.2024](https://github.com/epoc-ed/epoc-utils/commit/2198487645fbb5390e2f629b570ac0dbf18db268) [The plugin derived from Neggia](https://github.com/epoc-ed/DataProcessing/tree/main/XDS/neggia) requires `_master.h5` in the filename. Create a symbolic link:
        ```
        ln -s [full-path-of-hdffile] linked_master.h5
        ```
    - [Version before 10.Oct.2024](https://github.com/epoc-ed/GUI/releases/tag/v2024.10.10) Data stored with float32 format. [Neggia-derived plugin](https://github.com/epoc-ed/DataProcessing/tree/main/XDS/neggia) can work. [Another plugin](https://github.com/epoc-ed/xdslib_epoc-jungfrau/tree/master) can not.
    - [Version after 10.Oct.2024](https://github.com/epoc-ed/GUI/releases/tag/v2024.10.10) Data stored with int32 format and compressed. [Another plugin](https://github.com/epoc-ed/xdslib_epoc-jungfrau/tree/master) can work. [Neggia-derived plugin](https://github.com/epoc-ed/DataProcessing/tree/main/XDS/neggia) can not.

- **DIALS**: Install the [updated Format Class](https://github.com/epoc-ed/DataProcessing/blob/main/DIALS/format/FormatHDFJungfrauVIE02.py) to read the HDF file directly:\
   ``` dials.import [filename.h5] slow_fast_beam_center=257,515 distance=660 ```

## Troubleshooting

- **PowerShell console not responding after disconnecting from GUI**: Open another PowerShell console and kill the python process:

   ```bash
   Get-Process python
   kill [pid]
   ```
- **TEM-control button delay**: There may be a few seconds of delay when responding, especially the first time. Please wait.

### Launching previous system
- Usage of previous rotation commands/scripts under PyJEM3.8 environment
1. Open a Miniconda PowerShell Prompt (Anaconda submenu) from the Windows Start Menu.
1. activate 'vjem38' virtual environment
    ```
   conda activate vjem38
    ```
1. Navigate to `C:\ProgramData\xxxxxx`
1. start python, and load PyJEM module and use the commands
    ```
    python
    >>> from PyJEM import TEM3
    >>> stage = TEM3.Stage3()
    >>> stage.Setf1OverRateTxNum(1)
    >>> stage.SetTiltXAngle(60)
    ```
1. Or just call a python script
    ```
    python rotational_devel.py
    ```
