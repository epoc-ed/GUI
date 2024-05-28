#!/usr/bin/env python3

import os
import time
import logging
import datetime
import argparse
import numpy as np
import sys
import math
import reuss 
from reuss import config as cfg
from ZmqReceiver import *
from overlay_pyqt import draw_overlay 
import pyqtgraph as pg
from pyqtgraph.dockarea import Dock
from boost_histogram import Histogram
from boost_histogram.axis import Regular
from PySide6.QtWidgets import (QMainWindow, QPushButton, QSpinBox, QDoubleSpinBox,
                               QMessageBox, QLabel, QLineEdit, QApplication, QHBoxLayout, 
                               QVBoxLayout, QWidget, QGroupBox, QGraphicsEllipseItem, 
                               QGraphicsRectItem, QFileDialog, QFrame, QCheckBox, 
                               QGridLayout, QSizePolicy, QButtonGroup, QRadioButton)
from PySide6.QtCore import (Qt, QThread, QTimer, QCoreApplication, 
                            QRectF, QMetaObject, Signal, QObject)
from PySide6.QtGui import QTransform, QIcon
from workers import *
import multiprocessing as mp
from StreamWriter import StreamWriter
import h5py
from plot_dialog import *
from line_profiler import LineProfiler
import ctypes

# from task.control_worker import ControlWorker
from task.control_worker import *
from toolbox.tool import *
from ui.main_window_ui_temctrl import *

def save_captures(fname, data):
    logging.info(f'Saving: {fname}')
    reuss.io.save_tiff(fname, data)


class ToggleButton(QPushButton):
    def __init__(self, label, window):
        super().__init__(label, window)
        self.started = False


class ApplicationWindow(QMainWindow, Ui_TEMctrl):
    def __init__(self, receiver):
        super().__init__()
        self.receiver = receiver
        self.threadWorkerPairs = [] # List of constructed (thread, worker) pairs
        if globals.tem_mode:
            self.setupUI_temctrl(self)
            self.setupUI_temctrl_ready(self, False)
        self.initUI()
        
        if globals.tem_mode:
            self.control = ControlWorker(self)
            self.control.tem_socket_status.connect(self.on_sockstatus_change)
            self.control.updated.connect(self.on_tem_update)
            self.formatted_filename = ''
            self.temtools = TEMTools(self)

    def initUI(self):
        self.setWindowTitle("Viewer 2.x")
        self.setGeometry(50, 50, 1500, 1000)
        
        pg.setConfigOptions(imageAxisOrder='row-major')
        pg.mkQApp()
        # Define Dock element and include relevant widgets and items 
        self.dock = Dock("Image", size=(1000, 350))
        self.glWidget = pg.GraphicsLayoutWidget(self)
        self.plot = self.glWidget.addPlot(title="")
        self.dock.addWidget(self.glWidget)
        self.imageItem = pg.ImageItem()
        self.plot.addItem(self.imageItem)
        self.histogram = pg.HistogramLUTItem()
        self.histogram.setImageItem(self.imageItem)
        logging.debug(pg.graphicsItems.GradientEditorItem.Gradients.keys())
        # self.histogram.gradient.loadPreset('viridis')
        self.glWidget.addItem(self.histogram)
        self.histogram.setLevels(0,255)
        self.plot.setAspectLocked(True)
        # Create an ROI
        self.roi = pg.RectROI([450, 200], [150, 100], pen=(9,6))
        self.plot.addItem(self.roi)
        self.roi.addScaleHandle([0.5, 1], [0.5, 0.5])
        self.roi.addScaleHandle([0, 0.5], [0.5, 0.5])
        # Connect ROI changes to a method
        self.roi.sigRegionChanged.connect(self.roiChanged)
        # Create the fitting Ellipse
        self.ellipse_fit = QGraphicsEllipseItem()
        self.sigma_x_fit = QGraphicsRectItem()
        self.sigma_y_fit = QGraphicsRectItem()
        # Initial data
        data = np.random.rand(globals.nrow,globals.ncol).astype(globals.dtype)
        logging.debug(f"type(data) is {type(data[0,0])}")
        # Plot overlays from .reussrc          
        draw_overlay(self.plot)
        self.imageItem.setImage(data, autoRange = False, autoLevels = False, autoHistogramRange = False)
        # Mouse Hovering
        self.imageItem.hoverEvent = self.imageHoverEvent
        self.plotDialog = None
        """ 
        ===============
        General Layout
        =============== 
        """
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.dock)

        # Horizontal line separator
        h_line_1 = QFrame()
        h_line_1.setFrameShape(QFrame.HLine)
        h_line_1.setFrameShadow(QFrame.Plain)
        h_line_1.setStyleSheet("""QFrame {border: none; border-top: 1px solid grey;}""")

        # Sections layout
        sections_layout = QHBoxLayout()

        # Section 1 layout
        group1 = QGroupBox("Visualization Panel")
        section1 = QVBoxLayout()
        # Creating buttons for theme switching
        colors_group = QVBoxLayout()
        colors_layout = QHBoxLayout()
        theme_label = QLabel("Color map", self)
        colors_group.addWidget(theme_label)
        self.color_buttons = {
            'viridis': QPushButton('Viridis', self),
            'inferno': QPushButton('Inferno', self),
            'plasma': QPushButton('Plasma', self),
            'grey': QPushButton('Grey', self)
        }
        # Add buttons to layout and connect signals
        for name, button in self.color_buttons.items():
            colors_layout.addWidget(button)
            button.clicked.connect(lambda checked=False, b=name: self.change_theme(b))
        colors_group.addLayout(colors_layout)
        # Set Initial theme
        self.change_theme('viridis')
        section1.addLayout(colors_group)
        # Seperate subsections
        section1.addWidget(h_line_1)
        # Start stream viewing
        self.stream_view_button = ToggleButton("View Stream", self)
        self.stream_view_button.setStyleSheet(
            """
            ToggleButton {
                color: #FFFFFF; 
                font-size: 10pt;
                background-color: #333333;
            }
            """
        )
        self.stream_view_button.setMaximumHeight(50)
        # Auto-contrast area (Button + Status)
        contrast_box = QVBoxLayout()
        self.autoContrastBtn = QPushButton('Auto Contrast', self)
        self.autoContrastBtn.setStyleSheet('background-color: red; color: white;')
        self.autoContrastBtn.clicked.connect(self.applyAutoContrast)
        self.autoContrastON = False
        self.contrast_status = QLabel("Auto Contrast is OFF")
        self.contrast_status.setAlignment(Qt.AlignCenter) 
        self.contrast_status.setStyleSheet('color: red;')
        contrast_box.addWidget(self.autoContrastBtn)
        contrast_box.addWidget(self.contrast_status)
        #   Layout [           Stream View           ][Auto Contrast]
        view_contrast_group = QVBoxLayout()
        view_contrast_label = QLabel("Streaming & Contrast")
        view_contrast_group.addWidget(view_contrast_label)

        grid_1 = QGridLayout()
        grid_1.addWidget(self.stream_view_button, 0, 0, 2, 2)  # Span two rows two columns
        grid_1.addWidget(self.autoContrastBtn, 0, 2)
        grid_1.addWidget(self.contrast_status, 1, 2)

        view_contrast_group.addLayout(grid_1)
        section1.addLayout(view_contrast_group)

        # Time Interval
        time_interval = QLabel("Acquisition Interval (ms):", self)
        self.update_interval = QSpinBox(self)
        self.update_interval.setMaximum(5000)
        self.update_interval.setSuffix(' ms')
        self.update_interval.setValue(cfg.viewer.interval)
        time_interval_layout = QHBoxLayout()
        time_interval_layout.addWidget(time_interval)
        time_interval_layout.addWidget(self.update_interval)
        section1.addLayout(time_interval_layout)
        
        ##### communication with TEM
        if globals.tem_mode:
            section1.addLayout(self.hbox_mag)
            self.rb_speeds.buttonClicked.connect(self.toggle_rb_speeds)
            section1.addLayout(self.hbox_rot)
            self.movex10ump.clicked.connect(lambda: self.control.send.emit("stage.SetXRel(10000)"))
            self.movex10umn.clicked.connect(lambda: self.control.send.emit("stage.SetXRel(-10000)"))
            self.move10degp.clicked.connect(lambda: self.control.with_max_speed("stage.SetTXRel(10)"))
            self.move10degn.clicked.connect(lambda: self.control.with_max_speed("stage.SetTXRel(-10)"))
            self.move0deg.clicked.connect(lambda: self.control.with_max_speed("stage.SetTiltXAngle(0)"))
            section1.addLayout(self.hbox_move)
        ##### END of communication with TEM
        
        group1.setLayout(section1)

        # Section 2 layout
        group2 = QGroupBox("TEM Controls")
        section2 = QVBoxLayout()
        # Gaussian Fit of the Beam intensity
        if globals.tem_mode:
            self.btnBeamSweep.clicked.connect(self.callBeamFitTask)
        else:
            self.btnBeamFocus = ToggleButton("Beam Gaussian Fit", self)
        self.timer_fit = QTimer()
        self.timer_fit.timeout.connect(self.getFitParams)
        self.btnBeamFocus.clicked.connect(self.toggle_gaussianFit)
            
        # Create a checkbox
        self.checkbox = QCheckBox("Enable pop-up Window", self)
        self.checkbox.setChecked(False)

        label_gauss_height = QLabel()
        label_gauss_height.setText("Gaussian height")
        self.gauss_height_spBx = QDoubleSpinBox()
        self.gauss_height_spBx.setValue(1)
        self.gauss_height_spBx.setMaximum(1e8)

        label_sigma_x = QLabel()
        label_sigma_x.setText("Sigma x (px)")
        label_sigma_x.setStyleSheet('color: cyan;')
        self.sigma_x_spBx = QDoubleSpinBox()
        self.sigma_x_spBx.setStyleSheet('color: blue;')
        self.sigma_x_spBx.setValue(1)
        self.sigma_x_spBx.setSingleStep(0.1)

        label_sigma_y = QLabel()
        label_sigma_y.setText("Sigma y (px)")
        label_sigma_y.setStyleSheet('color: red;')
        self.sigma_y_spBx = QDoubleSpinBox()
        self.sigma_y_spBx.setStyleSheet('color: red;')
        self.sigma_y_spBx.setValue(1)
        self.sigma_y_spBx.setSingleStep(0.1)

        label_rot_angle = QLabel()
        label_rot_angle.setText("Theta (deg)")
        self.angle_spBx = QSpinBox()
        self.angle_spBx.setMinimum(-90)
        self.angle_spBx.setMaximum(90)
        self.angle_spBx.setSingleStep(15)

        BeamFocus_layout = QVBoxLayout()
        if globals.tem_mode:
            BeamFocus_layout.addLayout(self.focus_layout)
        else:
            BeamFocus_layout.addWidget(self.btnBeamFocus)
        BeamFocus_layout.addWidget(self.checkbox)
        gauss_H_layout = QHBoxLayout()
        gauss_H_layout.addWidget(label_gauss_height)  
        gauss_H_layout.addWidget(self.gauss_height_spBx)
        BeamFocus_layout.addLayout(gauss_H_layout)
        sigma_x_layout = QHBoxLayout()
        sigma_x_layout.addWidget(label_sigma_x)  
        sigma_x_layout.addWidget(self.sigma_x_spBx)         
        BeamFocus_layout.addLayout(sigma_x_layout)
        sigma_y_layout = QHBoxLayout()
        sigma_y_layout.addWidget(label_sigma_y)  
        sigma_y_layout.addWidget(self.sigma_y_spBx)         
        BeamFocus_layout.addLayout(sigma_y_layout)        
        rot_angle_layout = QHBoxLayout()
        rot_angle_layout.addWidget(label_rot_angle)  
        rot_angle_layout.addWidget(self.angle_spBx)         
        BeamFocus_layout.addLayout(rot_angle_layout)
 
        section2.addLayout(BeamFocus_layout)
        group2.setLayout(section2)

        # Section 3 layout
        group3 = QGroupBox("File Operations")
        section3 = QVBoxLayout()
        # Accumulate
        self.fname = QLabel("TIFF file name", self)
        self.fname_input = QLineEdit(self)
        self.fname_input.setText('file')
        self.findex = QLabel("index:", self)
        self.findex_input = QSpinBox(self)  

        tiff_file_layout = QHBoxLayout()
        tiff_file_layout.addWidget(self.fname)
        tiff_file_layout.addWidget(self.fname_input)
        tiff_file_layout.addWidget(self.findex)
        tiff_file_layout.addWidget(self.findex_input)

        section3.addLayout(tiff_file_layout)

        self.accumulate_button = QPushButton("Accumulate in TIFF", self)
        self.accumulate_button.setEnabled(False)
        self.accumulate_button.clicked.connect(self.start_accumulate)
        self.acc_spin = QSpinBox(self)
        self.acc_spin.setValue(10)
        self.acc_spin.setSuffix(' frames')

        accumulate_layout = QHBoxLayout()
        accumulate_layout.addWidget(self.accumulate_button)
        accumulate_layout.addWidget(self.acc_spin)

        section3.addLayout(accumulate_layout)
        
        # Horizontal line separator
        h_line_3 = QFrame()
        h_line_3.setFrameShape(QFrame.HLine)
        h_line_3.setFrameShadow(QFrame.Plain)
        h_line_3.setStyleSheet("""QFrame {border: none;border-top: 1px solid grey;}""")
        section3.addWidget(h_line_3)

        # Stream Writer
        # Initialize 
        self.h5_file_index = 0
        # Hdf5 file operations
        h5_file_ops_layout = QHBoxLayout()
        self.prefix = QLabel("HDF5 prefix", self)
        self.prefix_input = QLineEdit(self)
        self.prefix_input.setText('prefix')

        self.index_label= QLabel("index")
        self.index_box = QSpinBox(self)
        self.index_box.setValue(self.h5_file_index)
        self.index_box.valueChanged.connect(self.update_h5_file_index)

        h5_file_ops_layout.addWidget(self.prefix) 
        h5_file_ops_layout.addWidget(self.prefix_input)
        h5_file_ops_layout.addWidget(self.index_label)
        h5_file_ops_layout.addWidget(self.index_box)

        section3.addLayout(h5_file_ops_layout)

        output_folder_layout = QHBoxLayout()
        self.outPath = QLabel("H5 Output Path", self)
        self.outPath_input = QLineEdit(self)
        self.outPath_input.setText(os.getcwd())
        self.h5_folder_name = self.outPath_input.text()
        self.folder_button = QPushButton()
        self.folder_button.setIcon(QIcon("./extras/folder_icon.png"))
        self.folder_button.clicked.connect(self.open_directory_dialog)

        output_folder_layout.addWidget(self.outPath, 2)
        output_folder_layout.addWidget(self.outPath_input,7)
        output_folder_layout.addWidget(self.folder_button,1)

        section3.addLayout(output_folder_layout)

        hdf5_writer_layout = QGridLayout()
        self.streamWriter = None
        self.streamWriterButton = ToggleButton("Write Stream in H5", self)
        self.streamWriterButton.setEnabled(False)
        self.streamWriterButton.clicked.connect(self.toggle_hdf5Writer)
        # Create a checkbox
        self.xds_checkbox = QCheckBox("Prepare for XDS processing", self)
        self.xds_checkbox.setChecked(True)
        hdf5_writer_layout.addWidget(self.streamWriterButton, 0, 0, 1, 2)
        if globals.tem_mode:
            hdf5_writer_layout.addWidget(self.xds_checkbox, 1, 0)
            hdf5_writer_layout.addWidget(self.writer_for_rotation, 1, 2)
        else:
            hdf5_writer_layout.addWidget(self.xds_checkbox, 1, 0)

        self.nb_frame = QLabel("Number Written Frames:", self)
        self.total_frame_nb = QSpinBox(self)
        self.total_frame_nb.setMaximum(100000000)

        hdf5_writer_layout.addWidget(self.nb_frame, 0, 2)
        hdf5_writer_layout.addWidget(self.total_frame_nb, 0, 3)

        section3.addLayout(hdf5_writer_layout)
        group3.setLayout(section3)

        sections_layout.addWidget(group1, 1)
        sections_layout.addWidget(group2, 1)
        sections_layout.addWidget(group3, 1)

        main_layout.addLayout(sections_layout)
        # Exit
        if globals.tem_mode:
            self.exit_button.clicked.connect(self.do_exit)
            self.connecttem_button.clicked.connect(self.toggle_connectTEM)
            self.gettem_button.clicked.connect(self.callGetInfoTask)
            self.centering_button.clicked.connect(self.toggle_centering)
            self.rotation_button.clicked.connect(self.toggle_rotation)
            main_layout.addLayout(self.bottom_layout)
        else:
            self.exit_button = QPushButton("Exit", self)
            self.exit_button.clicked.connect(self.do_exit)
            main_layout.addWidget(self.exit_button)
        # Set the central widget of the MainWindow
        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)
        # Timer to trigger continuous stream reading
        self.timer = QTimer(self)
        self.stream_view_button.clicked.connect(self.toggle_viewStream)
        self.timer.timeout.connect(self.captureImage)

        logging.info("Viewer ready!")

    def change_theme(self, theme):
        self.histogram.gradient.loadPreset(theme)

    # @profile
    def applyAutoContrast(self, histo_boost = False):
        self.autoContrastON = True
        self.autoContrastBtn.setStyleSheet('background-color: green; color: white;')
        self.contrast_status.setText("Auto Contrast is ON")
        self.contrast_status.setStyleSheet('color: green;')
        if histo_boost:
            data_flat = self.imageItem.image.flatten()
            histogram = Histogram(Regular(1000000, data_flat.min(), data_flat.max()))
            histogram.fill(data_flat)
            cumsum = np.cumsum(histogram.view())
            total = cumsum[-1]
            low_thresh = np.searchsorted(cumsum, total * 0.01)
            high_thresh = np.searchsorted(cumsum, total * 0.99999)
        else:
            low_thresh, high_thresh = np.percentile(self.imageItem.image, (1, 99.999))
        
        self.histogram.setLevels(low_thresh, high_thresh)

    def roiChanged(self):
        # Get the current ROI position and size
        roiPos = self.roi.pos()
        roiSize = self.roi.size()
        imageShape = self.imageItem.image.shape
        # Calculate the maximum allowed positions for the ROI
        maxPosX = max(0, imageShape[1] - roiSize[0])  # image width - roi width
        maxPosY = max(0, imageShape[0] - roiSize[1])  # image height - roi height
        # Correct the ROI position if it's out of bounds
        correctedPosX = min(max(roiPos[0], 0), maxPosX)
        correctedPosY = min(max(roiPos[1], 0), maxPosY)
        # If the ROI size is larger than the image, adjust the size as well
        correctedSizeX = min(roiSize[0], imageShape[1])
        correctedSizeY = min(roiSize[1], imageShape[0])
        # Apply the corrections to the ROI
        self.roi.setPos([correctedPosX, correctedPosY], update=False)
        self.roi.setSize([correctedSizeX, correctedSizeY], update=False)
        # Print ROI position
        logging.debug(f"ROI Position: {self.roi.pos()}, Size: {self.roi.size()}")

    def imageHoverEvent(self, event):
        im = self.imageItem.image
        if event.isExit():
            self.plot.setTitle("")
            return
        pos = event.pos()
        i, j = pos.y(), pos.x()
        i = int(np.clip(i, 0, im.shape[0] - 1))
        j = int(np.clip(j, 0, im.shape[1] - 1))
        
        val = im[i, j]
        ppos = self.imageItem.mapToParent(pos)
        x, y = ppos.x(), ppos.y()
        #### click-on-centering
        if event.buttons() == Qt.LeftButton:
            if self.centering_button.started and globals.tem_mode:
                self.control.trigger_centering.emit(True, "%0.1f, %0.1f" % (x, y))
            else:
                QApplication.clipboard().setText("%0.1f, %0.1f" % (x, y))
        ####
        self.plot.setTitle("pos: (%0.1f, %0.1f)  pixel: (%d, %d)  value: %.3g" % (x, y, i, j, val))      

    def toggle_viewStream(self):
        if not self.stream_view_button.started:
            self.thread_read = QThread()
            self.streamReader = Reader(self.receiver)
            self.threadWorkerPairs.append((self.thread_read, self.streamReader))                              
            self.initializeWorker(self.thread_read, self.streamReader) # Initialize the worker thread and fitter
            self.thread_read.start()
            self.readerWorkerReady = True # Flag to indicate worker is ready
            logging.info("Starting reading process")
            # Adjust button display according to ongoing state of process
            self.stream_view_button.setText("Stop")
            self.plot.setTitle("View of the Stream")
            self.timer.setInterval(self.update_interval.value())
            self.stream_view_button.started = True
            logging.info(f"Timer interval: {self.timer.interval()}")
            # Start timer and enable file operation buttons
            self.timer.start()
            self.accumulate_button.setEnabled(True)
            self.streamWriterButton.setEnabled(True)
        else:
            self.stream_view_button.setText("View Stream")
            self.plot.setTitle("Stream stopped at the current Frame")
            self.stream_view_button.started = False
            self.timer.stop()
            # Properly stop and cleanup worker and thread  
            self.stopWorker(self.thread_read, self.streamReader)
            # Disable buttons
            self.accumulate_button.setEnabled(False)
            self.streamWriterButton.setEnabled(False)
            # Wait for thread to actually stop            
            if self.thread_read is not None:
                logging.info("** Read-thread forced to sleep **")
                time.sleep(0.1) 
            self.autoContrastON = False
            self.autoContrastBtn.setStyleSheet('background-color: red; color: white;')
            self.contrast_status.setText("Auto Contrast is OFF")
            self.contrast_status.setStyleSheet('color: red;')

    def initializeWorker(self, thread, worker):
        worker.moveToThread(thread)
        logging.info(f"{worker.__str__()} is Ready!")
        thread.started.connect(worker.run)
        if isinstance(worker, Reader):
            worker.finished.connect(self.updateUI)
            worker.finished.connect(self.getReaderReady)
        if isinstance(worker, Gaussian_Fitter):
            worker.finished.connect(self.updateFitParams)
            worker.finished.connect(self.getFitterReady)
        if isinstance(worker, Frame_Accumulator):
            worker.finished.connect(
                lambda x: save_captures(f'{self.fname_input.text()}_{self.findex_input.value()}', x))

    def getReaderReady(self):
        self.readerWorkerReady = True

    def captureImage(self):
        if self.readerWorkerReady:
            self.readerWorkerReady = False
            QMetaObject.invokeMethod(self.streamReader, "run", Qt.QueuedConnection)

    def updateUI(self, image, frame_nr):
        self.imageItem.setImage(image, autoRange = False, autoLevels = False, autoHistogramRange = False) ## .T)
        if self.autoContrastON:
                self.applyAutoContrast()
        self.statusBar().showMessage(f'Frame: {frame_nr}')

    def start_accumulate(self):
        file_index = self.findex_input.value()
        f_name = self.fname_input.text()
        nb_frames_to_take = self.acc_spin.value()
        # Construct the (thread, worker) pair
        self.thread_acc = QThread()
        self.accumulator = Frame_Accumulator(nb_frames_to_take)
        self.threadWorkerPairs.append((self.thread_acc, self.accumulator))
        self.initializeWorker(self.thread_acc, self.accumulator)
        # Connect signals to relevant slots for operations
        self.accumulator.finished.connect(self.thread_acc.quit)
        self.accumulator.finished.connect(lambda: self.stopWorker(self.thread_acc, self.accumulator))
        self.thread_acc.start()
        # Upadate file number for next take
        self.findex_input.setValue(file_index+1)
    
    def toggle_gaussianFit(self):
        if not self.btnBeamFocus.started:
            self.thread_fit = QThread()
            self.fitter = Gaussian_Fitter()
            self.threadWorkerPairs.append((self.thread_fit, self.fitter))                              
            self.initializeWorker(self.thread_fit, self.fitter) # Initialize the worker thread and fitter
            self.thread_fit.start()
            self.fitterWorkerReady = True # Flag to indicate worker is ready
            logging.info("Starting fitting process")
            self.btnBeamFocus.setText("Stop Fitting")
            self.btnBeamFocus.started = True
            # Pop-up Window
            if self.checkbox.isChecked():
                self.showPlotDialog()   
            # Timer started
            self.timer_fit.start()
        else:
            self.btnBeamFocus.setText("Beam Gaussian Fit")
            self.btnBeamFocus.started = False
            self.timer_fit.stop()  
            # Close Pop-up Window
            if self.plotDialog != None:
                self.plotDialog.close()
            self.stopWorker(self.thread_fit, self.fitter)
            self.removeAxes()

    def showPlotDialog(self):
        self.plotDialog = PlotDialog(self)
        self.plotDialog.startPlotting(self.gauss_height_spBx.value(), self.sigma_x_spBx.value(), self.sigma_y_spBx.value())
        self.plotDialog.show() 

    def getFitterReady(self):
        self.fitterWorkerReady = True

    def updateWorkerParams(self, imageItem, roi):
        if self.thread_fit.isRunning():
            # Emit the update signal with the new parameters
            self.fitter.updateParamsSignal.emit(imageItem, roi)  

    # @profile
    def getFitParams(self):
        if self.fitterWorkerReady:
            # Prevent new tasks until the current one is finished
            self.fitterWorkerReady = False
            # Make sure to update the fitter's parameters right before starting the computation
            self.updateWorkerParams(self.imageItem, self.roi)
            # Trigger the "run" computation in the thread where self.fitter" lives
            QMetaObject.invokeMethod(self.fitter, "run", Qt.QueuedConnection)

    def updateFitParams(self, fit_result_best_values):
        amplitude = float(fit_result_best_values['amplitude'])
        xo = float(fit_result_best_values['xo'])
        yo = float(fit_result_best_values['yo'])        
        sigma_x = float(fit_result_best_values['sigma_x'])
        sigma_y = float(fit_result_best_values['sigma_y'])
        theta_deg = 180*float(fit_result_best_values['theta'])/np.pi
        # Show fitting parameters 
        self.gauss_height_spBx.setValue(amplitude)
        self.sigma_x_spBx.setValue(sigma_x)
        self.sigma_x_spBx.setValue(sigma_x)
        self.sigma_y_spBx.setValue(sigma_y)
        self.angle_spBx.setValue(theta_deg)
        # Update graph in pop-up Window
        if self.plotDialog != None:
            self.plotDialog.updatePlot(amplitude, sigma_x, sigma_y, 20)
        # Draw the fitting line at the FWHM of the 2d-gaussian
        self.drawFittingEllipse(xo,yo,sigma_x, sigma_y, theta_deg)

    def drawFittingEllipse(self, xo, yo, sigma_x, sigma_y, theta_deg):
        # p = 0.5 is equivalent to using the Full Width at Half Maximum (FWHM)
        # where FWHM = 2*sqrt(2*ln(2))*sigma ~ 2.3548*sigma
        p = 0.2
        alpha = 2*np.sqrt(-2*math.log(p))
        width = alpha * sigma_x # Use 
        height = alpha * sigma_y # 
        # Check if the item is added to a scene, and remove it if so
        scene = self.ellipse_fit.scene() 
        scene_x = self.sigma_x_fit.scene() 
        scene_y = self.sigma_y_fit.scene() 
        if scene:  
            scene.removeItem(self.ellipse_fit)
        if scene_x:
            scene_x.removeItem(self.sigma_x_fit)
        if scene_y: 
            scene_y.removeItem(self.sigma_y_fit)
        # Create the ellipse item with its bounding rectangle
        self.ellipse_fit = QGraphicsEllipseItem(QRectF(xo-0.5*width, yo-0.5*height, width, height))
        self.sigma_x_fit = QGraphicsRectItem(QRectF(xo-0.5*width, yo, width, 0))
        self.sigma_y_fit = QGraphicsRectItem(QRectF(xo, yo-0.5*height, 0, height))
        # First, translate the coordinate system to the center of the ellipse,
        # then rotate around this point and finally translate back to origin.
        rotationTransform = QTransform().translate(xo, yo).rotate(theta_deg).translate(-xo, -yo)
        
        self.ellipse_fit.setPen(pg.mkPen('b', width=3))
        self.ellipse_fit.setTransform(rotationTransform)
        self.plot.addItem(self.ellipse_fit)

        self.sigma_x_fit.setPen(pg.mkPen('b', width=2))
        self.sigma_x_fit.setTransform(rotationTransform)
        self.plot.addItem(self.sigma_x_fit)

        self.sigma_y_fit.setPen(pg.mkPen('r', width=2))
        self.sigma_y_fit.setTransform(rotationTransform)
        self.plot.addItem(self.sigma_y_fit)

    def removeAxes(self):
        logging.info("Removing gaussian fitting ellipse.")
        if self.ellipse_fit.scene():
            logging.debug("Removing ellipse_fit from scene")
            self.ellipse_fit.scene().removeItem(self.ellipse_fit)
        if self.sigma_x_fit.scene():
            logging.debug("Removing sigma_x_fit from scene")
            self.sigma_x_fit.scene().removeItem(self.sigma_x_fit)
        if self.sigma_y_fit.scene():
            logging.debug("Removing sigma_y_fit from scene")
            self.sigma_y_fit.scene().removeItem(self.sigma_y_fit)
        # Optionally, update or refresh the scene if necessary
        # if self.plot.scene():
        #     self.plot.scene().update()

    def stopWorker(self, thread, worker):
        if worker:
            worker.finished.disconnect()
        if thread.isRunning():
            thread.quit()
            thread.wait() # Wait for the thread to finish
        self.threadCleanup(thread, worker)
        
    def threadCleanup(self, thread, worker):
        index_to_delete = None
        for i, (t, worker) in enumerate(self.threadWorkerPairs):
            if t == thread:
                if worker is not None:
                    logging.info(f"Stopping {worker.__str__()}!")
                    worker.deleteLater() # Schedule the worker for deletion
                    worker = None
                    logging.info("Process stopped!")
                index_to_delete = i
                break # because always only one instance of a thread/worker pair type
        if index_to_delete is not None:
            del self.threadWorkerPairs[index_to_delete]
        thread.deleteLater()  # Schedule the thread for deletion
        thread = None

    def open_directory_dialog(self):
        initial_dir = self.h5_folder_name or self.outPath_input.text()
        folder_name = QFileDialog.getExistingDirectory(self, "Select Directory", initial_dir)
        if not folder_name:
                return  # User canceled folder selection
        self.h5_folder_name = folder_name
        self.outPath_input.setText(self.h5_folder_name)
        logging.info(f"H5 output path set to: {self.h5_folder_name}")

    def toggle_hdf5Writer_dummy(self):
        if not self.streamWriterButton.started:
            prefix = self.prefix_input.text().strip()
            self.streamWriterButton.setText("Stop Writing")
            self.streamWriterButton.started = True
        else:
            self.streamWriterButton.setText("Write Stream in H5")
            self.streamWriterButton.started = False
        
        
    def toggle_hdf5Writer(self):
        if not self.streamWriterButton.started:
            prefix = self.prefix_input.text().strip()
            if not prefix:
                logging.error("Error: Prefix is missing! Please specify prefix of the written file(s).")# Handle error: Prefix is mandatory
                QMessageBox.critical(self, "Prefix Missing", "Prefix of written files is missing!\nPlease specify one under the field 'HDF5 prefix'.", QMessageBox.Ok)
                return
            
            logging.debug("TCP address for Hdf5 writer to bind to is ", args.stream)
            logging.debug("Data type to build the streamWriter object ", args.dtype)

            self.formatted_filename = self.generate_h5_filename(prefix)
            self.streamWriter = StreamWriter(filename=self.formatted_filename, 
                                             endpoint=args.stream, 
                                             image_size = (globals.nrow, globals.ncol),
                                             dtype=args.dtype)
            self.streamWriter.start()
            self.streamWriterButton.setText("Stop Writing")
            self.streamWriterButton.started = True
        else:
            self.streamWriterButton.setText("Write Stream in H5")
            self.streamWriterButton.started = False
            self.streamWriter.stop()
            self.total_frame_nb.setValue(self.streamWriter.number_frames_witten)
            logging.info(f"Last written frame number is   {self.streamWriter.last_frame_number.value}")
            logging.info(f"Total number of frames written in H5 file:   {self.streamWriter.number_frames_witten}")

            # if self.xds_checkbox.isChecked():
            #     self.generate_h5_master(self.formatted_filename)

    def update_h5_file_index(self, index):
            self.h5_file_index = index
            
    def generate_h5_filename(self, prefix):
        now = datetime.datetime.now()
        date_str = now.strftime("%d_%B_%Y_%H:%M:%S")
        index_str = f"{self.h5_file_index:03}"
        self.h5_file_index += 1
        self.index_box.setValue(self.h5_file_index)
        filename = f"{prefix}_{index_str}_{date_str}.h5"
        if self.xds_checkbox.isChecked():
            filename = f"{prefix}_{index_str}_{date_str}_master.h5" # for XDS
        full_path = os.path.join(self.h5_folder_name, filename)
        return full_path

    def generate_h5_master(self, formatted_filename_original_h5):
        logging.info("Generating HDF5 master file for XDS analysis...")
        with h5py.File(formatted_filename_original_h5, 'r') as f:
            data_shape = f['entry/data/data_000001'].shape

        external_link = h5py.ExternalLink(
            filename = formatted_filename_original_h5,
            path = 'entry/data/data_000001'
        )
        # output = os.path.basename(args.path_input)[:-24] + '_master.h5'
        output = formatted_filename_original_h5[:-24]  + '_master.h5'
        with h5py.File(output, 'w') as f:
            f['entry/data/data_000001'] = external_link
            f.create_dataset('entry/instrument/detector/detectorSpecific/nimages', data = data_shape[0], dtype='uint64')
            f.create_dataset('entry/instrument/detector/detectorSpecific/pixel_mask', data = np.zeros((data_shape[1], data_shape[2]), dtype='uint32')) ## 514, 1030, 512, 1024
            f.create_dataset('entry/instrument/detector/detectorSpecific/x_pixels_in_detector', data = data_shape[1], dtype='uint64') # 512
            f.create_dataset('entry/instrument/detector/detectorSpecific/y_pixels_in_detector', data = data_shape[2], dtype='uint64') # 1030

        print('HDF5 Master file is ready at ', output)

    def do_exit(self):
        running_threadWorkerPairs = [(thread, worker) for thread, worker in self.threadWorkerPairs if thread.isRunning()]
        if running_threadWorkerPairs:
            # Show warning dialog
            reply = QMessageBox.question(self, 'Thread still running',
                                        "A process is still running. Are you sure you want to exit?",
                                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                if self.streamWriter is not None:
                    if self.streamWriter.write_process.is_alive():
                        self.streamWriter.stop()
                globals.exit_flag.value = True
                for thread, worker in running_threadWorkerPairs:
                    logging.debug(f'Stopping Thread-Worker pair = ({thread}-{worker}).')
                    self.stopWorker(thread, worker) 
            else: 
                return
        
        if self.connecttem_button.started:
            self.control.trigger_shutdown.emit()

        logging.info("Exiting app!") 
        app.quit()

    def callBeamFitTask(self):
        if self.connecttem_button.started:
            self.control.actionFit_Beam.emit()

    def callGetInfoTask(self):
        if self.connecttem_button.started:
            if not os.access(self.outPath_input.text(), os.W_OK):
                self.gettem_checkbox.setChecked(False)
                logging.error(f'Writing in {self.outPath_input.text()} is not permitted!')
            if self.gettem_checkbox.isChecked():
                self.control.trigger_getteminfo.emit('Y')
            else:
                self.control.trigger_getteminfo.emit('N')
            if os.path.isfile(self.formatted_filename):
                self.temtools.addinfo_to_hdf()

    def toggle_rotation(self):
        if not self.rotation_button.started:
            self.rotation_button.setText("Stop")
            self.rotation_button.started = True
            self.streamWriterButton.setEnabled(False)
            self.control.trigger_record.emit()
        else:
            self.rotation_button.setText("Rotation")
            self.rotation_button.started = False
            if self.streamWriterButton.started:
                self.toggle_hdf5Writer_dummy()
            self.streamWriterButton.setEnabled(True)
            self.control.stop()

    def toggle_centering(self):
        if not self.centering_button.started:
            self.centering_button.setText("Deactivate centering")
            self.centering_button.started = True
        else:
            self.centering_button.setText("Click-on-Centering")
            self.centering_button.started = False

    def drawDebyeRing(self, xo=0, yo=0, d_draw=1, draw=True):
        if draw:
            detector_distance_cm = self.control.tem_status["eos.GetMagValue"][0] # in cm
            radius_in_px = tool.d2radius_in_px(d_draw, camlen=detector_distance_cm*10)
            self.debyering = QGraphicsEllipseItem(QRectF(xo-radius_in_px, yo-radius_in_px, radius_in_px*2, radius_in_px*2))
            self.debyering.setPen(pg.mkPen('b', width=3))
            self.plot.addItem(self.debyering)
        else:
            self.plot.removeItem(self.debyering)

    def on_tem_update(self):
        angle_x = self.control.tem_status["stage.GetPos"][3]
        self.input_start_angle.setValue(angle_x)
        
        if self.control.tem_status["eos.GetFunctionMode"][0] in [0, 1, 2]:
            magnification = self.control.tem_status["eos.GetMagValue"][2]
            self.input_magnification.setText(magnification)
            # self.drawDebyeRing(draw=False)
        if self.control.tem_status["eos.GetFunctionMode"][0] == 4:
            detector_distance = self.control.tem_status["eos.GetMagValue"][2]
            self.input_det_distance.setText(detector_distance)
            if self.gettem_checkbox.isChecked():
                pass
                # self.drawDebyeRing(xo=self.imageItem.image.shape[0]/2, yo=self.imageItem.image.shape[1]/2, draw=True)
        
        rotation_speed_index = self.control.tem_status["stage.Getf1OverRateTxNum"]
        self.rb_speeds.button(rotation_speed_index).setChecked(True)

    def toggle_rb_speeds(self):
        if self.connecttem_button.started:
            self.control.send.emit("stage.Setf1OverRateTxNum("+ str(self.rb_speeds.checkedId()) +")")
            
    # @Slot(int, str)
    def on_sockstatus_change(self, state, error_msg):
        if state == QAbstractSocket.SocketState.ConnectedState:
            message, color = "Connected", "green"
            self.connecttem_button.started = True
        elif state == QAbstractSocket.SocketState.ConnectingState:
            message, color = "Connecting", "orange"
            self.connecttem_button.started = True
        elif error_msg:
            message = "Error (" + error_msg + ")"
            color = "red"
            self.connecttem_button.started = False
        else:
            message, color = "Disconnected", "red"
            self.connecttem_button.started = False
        self.connecttem_button.setText(message)
        # self.setupUI_temctrl_ready(self, self.connecttem_button.started)
        print(message, color)
        # return message, color
            
    def toggle_connectTEM(self):
        if not self.connecttem_button.started:
            self.control.init.emit()
            self.connecttem_button.setText("Disconnect")
            self.connecttem_button.started = True
            self.control.trigger_getteminfo.emit('N')
        else:
            self.control.trigger_shutdown.emit()
            self.connecttem_button.setText("Connect to TEM")
            self.connecttem_button.started = False
        self.setupUI_temctrl_ready(self, self.connecttem_button.started)
        
if __name__ == "__main__":
    format = "%(message)s"
    logging.basicConfig(format=format, level=logging.INFO)

    app = QApplication(sys.argv)
    
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--stream', type=str, default="tcp://localhost:4545", help="zmq stream")
    parser.add_argument("-d", "--dtype", help="Data type", type = np.dtype, default=np.float32)
    parser.add_argument("-t", "--tem", action="store_true", help="Activate tem-control functions")

    args = parser.parse_args()

    # if args.dtype == np.float32:
    #     cdtype = ctypes.c_float
    # elif args.dtype == np.double:
    #     cdtype = ctypes.c_double
    # else:
    #     raise ValueError("unknown data type")

    # Update the type of global variables 
    globals.dtype = args.dtype
    globals.acc_image = np.zeros((globals.nrow,globals.ncol), dtype = args.dtype)
    globals.tem_mode = args.tem
    logging.debug(type(globals.acc_image[0,0]))

    Rcv = ZmqReceiver(endpoint=args.stream, dtype=args.dtype) 

    viewer = ApplicationWindow(Rcv)
    app_palette = palette.get_palette("dark")
    viewer.setPalette(app_palette)

    viewer.show()
    QCoreApplication.processEvents()

    sys.exit(app.exec())
