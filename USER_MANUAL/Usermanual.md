# New Receiver and Viewer of JUNGFRAU for ED, CCSA-UniWien
This document was updated on 22 Jan 2024\
**When you encounter bug-like behaviors, please check [known bugs](#Known-bugs).**

## Table of Contents
- [TEM control activation](#tem-control-activation)
- [Starting the receiver](#starting-the-receiver)
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
   This must be done **before** starting the GUI below.
2. Follow the below steps depending on the receiver in use:
   
## Starting the JUNGFRAUJOCH Receiver

#### Server (noether)
**This part is a bit out of date and will soon be updated. Broker and Writer are runnig backgroud and users need not care them in usual. (13 Dec 2024)**
1. Login as ```psi``` and switch to the Root User.
2. Start the Jungfraujoch broker:
    ```/opt/jfjoch/bin# ./jfjoch_broker /opt/etc/broker_jf500k.json```
3. For data collection, open a separate terminal and start the Jungfraujoch writer:
   ```/opt/jfjoch/bin/jfjoch_writer -R /data/epoc/storage/jfjoch_test/ tcp://127.0.0.1:5500```
4. (Option) For writing meta-data in the saved hdf files, open a new terminal and start the metadata-writer:
    ```bash
    cd /data/epoc/storage/jem2100plus
    python -i metadata_update_server.py
    ```

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
5. Confirm you are on the `no-reuss-client` branch, otherwise switch:
   ```bash
   git branch --contains
   git switch no-reuss-client
   ```
6. Start the GUI:
   ```bash
   python launch_gui.py -t -s tcp://noether:5501
   ```
   >```-f``` can be added to save logs in a file
7. To start streaming:
    > Starting the decoding of the streamed data -> Push ```View Stream```
    > Ensure good connection to JFJ -> Push ```Connection to Jungfraujoch```
    > Display decoded frames -> ```Live Stream```
    > Record the dark frame -> ```Record Full Pedestal``` (Blocking operation so wait until the end)

8. To collect data when TEM controls are OFF:
   > Push the button ```Collect``` and stop collection with ```Cancel```

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
- `Apply Auto Contrast`: Dynamically adjusts the contrast of displayed frames ([not working correctly](#Known-bugs)).
- `Reset Contrast`: Turn off the auto-contrast and reload preset contrast values from Redis. Four other presets can also be used.
- `Exit`: Exits the GUI.
- `Beam Gaussian Fit`: Starts fitting the beam's elliptical spot shape (non-TEM mode only, useful for manual focusing).
- `Magnification`, `Distance`: Displays the magnification and distance values (TEM mode only). `scale` checkbox displays the scale bar (1 um) or the ring (1 A).
- `Accumulate in TIFF`: Saves a TIFF snapshot to the specified data path (**[not tested in jfj-version](#Known-bugs)**).
- `Write Stream in H5`: Saves an HDF movie to the specified data path (**[not tested in jfj-version](#Known-bugs)**).

### Summing Receiver Controls
#### A. [JUNGFRAUJOCH](../jungfrau_gui/screenshot/ver_13Dec2024.png)
- `Connect to jungfraujoch`: Establishes a connection with the jungfraujoch-receiver.
- `Live stream`: Displays summed frames.
- `Data Collection`:
    - `Threshold`: \
            - `wait`:
- `Collect`: Starts recording of frame streams. Ends with `Cancel`.
- `Record Full Pedestal`: Records and subtracts the dark frames. Temporarily gets unresponsive to any controls (several seconds). Pedestal data is saved in jfj (not in GUI).

### [TEM-control Function](../jungfrau_gui/screenshot/ver_16Aug2024.PNG)

- `Check TEM connection`: Starts communication with TEM.
- `Get TEM status`: Displays the TEM status in the terminal [with the option of writing status in .log file]
   -`recording`: **(disabled)** When checked, allows to save the TEM status in a .log file. ([not working correctly](#Known-bugs))
- `Click-on-Centering`: **(disabled)** Activates stage control by clicking the image.
- `Beam Autofocus`: **(Not ready for use)** Sweeps IL1 and ILstig values.
- `Rotation`: Starts stage rotation to the target angle. The beam is unblanked during rotation and blanked when rotation ends.
    - `with Writer`: Synchronizes the HDF writer with rotation.
    - `JFJ`: Saves data in JFJ-server (noether).
    - `Auto reset`: Resets the tilt to 0 degrees after rotation.
- `Rotation Speed`: Adjusts rotation speed before starting the rotation. Also updates the `rotation_speed_idx` variable of the Configuration Manager in the data base.
- `Stage Ctrl`: Moves the stage in specific direction. \*Rotations are not automatically quicken.
- `Mag Mode`: Switches and indicates the current magnification mode. Also deactivates the Auto-contrast. [See issue \#80](https://github.com/epoc-ed/GUI/issues/80).

### [File Operation and Redis](../jungfrau_gui/screenshot/ver_24Sept2024.png)

#### Redis Store Settings
- `Experiment Class`: Specifies for whom the data is collected (e.g., UniVie, External, IP).
- `User Name`*: Enter the PI (Person of Interest).
- `Project ID`*: Enter the project identifier.
- `Base Data Directory`: Specifies the root directory for data saving.

**Note:** The [Get] buttons were coded for debugging purposes. They will be removed for the stable version.

**Important:** TIFF-Writer and HDF5-Writer have not been tested with JFJ. Use [`Collect`](#summing-receiver-controls) in Visualization Panel instead.
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
### A. [JUNGFRAUJOCH]
1. Set up the beam and stage of TEM.
2. Blank the beam to avoid sample damage.
3. Confirm the data output path on the `H5 Output Path` line-edit.
4. Modify the stage rotation speed and end angle.
5. Check the `with Writer` and `JFJ` boxes.
6. Click `Rotation` to start the rotation and recording.
7. Continue until the end angle is reached or interrupted.
8. Take an HDF movie if needed.

## Data-processing notes

- **XDS**:  
    - [Version before 20.Aug.2024](https://github.com/epoc-ed/epoc-utils/commit/2198487645fbb5390e2f629b570ac0dbf18db268) [The plugin derived from Neggia](https://github.com/epoc-ed/DataProcessing/tree/main/XDS/neggia) requires `_master.h5` in the filename. Create a symbolic link:
        ```
        ln -s [full-path-of-hdffile] linked_master.h5
        ```
    - [Version before 10.Oct.2024](https://github.com/epoc-ed/GUI/releases/tag/v2024.10.10) Data stored with float32 format. [Neggia-derived plugin](https://github.com/epoc-ed/DataProcessing/tree/main/XDS/neggia) can work. [Another plugin](https://github.com/epoc-ed/xdslib_epoc-jungfrau/tree/master) can not.
    - [Version after 10.Oct.2024](https://github.com/epoc-ed/GUI/releases/tag/v2024.10.10) Data stored with int32 format and compressed. [Another plugin](https://github.com/epoc-ed/xdslib_epoc-jungfrau/tree/master) can work. [Neggia-derived plugin](https://github.com/epoc-ed/DataProcessing/tree/main/XDS/neggia) can not.
    - Version after XX.Nov.2024 (JFJ installation) Data stored with int32 format and linked with master.h5. [**The original Neggia-plugin**](https://github.com/dectris/neggia/) can process the data.

- **DIALS**: Install the [updated Format Class](https://github.com/epoc-ed/DataProcessing/blob/main/DIALS/format/FormatHDFJungfrauVIE02.py) to read the HDF file directly:\
   ``` dials.import [filename.h5] slow_fast_beam_center=257,515 distance=660 ```

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
- Tiff- and HDF- writers have not been tested after installation of JFJ. Use [`Collect` and `Cancel`](#summing-receiver-controls) in Visualization Panel instead.
- Recording of TEM-related values does not correctly output a file. Currently this function is disabled.

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
