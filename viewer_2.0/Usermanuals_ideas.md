# New Receiver and Viewer of JUNGFRAU for ED, CCSA-UniWien
### Usage - This is a draft and should be updated -

#### Activation
**\*CameraPC (hodgkin)**
1. When we login as 'psi', the environment has been setup.
1.  ```$ p config ~/jf.config```
1.  ```$ p start```
1.  ```$ cd /home/psi/software/v2/reuss/build```
1.  ```$ srecv -t 12```
    what is '-t 12' ?
1.  ```$ cd /home/ktakaba/PyJEM_lab/EPOC_git_GUI/GUI_KF/GUI/viewer_2.0```
1.  ```$ ./viewer_2x.py```
1.  start streaming in the viewer-GUI, without incident beam.
1.  ```>>> r.record_pedestal(1)```

**\*TEM-PC**
1. Activate relay_server  
Open PowerShell console on TEMPC: C:\ProgramData\SinglaGUI,
```$ python relay_server_testKT.py```  
*\*Will not correctly communicate with the previous version, 'relay_server.py'*  
*\*When the sevrver is stuck, open another PowerShell console and kill the python process*  
```$ Get-Process python```  
```$ kill [pid]```  

***
#### Function
 -
 -
 - 'Connect to TEM': Starts communication with TEM. Takes ~10 sec.
 - 'Get TEM status': Updates the TEM information and shows in the console
 - 'Click-on-Centring': Activates stage control by clicking the streaming image
 - 'Start Rotation (+60)': Starts stage rotation until +60 deg., reports the setting parapemters, and resets the stage-tilt to zero when the rotation is stopped.
 - 'Magnification', 'Distance': Indicates the current or just previous value of magnicication/distance
 - 'Rotation Speed': Changes rotation speed settings and indicates the current value
 - 'Start Focus-sweeping': Sweeps IL1 and ILstig values linearly, roughly and finely


##### Checklist for activation
- [x] Beam-fitting module and the pop-up plotting module did work without fatal errors.
- [x] Writing H5 did work without fatal errors.
- [ ] 2 is mandatory for new receiver everytime?
- [ ] 9 is correct for starting measurement? How we can recognize the end of pedestal-recording?
- [ ] What is the safe way to shut down the receiver? (Ctrl+C or Ctrl+D or other specific command?)
- [ ] 

##### TODO for TEMcontroling function
1. [ ] prepare an user-manual / KT & KF
1. [ ] interaction with beam fit and focus sweeping
1. [ ] provide master.h5 for processing with XDS, referring to [https://github.com/epoc-ed/DataProcessing/tree/main/XDS]
1. [ ] separate functions in 'Start Rotation' and combination with 'Write Stream with H5' / KT
    1. [ ] switch the function to stop once activated
1. [ ] monitoring additional lens values / KT
1. [ ] click-on-centring with double-click and improve the reaction / KT

1. [ ] draw Debye-Scherrer ring for diffraction mode and a scale bar for imaging mode/ KT
1. [ ] loading TEM-setting values from log file, using glob etc.
1. [ ] take image(s) and save within hdf / KT
1. [ ] button to take a screenshot / KT

- Tim's request
1. [ ] sample ID / KF
1. [ ] select output directory data
1. [ ] select output directory working dir
1. [ ] frames/degree (default: 0.1 deg/s)
1. [ ] push button 'screen shot' need to discuss where screen shot should be saved, and format of output filename
1. [ ] end frame
1. [x] rotation rate (provided by JEM: 10 deg/s, 2.0 deg/s, 1.0 deg/s, 0.5 deg/s)
1. [ ] Image of sample: can we store the image inside the H5-file? / KT


