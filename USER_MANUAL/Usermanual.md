# New Receiver and Viewer of JUNGFRAU for ED, CCSA-UniWien
This document was updated on 13 Feb 2025\
**When you encounter bug-like behaviors, please check [known bugs](#Known-bugs).**

## Table of Contents
- [TEM control activation](#tem-control-activation)
- [Starting the Jungfraujoch receiver](#starting-the-jungfraujoch-receiver)
- [Deactivation](#deactivation)
- [Main Functionalities](#main-functionalities)
- [Summing Receiver Controls](#summing-receiver-controls)
- [TEM-control Function](#tem-control-function)
- [File Operation and Redis](#file-operation-and-redis)
- [Data-recording workflow](#data-recording-workflow)
- [Data-processing notes](#data-processing-notes)
- [Troubleshooting](#troubleshooting)
    - [Known bugs (13 Dec 2024)](#Known-bugs)
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

**⚠️ The above Step 1. needs to be done before starting the GUI below.**

2. Follow the below steps.
   
## Starting the JUNGFRAUJOCH Receiver

#### Server (NOETHER)
**⚠️ In the below, Steps 1. and 2. depict the manual start up of the Jungfraujoch backend.**\
**As of 2025-01-24, these steps are no longer necessary as the broker and writer scripts are rare started automatically at boot time of NOETHER.**

1. Login as ```psi``` and switch to the **root** user.

2. Start the Jungfraujoch broker:

   ``` bash
   /opt/jfjoch/bin/jfjoch_broker /opt/etc/broker_jf500k.json
   ```

3. For data collection, open a separate terminal and start the Jungfraujoch writer:

   ``` bash
   /opt/jfjoch/bin/jfjoch_writer -R /data/epoc/storage/jfjoch_test/ tcp://127.0.0.1:5500
   ```

4. (Optional) For writing meta-data in the saved hdf5 files, open a new terminal and start the metadata-writer:

   ``` bash
   cd /data/epoc/storage/jem2100plus
   python -i metadata_update_server.py
   ```

#### CameraPC (HODGKIN)
1. To open the JFJ web interface, open the web browser (firefox on HODGKIN) and enter ```http://noether:5232/``` in the address bar.\
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
5. Confirm you are on the `main` branch, otherwise switch:
   ```bash
   git branch --contains
   git switch main
   ```
6. Start the GUI:
   ```bash
   python launch_gui.py -t -s tcp://noether:5501
   ```
   ```-f```    : save loggings in a file \
   ```-th```   : choose host for tem-gui communication e.g. localhost \
   ```-l```    : Set the logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL) \

7. To start streaming:\
    - Starting the decoding of the streamed data -> Push ```View Stream```\
    - Ensure good connection to JFJ -> Push ```Connection to Jungfraujoch```\
    - Display decoded frames -> ```Live Stream```\
    - Record the dark frame -> ```Record Full Pedestal``` (Blocking operation so wait until the end)

8. To collect data when TEM controls are OFF:\
    - Push the button ```Collect``` and stop collection with ```Cancel```

## Deactivation

### CameraPC (hodgkin)
1. Stop the receiver by clicking the `Stop` pushbutton. This may take several seconds.\
2. Disconnect to TEM, stop streaming, and exit the viewer.

### TEM-PC
1. Open another PowerShell console and kill the corresponding python process:
   ```bash
   Get-Process python
   kill [process-id]
   ```

## Main Functionalities

- `View Stream`: Reads the stream of frames published by the receiver.
- `Apply Auto Contrast`: Dynamically adjusts the contrast of displayed frames (~[not working correctly](#Known-bugs)~ fixed).
- `Reset Contrast`: Turn off the auto-contrast and reload preset contrast values from Redis. Four other presets can also be used.
- `Exit`: Exits the GUI.
- `Beam Gaussian Fit`: Starts fitting the beam's elliptical spot shape (non-TEM mode only, useful for manual focusing).
- `Magnification`, `Distance`: Displays the magnification and distance values (TEM mode only). `scale` checkbox displays the scale bar (1 um) or the ring (1 A).

### [Summing Receiver Controls](../jungfrau_gui/screenshot/ver_13Dec2024.png)

- `Connect to jungfraujoch`: Establishes a connection with the jungfraujoch-receiver.
- `Live stream`: Displays summed frames.
- `Data Collection`:
    - `Threshold`: Defines the energy (**th**) in keV below which values are cut.\
          - If **th = 0** : Thresholding is disabled \
          - If **th > 0** : Pixel values below **th** are reset to zero. \
    - `wait`: If checked, this option freezes the GUI during data collection.
- `Collect`: Starts recording of frame streams. Ends with `Cancel`.
- `Record Full Pedestal`: Records and subtracts the dark frames. Temporarily gets unresponsive to any controls (several seconds). Pedestal data is saved in jfj (not in GUI).

### [TEM-control Function](../jungfrau_gui/screenshot/ver_16Aug2024.PNG)

- `Check TEM connection`: Starts communication with TEM.
- `Get TEM status`: Displays the TEM status in the terminal [with the option of writing status in .log file] \
    -`recording`: **(disabled)** When checked, allows to save the TEM status in a .log file. ([not working correctly](#Known-bugs))
- `Click-on-Centering`: Activates stage XY-control by clicking on the imageat the pint of interest.
- `Gaussian Fit`: Fits a gaussian to the direct beam  within the ROI (A preliminary way to get the beam center info to add to the metadata)
    - `Beam center (px)`: Displays the position (X_center,Y_center) of the center of the fitted gaussian  
    - `Gaussian height`: Displays the peak of the gaussian (keV)
    - `Sigma x (px)`: Standard deviation in the major x-axis
    - `Sigma y (px)`: Standard deviation in the minor y-axis
    - `Theta (deg)`: Orientation of the gaussian tilt angle with respect to the horizontal X-axis of the frame.
- `Beam Autofocus`: **(Not ready for use)** Sweeps IL1 and ILstig values.
- `Rotation`: Starts stage rotation to the target angle. The beam is unblanked during rotation and blanked when rotation ends.
    - `with Writer`: Synchronizes the HDF writer with rotation.
    - `Auto reset`: Resets the tilt to 0 degrees after rotation.
- `Rotation Speed`: Adjusts rotation speed before starting the rotation. Also updates the `rotation_speed_idx` variable of the Configuration Manager in the data base.
- `Stage Ctrl`: Moves the stage in specific direction. \*Rotations are not automatically quicken.
- `Blank beam`: Blanks/unblanks beam and displays the blanking status
- `Screen Up/Down`: **(Not ready for use)** Moves screen (activated with '-e'). Does not indicate the current screen status.
- `Mag Mode`: Switches and indicates the current magnification mode. Also deactivates the Auto-contrast. [See issue \#80](https://github.com/epoc-ed/GUI/issues/80).
- `Positions`: Dropdown menu to set the XY positions of the stage
    - `Add`: Enquires about TEM stage position (through the API) and saves the coordinates in the dropdown menu 
    - `Go`: Sends the command to move the TEM stage the X-Y coordiantes set in the `Positions` menu
    
### [File Operation and Redis](../jungfrau_gui/screenshot/ver_24Sept2024.png)

#### Redis Store Settings
- `Experiment Class`: Specifies for whom the data is collected (e.g., UniVie, External, IP).
- `User Name`*: Enter the PI (Person of Interest).
- `Project ID`*: Enter the project identifier.
- `Base Data Directory`: Specifies the root directory for data saving.

#### HDF5 output
- `HDF5 Tag`*: Enter the file prefix (ASCII characters and underscores only).
- `index`*: Set the file index for the HDF5 file.
- `H5 Output Path`: Read-only field showing the path where datasets are saved.

**⚠️ Important ⚠️** All the fields with (*) are manually editable. During edition, the entered values/text will be displayed in orange. Press [ENTER] to confirm modifications and values will be uploaded to the data base.

## Data-recording workflow

1. Set up the beam and stage of TEM.
2. Blank the beam to avoid sample damage.
3. Confirm the data output path on the `H5 Output Path` line-edit.
4. Modify the stage rotation speed and end angle.
5. Check the `with Writer` box.
6. Click `Rotation` to start the rotation and recording.
7. Continue until the end angle is reached or interrupted.
8. Take an HDF movie if needed (e.g. crystal picture).

## Data-processing notes
updated on 19 Jan 2025
- Data loading
    - **XDS**:
        - [Version before 20.Aug.2024](https://github.com/epoc-ed/epoc-utils/commit/2198487645fbb5390e2f629b570ac0dbf18db268) [The plugin derived from Neggia](https://github.com/epoc-ed/DataProcessing/tree/main/XDS/neggia) requires `_master.h5` in the filename. Create a symbolic link:
            ```
            ln -s [full-path-of-hdffile] linked_master.h5
            ```
        - [Version before 10.Oct.2024](https://github.com/epoc-ed/GUI/releases/tag/v2024.10.10) Data stored with float32 format. [Neggia-derived plugin](https://github.com/epoc-ed/DataProcessing/tree/main/XDS/neggia) can work. [Another plugin](https://github.com/epoc-ed/xdslib_epoc-jungfrau/tree/master) can not.
        - [Version after 10.Oct.2024](https://github.com/epoc-ed/GUI/releases/tag/v2024.10.10) Data stored with int32 format and compressed. [Another plugin](https://github.com/epoc-ed/xdslib_epoc-jungfrau/tree/master) can work. [Neggia-derived plugin](https://github.com/epoc-ed/DataProcessing/tree/main/XDS/neggia) can not.
        - Version after XX.Nov.2024 (JFJ installation) Data stored with int32 format and linked with master.h5. [**The original Neggia-plugin**](https://github.com/dectris/neggia/) can process the data.


    - **DIALS**: Install the [updated Format Class for JF1M](https://github.com/epoc-ed/DataProcessing/blob/main/DIALS/format/FormatHDFJungfrau1MJFJVIE01.py) to read the HDF file directly:\
       ``` dials.import [filename.h5] slow_fast_beam_center=532,515```
- Script-based launching\
**This procedure is still under testing! Please try it carefully.\
To run for the datasets recorded with the previous version of GUI, some parameters in the generated files (oscillation, calibrated camera length, etc.) need to be modified manually.**
1. Copy [metadata_update_server.py](../jungfrau_gui/metadata_uploader/metadata_update_server.py) and [jf1m_reprocess.py](../jungfrau_gui/metadata_uploader/jf1m_reprocess.py) to your local directory path in the processing-server (noether)
1. (Option) Setup to launch DIALS
    ```
    source [dials_installation_path]/dials-v3-22-1/dials_env.sh
    ```
1. Run jf1m_reprocess.py to **generate XDS.INP** and **(Optional) run DIALS with default parameters** at your working directory with python or *dxtbx.python*
    ```
    (dxtbx.)python jf1m_reprocess.py [full-path-of-xxx_master.h5] [full-path-of-template_directory_path]/XDS-JF1M_JFJ_2024-12-10.INP
    ```
\**Expected directory structure:*
```
.
|--XDS
|    └--XDS.INP
└--DIALS
     |--dials.import.log
     |--imported.expt
     |--dials.find_spots.log
     |--strong.refl
     :
```

## Troubleshooting

- **PowerShell console not responding after disconnecting from GUI**: Open another PowerShell console and kill the python process:

   ```bash
   Get-Process python
   kill [pid]
   ```
- **TEM-control button delay**: There may be a few seconds of delay when responding, especially the first time. Please wait.

### Known bugs
updated on 13 Dec 2024
- Autocontrast does not work correctly after installation of JF-1M. Modify contrast manually or use fixed-contrast buttons.
- Recording of TEM-related values does not correctly output a file. Currently this function is disabled.

### Launching previous system
- Usage of previous rotation commands/scripts under PyJEM3.8 environment
1. Open a Miniconda PowerShell Prompt (Anaconda submenu) from the Windows Start Menu.
1. activate 'vjem38' virtual environment

    ``` bash
   conda activate vjem38
    ```
1. Navigate to `C:\ProgramData\xxxxxx`
1. Start interactive python, and load PyJEM module and use the commands:\

    ``` bash
    python
    >>> from PyJEM import TEM3
    >>> stage = TEM3.Stage3()
    >>> stage.Setf1OverRateTxNum(1)
    >>> stage.SetTiltXAngle(60)
    ```

1. Or just call a python script

    ``` bash
    python rotational_devel.py
    ```
