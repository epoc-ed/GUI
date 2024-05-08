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
                               QGraphicsRectItem, QFileDialog, QFrame, QCheckBox)
from PySide6.QtCore import (Qt, QThread, QTimer, QCoreApplication, 
                            QRectF, QMetaObject)
from PySide6.QtGui import QTransform
from workers import *
import multiprocessing as mp
from StreamWriter import StreamWriter
from plot_dialog import *
from line_profiler import LineProfiler
import ctypes

def save_captures(fname, data):
    logging.info(f'Saving: {fname}')
    reuss.io.save_tiff(fname, data)


class ToggleButton(QPushButton):
    def __init__(self, label, window):
        super().__init__(label, window)
        self.started = False


class ApplicationWindow(QMainWindow):
    def __init__(self, receiver):
        super().__init__()
        self.receiver = receiver
        self.threadWorkerPairs = [] # List of constructed (thread, worker) pairs
        self.initUI()

    def initUI(self):
        self.setWindowTitle("Viewer 2.0")
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
        # Sections layout
        sections_layout = QHBoxLayout()

        # Section 1 layout
        group1 = QGroupBox("Streaming && Contrast")
        section1 = QVBoxLayout()
        # Creating buttons for theme switching
        colors_layout = QHBoxLayout()
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

        # Set Initial theme
        self.change_theme('viridis')
        section1.addLayout(colors_layout)
        # Start stream viewing
        self.stream_view_button = ToggleButton("View Stream", self)
        # Auto-contrast button
        self.autoContrastBtn = QPushButton('Auto Contrast', self)
        self.autoContrastBtn.clicked.connect(self.applyAutoContrast)
        #   Layout [           Stream View           ][Auto Contrast]
        hbox = QHBoxLayout()
        hbox.addWidget(self.stream_view_button, 3)
        hbox.addWidget(self.autoContrastBtn, 1) 
        section1.addLayout(hbox)
        # Time Interval
        time_interval = QLabel("Interval (ms):", self)
        self.update_interval = QSpinBox(self)
        self.update_interval.setMaximum(5000)
        self.update_interval.setSuffix(' ms')
        self.update_interval.setValue(cfg.viewer.interval)
        time_interval_layout = QHBoxLayout()
        time_interval_layout.addWidget(time_interval)
        time_interval_layout.addWidget(self.update_interval)
        section1.addLayout(time_interval_layout)
        group1.setLayout(section1)

        # Section 2 layout
        group2 = QGroupBox("Beam Focus")
        section2 = QVBoxLayout()
        # Gaussian Fit of the Beam intensity
        self.btnBeamFocus = ToggleButton("Beam Gaussian Fit", self)
        self.timer_fit = QTimer()
        self.timer_fit.timeout.connect(self.getFitParams)
        self.btnBeamFocus.clicked.connect(self.toggle_gaussianFit)
        
        # Create a checkbox
        self.checkbox = QCheckBox("Enable pop-up Window", self)
        self.checkbox.setChecked(False)

        label_sigma_x = QLabel()
        label_sigma_x.setText("Sigma_x (px)")
        self.sigma_x_spBx = QDoubleSpinBox()
        self.sigma_x_spBx.setValue(1)
        self.sigma_x_spBx.setSingleStep(0.1)

        label_sigma_y = QLabel()
        label_sigma_y.setText("Sigma_y (px)")
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
        BeamFocus_layout.addWidget(self.btnBeamFocus)
        BeamFocus_layout.addWidget(self.checkbox)
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
        self.fname = QLabel("TIFF file name:", self)
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
        h_line = QFrame()
        h_line.setFrameShape(QFrame.HLine)
        h_line.setFrameShadow(QFrame.Plain)
        h_line.setStyleSheet("""QFrame {border: none;border-top: 1px solid grey;}""")
        section3.addWidget(h_line)

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

        self.streamWriter = None
        self.streamWriterButton = ToggleButton("Write Stream in H5", self)
        self.streamWriterButton.setEnabled(False)
        self.streamWriterButton.clicked.connect(self.toggle_hdf5Writer)

        self.last_frame = QLabel("Last written Frame:", self)
        self.last_frame_nb = QSpinBox(self)
        self.last_frame_nb.setMaximum(100000)

        hdf5_writer_layout = QHBoxLayout()
        hdf5_writer_layout.addWidget(self.streamWriterButton, 3)
        hdf5_writer_layout.addWidget(self.last_frame, 1)
        hdf5_writer_layout.addWidget(self.last_frame_nb, 2)

        section3.addLayout(hdf5_writer_layout)
        group3.setLayout(section3)

        sections_layout.addWidget(group1, 1)
        sections_layout.addWidget(group2, 1)
        sections_layout.addWidget(group3, 1)

        main_layout.addLayout(sections_layout)
        # Exit
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
        self.roi.setPos([correctedPosX, correctedPosY])
        self.roi.setSize([correctedSizeX, correctedSizeY])
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
        self.plotDialog.startPlotting(self.sigma_x_spBx.value(), self.sigma_y_spBx.value())
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
        xo = float(fit_result_best_values['xo'])
        yo = float(fit_result_best_values['yo'])        
        sigma_x = float(fit_result_best_values['sigma_x'])
        sigma_y = float(fit_result_best_values['sigma_y'])
        theta_deg = 180*float(fit_result_best_values['theta'])/np.pi
        # Show fitting parameters 
        self.sigma_x_spBx.setValue(sigma_x)
        self.sigma_y_spBx.setValue(sigma_y)
        self.angle_spBx.setValue(theta_deg)
        # Update graph in pop-up Window
        if self.plotDialog != None:
            self.plotDialog.updatePlot(sigma_x, sigma_y, 20)
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
        logging.info("removeAxes called")
        if self.ellipse_fit.scene():
            logging.info("Removing ellipse_fit from scene")
            self.ellipse_fit.scene().removeItem(self.ellipse_fit)
        if self.sigma_x_fit.scene():
            logging.info("Removing sigma_x_fit from scene")
            self.sigma_x_fit.scene().removeItem(self.sigma_x_fit)
        if self.sigma_y_fit.scene():
            logging.info("Removing sigma_y_fit from scene")
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

    def toggle_hdf5Writer(self):
        if not self.streamWriterButton.started:
            folder_name = QFileDialog.getExistingDirectory(self, "Select Directory")
            if not folder_name:
                return  # User canceled folder selection
            self.folder_name = folder_name

            prefix = self.prefix_input.text().strip()
            if not prefix:
                # Handle error: Prefix is mandatory
                return
            
            logging.debug("TCP address for Hdf5 writer to bind to is ", args.stream)
            logging.debug("Data type to build the streamWriter object ", args.dtype)

            formatted_filename = self.generate_filename(prefix)
            self.streamWriter = StreamWriter(filename=formatted_filename, 
                                             endpoint=args.stream, 
                                             dtype=args.dtype)
            self.streamWriter.start()
            self.streamWriterButton.setText("Stop Writing")
            self.streamWriterButton.started = True
        else:
            self.streamWriterButton.setText("Write Stream in H5")
            self.streamWriterButton.started = False
            self.streamWriter.stop()
            self.last_frame_nb.setValue(self.streamWriter.last_frame)
            
    
    def update_h5_file_index(self, index):
            self.h5_file_index = index
            
    def generate_filename(self, prefix):
        now = datetime.datetime.now()
        date_str = now.strftime("%d_%B_%Y_%H:%M:%S")
        index_str = f"{self.h5_file_index:03}"
        self.h5_file_index += 1
        self.index_box.setValue(self.h5_file_index)
        filename = f"{prefix}_{index_str}_{date_str}.h5"
        full_path = os.path.join(self.folder_name, filename)
        return full_path

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
        
        logging.info("Exiting app!") 
        app.quit()


if __name__ == "__main__":
    format = "%(message)s"
    logging.basicConfig(format=format, level=logging.INFO)

    app = QApplication(sys.argv)
    
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--stream', type=str, default="tcp://localhost:4545", help="zmq stream")
    parser.add_argument("-d", "--dtype", help="Data type", type = np.dtype, default=np.float32)

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
    logging.debug(type(globals.acc_image[0,0]))

    Rcv = ZmqReceiver(endpoint=args.stream, dtype=args.dtype) 

    viewer = ApplicationWindow(Rcv)
    app_palette = palette.get_palette("dark")
    viewer.setPalette(app_palette)

    viewer.show()
    QCoreApplication.processEvents()

    sys.exit(app.exec())
