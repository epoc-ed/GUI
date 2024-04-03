import time
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
                               QGraphicsRectItem)
from PySide6.QtCore import (Qt, QThread, QTimer, QCoreApplication, 
                            QRectF, QMetaObject)
from PySide6.QtGui import QPalette, QColor, QTransform
from workers import *
from plot_dialog import *
from line_profiler import LineProfiler


# Define the available theme of the main window
def get_palette(name):
    if name == "dark":
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(53, 53, 53))
        palette.setColor(QPalette.WindowText, Qt.GlobalColor.white)
        palette.setColor(QPalette.Base, QColor(25, 25, 25))
        palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
        palette.setColor(QPalette.ToolTipBase, Qt.GlobalColor.white)
        palette.setColor(QPalette.ToolTipText, Qt.GlobalColor.white)
        palette.setColor(QPalette.Text, Qt.GlobalColor.white)
        palette.setColor(QPalette.Button, QColor(53, 53, 53))
        palette.setColor(QPalette.ButtonText, Qt.GlobalColor.white)
        palette.setColor(QPalette.BrightText, Qt.GlobalColor.red)
        palette.setColor(QPalette.Link, QColor(42, 130, 218))
        palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
        palette.setColor(QPalette.HighlightedText, Qt.GlobalColor.black)
        return palette
    else:
        raise NotImplementedError("only dark theme is implemented")


def save_captures(fname, data):
    print(f'Saving: {fname}')
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
        self.i_h5 = 0 # Indexing the outputted hdf5 files
        self.initUI()

    def initUI(self):
        self.setWindowTitle("Viewer 2.0")
        self.setGeometry(50, 50, 1050, 750)
        
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
        self.histogram.gradient.loadPreset('viridis')
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
        data = np.random.rand(globals.nrow,globals.ncol)
        # Plot overlays from .reussrc          
        draw_overlay(self.plot)
        self.imageItem.setImage(data, autoRange = False, autoLevels = False, autoHistogramRange = False)
        # Mouse Hovering
        self.imageItem.hoverEvent = self.imageHoverEvent

        ################
        # General Layout
        ################
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.dock)
        # Sections layout
        sections_layout = QHBoxLayout()

        # Section 1 layout
        group1 = QGroupBox("Streaming && Contrast")
        section1 = QVBoxLayout()
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
        
        label_sigma_x = QLabel()
        label_sigma_x.setText("Sigma_x (px)")
        self.sigma_x_spBx = QDoubleSpinBox()
        self.sigma_x_spBx.setSingleStep(0.1)

        label_sigma_y = QLabel()
        label_sigma_y.setText("Sigma_y (px)")
        label_sigma_y.setStyleSheet('color: red;')
        self.sigma_y_spBx = QDoubleSpinBox()
        self.sigma_y_spBx.setStyleSheet('color: red;')
        self.sigma_y_spBx.setSingleStep(0.1)

        label_rot_angle = QLabel()
        label_rot_angle.setText("Theta (deg)")
        self.angle_spBx = QSpinBox()
        self.angle_spBx.setMinimum(-90)
        self.angle_spBx.setMaximum(90)
        self.angle_spBx.setSingleStep(15)

        BeamFocus_layout = QVBoxLayout()
        BeamFocus_layout.addWidget(self.btnBeamFocus)
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
        self.fname = QLabel("tiff_file_name:", self)
        self.fname_input = QLineEdit(self)
        self.fname_input.setText('file')
        self.findex = QLabel("file_index:", self)
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
        # Stream Writer
        self.streamWriterButton = ToggleButton("Write Stream in H5", self)
        self.streamWriterButton.setEnabled(False)
        self.streamWriterButton.clicked.connect(self.toggle_hdf5Writer)

        self.last_frame = QLabel("Last written Frame:", self)
        self.last_frame_nb = QSpinBox(self)
        self.last_frame_nb.setMaximum(5000)

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

    def applyAutoContrast(self):
        data_flat = self.imageItem.image.flatten()
        histogram = Histogram(Regular(1000000, data_flat.min(), data_flat.max()))
        histogram.fill(data_flat)
        cumsum = np.cumsum(histogram.view())
        total = cumsum[-1]
        low_thresh = np.searchsorted(cumsum, total * 0.01)
        high_thresh = np.searchsorted(cumsum, total * 0.99999)
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
        roiPos = self.roi.pos()
        roiSize = self.roi.size()
        print(f"ROI Position: {roiPos}, Size: {roiSize}")

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
            print("Starting reading process")
            # Adjust button display according to ongoing state of process
            self.stream_view_button.setText("Stop")
            self.plot.setTitle("View of the Stream")
            self.timer.setInterval(self.update_interval.value())
            self.stream_view_button.started = True
            print(f"Timer interval: {self.timer.interval()}")
            # Start timer and enable file operation buttons
            self.timer.start(10)
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
        print(f"{worker.__str__()} is Ready!")
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
        if isinstance(worker, Hdf5_Writer):
            worker.finished.connect(self.update_last_frame_written)

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
            print("Starting fitting process")

            self.btnBeamFocus.setText("Stop Fitting")
            self.btnBeamFocus.started = True
            # Pop-up Window
            self.showPlotDialog()    
            # Timer started
            self.timer_fit.start()
        else:
            self.btnBeamFocus.setText("Beam Gaussian Fit")
            self.btnBeamFocus.started = False
            self.timer_fit.stop()  
            # Close Pop-up Window
            self.plotDialog.close()
            self.stopWorker(self.thread_fit, self.fitter)

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
        self.plotDialog.updatePlot(sigma_x, sigma_y, 20)
        # Draw the fitting line at the FWHM of the 2d-gaussian
        self.drawFittingEllipse(xo,yo,sigma_x, sigma_y, theta_deg)

    def drawFittingEllipse(self, xo, yo, sigma_x, sigma_y, theta_deg):
        # p = 0.5 is equivalent to using the Full Width at Half Maximum (FWHM)
        # where FWHM = 2*sqrt(2*ln(2)) * sigma
        p = 0.15
        alpha = 2*np.sqrt(-2*math.log(p))
        width = alpha * sigma_x # Use 
        height = alpha * sigma_y # 
        # Check if the item is added to a scene, and remove it if so
        scene = self.ellipse_fit.scene() 
        scene_ = self.sigma_x_fit.scene() 
        scene__ = self.sigma_y_fit.scene() 
        if scene:  
            scene.removeItem(self.ellipse_fit)
            scene_.removeItem(self.sigma_x_fit)
            scene__.removeItem(self.sigma_y_fit)
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

    def stopWorker(self, thread, worker):
        if isinstance(worker, Hdf5_Writer):
            globals.write_hdf5 = False
        if thread.isRunning():
            thread.quit()
            thread.wait() # Wait for the thread to finish
        self.threadCleanup(thread, worker)
        
    def threadCleanup(self, thread, worker):
        index_to_delete = None
        for i, (t, worker) in enumerate(self.threadWorkerPairs):
            if t == thread:
                if worker is not None:
                    if isinstance(worker, Gaussian_Fitter):
                        worker.finished.disconnect(self.updateFitParams)
                        worker.finished.disconnect(self.getFitterReady)
                    print(f"Stopping {worker.__str__()}!")
                    worker.deleteLater() # Schedule the worker for deletion
                    worker = None
                    print("Process stopped!")
                index_to_delete = i
                break
        if index_to_delete is not None:
            del self.threadWorkerPairs[index_to_delete]
        thread.deleteLater()  # Schedule the thread for deletion
        thread = None
        # Make sure that the destroyed workers are also disabled in the logic
        if isinstance(worker, Gaussian_Fitter):
            self.fitterWorkerReady = False
        if isinstance(worker, Reader):
            self.readerWorkerReady = False

    def toggle_hdf5Writer(self):
        if not self.streamWriterButton.started:
            self.thread_h5 = QThread()
            # self.streamWriter = Hdf5_Writer(filename="all_in_one_hdf5_file")
            self.streamWriter = Hdf5_Writer(filename=f"hdf5_file_{self.i_h5}")
            self.i_h5 += 1
            self.threadWorkerPairs.append((self.thread_h5, self.streamWriter))              
            self.initializeWorker(self.thread_h5, self.streamWriter) # Initialize the worker thread and fitter
            self.thread_h5.start()
            self.streamWriterButton.setText("Stop Writing")
            self.streamWriterButton.started = True
        else:
            self.streamWriterButton.setText("Write Stream in H5")
            self.streamWriterButton.started = False
            self.stopWorker(self.thread_h5, self.streamWriter) # Properly stop and cleanup worker and thread

    def update_last_frame_written(self, nb_of_frame):
        self.last_frame_nb.setValue(nb_of_frame)

    def do_exit(self):
        running_threadWorkerPairs = [(thread, worker) for thread, worker in self.threadWorkerPairs if thread.isRunning()]
        if running_threadWorkerPairs:
            # Show warning dialog
            reply = QMessageBox.question(self, 'Thread still running',
                                        "A process is still running. Are you sure you want to exit?",
                                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                for thread, worker in running_threadWorkerPairs:
                    print(f'Stopping Thread-Worker pair = ({thread}-{worker}).')
                    self.stopWorker(thread, worker)
                print("Exiting app!") 
                app.quit()  
            else: 
                pass
        else:
            app.quit()


if __name__ == "__main__":

    app = QApplication(sys.argv)
    
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--stream', type=str, default="tcp://localhost:4545", help="zmq stream")
    parser.add_argument("-d", "--dtype", help="Data type", type = np.dtype, default=np.float32)

    args = parser.parse_args()
    
    Rcv = ZmqReceiver(args.stream) 

    viewer = ApplicationWindow(Rcv)
    palette = get_palette("dark")
    viewer.setPalette(palette)

    viewer.show()
    QCoreApplication.processEvents()

    sys.exit(app.exec())