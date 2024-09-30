# New Receiver and Viewer of JUNGFRAU for ED, CCSA-UniWien
**Latest update**: 30 Sep 2024

## Table of Contents
- [Activation](#activation)
- [Deactivation](#deactivation)
- [Main Function](#main-function)
- [TEM-control Function](#tem-control-function)
- [Data-recording Workflow](#data-recording-workflow)
- [Data-recording Workflow with Testing Version](#data-recording-workflow-with-testing-version)
- [Data-processing Notes](#data-processing-notes-6-7-jun-2024)
- [Troubleshooting](#troubleshooting)

## Activation

### TEM-PC (not required if using only the TEM console panel)
1. Log in with the user 'JEM User'.
2. Open a **Miniconda PowerShell Prompt** (Anaconda submenu) from the Windows Start Menu.
3. Navigate to the `C:\ProgramData\EPOC` directory:
   ```bash
   cd C:\ProgramData\EPOC
   ```
4. Activate the environment:
   ```bash
   conda activate vjem38
   ```
5. Start the TEM server:
   ```bash
   python server_tem.py
   ```
   > **Note:** This must be done **before** starting the GUI.

### CameraPC (hodgkin)
1. Log in as 'psi', the environment is already set up.
2. Check the JF status:
   ```bash
   g status
   ```
3. If the JF is not configured, set it up and start it:
   ```bash
   p config ~/jf.config
   p start
   ```
4. If the configuration is ready, simply start the JF:
   ```bash
   p start
   ```
5. Navigate to the build directory:
   ```bash
   cd /home/psi/software/v2/reuss/build
   ```
6. Start the receiver with 12 threads:
   ```bash
   ./srecv -t 12
   ```
   > **Note:** Do not use the `srecv` located in `/home/psi/software/v2/python/app/srecv`.

7. Navigate to the GUI directory:
   ```bash
   cd /home/psi/software/viewer_2.0/GUI
   ```
   <!-- The 'testing' version will be renamed as 'stable' after the bug fix -->

8. Switch to the `testing` branch:
   ```bash
   git switch testing
   ```
   or
   ```bash
   git checkout testing
   ```

9. Confirm you are on the `testing` branch:
   ```bash
   git branch --contains
   ```

10. Start the GUI:
    
    ```bash
    python launch_gui.py
    ```
    
    **To use TEM control functions**, run:
    
    ```bash
    python launch_gui.py -t
    ```

11. Start streaming in the GUI without the incident beam.

12. Run the following in the terminal window, where the receiver (`srecv`) is running, to record the pedestal:

    ```bash
    r.record_pedestal(1)
    ```

    **Tip:** To adjust the threshold before pedestaling, run:
    
    ```bash
    r.set_threshold(-50)
    ```

13. (Optional) Record pedestal with gain:
    
    ```bash
    r.record_pedestal(2)
    ```


14. (Optional) Adjust the acquisition interval in the GUI to reduce the delay:
    - Change 'Acquisition Interval (ms)' to 20. Any error messages generated can be ignored.

## Deactivation

### CameraPC (hodgkin)
1. Stop streaming and exit the viewer.
2. Stop the receiver from the terminal window (this may take several seconds):
   ```bash
   r.stop()
   ```
3. Stop the JF process:
   ```bash
   p stop
   ```

### TEM-PC
1. Open another PowerShell console and kill the corresponding Python process:
   ```bash
   Get-Process python
   kill [process-id]
   ```

***

## Main Function
- **View Stream**: Reads the stream of frames sent by the receiver.
- **Auto Contrast**: Dynamically adjusts the contrast of the displayed frames.
- **Exit**: Exits the GUI. Disconnects the TEM before exiting.
- **[A]**: Resets the viewer scale (bottom left of the viewer panel).
- **Beam Gaussian Fit**: Starts fitting the beam's elliptical spot shape.
   - *For non-TEM mode only, useful for manual focusing.*
- **Magnification**, **Distance**: Displays values from the previous recording.
   - *Available in TEM mode only.*
- **Accumulate in TIFF**: Saves a TIFF snapshot to the specified data path in the line edit.
- **Write Stream in H5**: Saves an HDF movie to the specified data path with the given prefix. The output file ends with `_master.h5`.

***

## TEM-control Function
- **Connect to TEM**: (deactivated) Starts communication with TEM.
- **Get TEM Status**: (deactivated) Updates the TEM information and shows it in the terminal. If an HDF file with the defined filename exists, the information is added to the header.
- **Recording**: (deactivated) Saves the TEM values in the log file in the current directory.
- **Click-on-Centring**: (deactivated) Activates stage control by clicking the streaming image.
- **Beam Autofocus**: (**Not ready for use**) Sweeps IL1 and ILstig values roughly and finely.
- **Rotation**: Starts stage rotation to the input tilt degree ('Target angle') and reports the parameters.
   - The beam is unblanked when the rotation starts and blanked when it ends.
   - Rotation can be interrupted by clicking the button again or using the TEM console tilt button.
   - *The start angle only indicates the current value and cannot be modified.*
   - **With Writer**: Synchronizes the HDF writer with the rotation.
   - **Auto Reset**: Resets the stage tilt to 0° after rotation.
   - **Rotation Speed**: Changes the rotation speed and indicates the current value.\
     > **Note:** Click the rotation speed button right before starting rotation. [This will be fixed.](https://github.com/epoc-ed/GUI/issues/37)
- **Stage Ctrl**: Moves the stage quickly by constant values.

***

## Data-recording Workflow

1. Set up the beam and stage of the TEM for data collection.
2. Define the data output path on the 'H5 Output Path' line edit via the folder icon.
3. Start the stage rotation of TEM and immediately click **Write Stream in H5**.
4. Click **Stop Writing** just before the rotation ends.

<!-- 1. When 'Prepare for XDS processing' is checked, the output filename will end with `_master.h5`. -->
<!-- 1. Modify the 'Acquisition Interval (ms)'. -->

***

## Data-recording Workflow with Testing Version (*'-t'*)

1. Set up the beam and stage of the TEM for data collection.
2. Blank the beam to avoid sample damage.
3. Confirm/modify the data output path in the 'H5 Output Path' line edit (via folder icon or manually). *Cannot create an inexistent folder*.
4. Confirm/modify the stage rotation speed and the end angle of the rotation.
5. Check the **With Writer** box. Check/uncheck the **Auto Reset** box.
6. Click **Rotation** to start the rotation and recording synchronously.
7. The rotation/recording continues until the end angle is reached or interrupted.
8. Take a TIFF image if needed. *The TIFF image is not tied to the HDF file at the moment*.

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

## Data-processing Notes, 6-7 Jun 2024

- **Read with XDS**: The plugin derived from Neggia requires `_master.h5` in the input filename, and a symbolic link with the suffix should be additionally prepared:

   ```bash
   ln -s [full-path-of-hdffile] linked_master.h5
   ```

- **Read with DIALS**: Install the updated [Format Class](https://github.com/epoc-ed/DataProcessing/blob/main/DIALS/format/FormatHDFJungfrauVIE02.py) to read the HDF file directly:
   
   ```bash
   dials.import [filename.h5] slow_fast_beam_center=257,515 distance=660
   ```

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

## Troubleshooting
- **PowerShell console does not recover after disconnecting from GUI**:
    Open another PowerShell console and kill the corresponding Python process:

    ```bash
    Get-Process python
    kill [pid]
    ```
- **HDF files are not output to the defined path**:
    Modify the H5 Output Path via the folder icon (activates the file-browser system).
- **TEM-control button does not respond immediately**:
    There may be a delay of a few seconds in responding, especially the first time. Please wait a few moments.
