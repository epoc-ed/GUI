import time
import argparse
import ctypes
import zmq
import numpy as np
import sys
from pathlib import Path
import math

import overlay_pyqt
from overlay_pyqt import draw_overlay

import reuss 
from reuss import config as cfg

from fit_beam_intensity import fit_2d_gaussian_roi

import pyqtgraph as pg
from pyqtgraph.dockarea import DockArea, Dock

from PySide6.QtWidgets import (QMainWindow, QPushButton, QSpinBox, QDoubleSpinBox,
                               QLabel, QApplication, QHBoxLayout, QVBoxLayout, 
                               QWidget, QGraphicsEllipseItem, QGraphicsRectItem)
from PySide6.QtCore import (Qt, QThread, Signal, QTimer, QCoreApplication, 
                            QRectF)
from PySide6.QtGui import QPalette, QColor, QTransform


#Configuration
nrow = cfg.nrows()
ncol = cfg.ncols()


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


# Receiver of the ZMQ stream
class ZmqReceiver:
    def __init__(self, endpoint, 
                 timeout_ms = 100, 
                 dtype = np.float32,
                 n_frames = 2, n_acc = 1):

        self.dt = dtype
        self.n_frames = n_frames
        self.n_acc = n_acc
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.SUB)
        self.socket.setsockopt(zmq.RCVTIMEO, timeout_ms)
        self.socket.setsockopt(zmq.RCVHWM, self.n_frames)
        self.socket.setsockopt(zmq.RCVBUF, self.n_frames*1024*1024*np.dtype(self.dt).itemsize)
        self.socket.connect(endpoint)
        self.socket.setsockopt(zmq.SUBSCRIBE, b"")

    def get_frame(self):
        for i in range(self.n_acc):
            msgs = self.socket.recv_multipart()
            frame_nr = np.frombuffer(msgs[0], dtype = np.int64)[0]
            image = np.frombuffer(msgs[1], dtype = np.float32).reshape(512, 1024)
        return image, frame_nr


class Reader(QThread):
    finished = Signal(object, object)  # Signal to indicate completion and carry results

    def __init__(self, receiver):
        super(Reader, self).__init__()
        self.receiver = receiver

    def run(self):
        image, frame_nr = self.receiver.get_frame()  # Retrieve image and header
        self.finished.emit(image, frame_nr)  # Emit signal with results


class Gaussian_Fitter(QThread):
    finished = Signal(object)
    # progress = Signal(Arg)  # Use Signal with the argument type

    def __init__(self, imageItem, roi):
        super(Gaussian_Fitter, self).__init__()
        self.imageItem = imageItem
        self.roi = roi
        
    def run(self):
        im = self.imageItem.image
        roiPos = self.roi.pos()
        roiSize = self.roi.size()
        roi_start_row = int(np.floor(roiPos.y()))
        roi_end_row = int(np.ceil(roiPos.y() + roiSize.y()))
        roi_start_col = int(np.floor(roiPos.x()))
        roi_end_col = int(np.ceil(roiPos.x() + roiSize.x()))
        fit_result = fit_2d_gaussian_roi(im, roi_start_row, roi_end_row, roi_start_col, roi_end_col)
        # self.progress.emit(smthing to inform about fitting status or...)
        self.finished.emit(fit_result.best_values)


class ToggleButton(QPushButton):
    def __init__(self, label, window):
        super().__init__(label, window)
        self.started = False


class ApplicationWindow(QMainWindow):
    def __init__(self, receiver):
        super().__init__()
        self.receiver = receiver
        
        self.reader = Reader(self.receiver)  # Create a Reader worker instance
        self.reader.finished.connect(self.updateUI)  # Connect signal to slot

        self.initUI()

    def initUI(self):
        self.setWindowTitle("Viewer 2.0")
        self.setGeometry(100, 100, 1100, 700)
        
        pg.setConfigOptions(imageAxisOrder='row-major')
        pg.mkQApp()

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
        data = np.random.rand(nrow,ncol)

        self.fitter = Gaussian_Fitter(self.imageItem, self.roi)
        self.fitter.finished.connect(self.updateFitParams)

        # Plot overlays from .reussrc          
        draw_overlay(self.plot)
        self.imageItem.setImage(data, autoRange = False, autoLevels = False, autoHistogramRange = False)

        self.imageItem.hoverEvent = self.imageHoverEvent

        self.stream_view_button = ToggleButton("View Stream", self)

        time_interval = QLabel("Interval (ms):", self)
        self.update_interval = QSpinBox(self)
        self.update_interval.setMaximum(5000)
        self.update_interval.setSuffix(' ms')
        self.update_interval.setValue(cfg.viewer.interval)

        time_interval_layout = QHBoxLayout()
        time_interval_layout.addWidget(time_interval)
        time_interval_layout.addWidget(self.update_interval)

        self.spBxFrame , self.integerSpinBox = self.createSpinBox("Accumulate frames:", 1, self.receiver.n_acc)
        self.integerSpinBox.valueChanged.connect(self.frameNbTakesChange)

        spBxFr_layout = QHBoxLayout()
        spBxFr_layout.addWidget(self.spBxFrame)
        spBxFr_layout.addWidget(self.integerSpinBox)
        
        self.btnBeamFocus = QPushButton("Beam Gaussian Fit", self)
        self.btnBeamFocus.clicked.connect(self.getFitParams)

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

        self.exit_button = QPushButton("Exit", self)
        self.exit_button.clicked.connect(self.do_exit)

        BeamFocus_layout = QHBoxLayout()
        BeamFocus_layout.addWidget(self.btnBeamFocus)
        BeamFocus_layout.addWidget(label_sigma_x)
        BeamFocus_layout.addWidget(self.sigma_x_spBx)
        BeamFocus_layout.addWidget(label_sigma_y)
        BeamFocus_layout.addWidget(self.sigma_y_spBx)
        BeamFocus_layout.addWidget(label_rot_angle)
        BeamFocus_layout.addWidget(self.angle_spBx)

        gen_layout = QVBoxLayout()
        gen_layout.addWidget(self.dock)
        gen_layout.addWidget(self.stream_view_button)
        gen_layout.addLayout(time_interval_layout)
        gen_layout.addLayout(spBxFr_layout)
        gen_layout.addLayout(BeamFocus_layout)
        gen_layout.addWidget(self.exit_button)
        
        widget = QWidget()
        widget.setLayout(gen_layout)
        self.setCentralWidget(widget)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.captureImage)
        self.stream_view_button.clicked.connect(self.toggle_viewStream)
    
    def do_exit(self):
        print('Exiting')
        app.quit()
    
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
        global t0
        t0 = time.time()
        if not self.stream_view_button.started:
            self.stream_view_button.setText("Stop")
            self.plot.setTitle("View of the Stream")
            self.timer.setInterval(self.update_interval.value())
            self.stream_view_button.started = True
            print(f"Timer interval: {self.timer.interval()}")
            # wait_flag.value = False
            self.timer.start(10)
            # self.accumulate_button.setEnabled(True)
        else:
            self.stream_view_button.setText("View Stream")
            self.plot.setTitle("Stream stopped at the current Frame")
            self.stream_view_button.started = False
            self.timer.stop()
            # wait_flag.value = True
            # self.accumulate_button.setEnabled(False)

    def captureImage(self):
        if not self.reader.isRunning():
            self.reader.run()  # Start the Reader worker thread

    def updateUI(self, image, frame_nr):
        self.imageItem.setImage(image, autoRange = False, autoLevels = False, autoHistogramRange = False) ## .T)
        # self.statusBar().showMessage(f'Frame: {frame_nr}')
        # print(f'Total Number of Frames: {frame_nr}')

    def getFitParams(self):
        if not self.fitter.isRunning():
            self.fitter.run()  # Start the Fitter worker thread

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

        # Draw the fitting line at the FWHM of the 2d-gaussian
        self.drawFittingEllipse(xo,yo,sigma_x, sigma_y, theta_deg)

    def drawFittingEllipse(self, xo, yo, sigma_x, sigma_y, theta_deg):
        # p = 0.5 is equivalent to using the Full Width at Half Maximum (FWHM)
        # where FWHM = 2*sqrt(2*ln(2)) * sigma
        p = 0.15
        alpha = 2*np.sqrt(-2*math.log(p))
        print(f"Width/sigma_x = Height/sigma_y = {alpha}")
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

    def createSpinBox(self, text, step_val, set_value):
        spBx = QLabel()
        spBx.setText(text)
        
        valSpinBox = QSpinBox()
        valSpinBox.setMinimum(0)
        valSpinBox.setMaximum(1000)
        valSpinBox.setSingleStep(step_val)
        valSpinBox.setValue(set_value)
        return spBx, valSpinBox

    def frameNbTakesChange(self, value):
        self.receiver.n_acc = value
        print(f'Number of Frames: {value}')

if __name__ == "__main__":
    t0 = time.time()

    app = QApplication(sys.argv)
    
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--stream', type=str, default="tcp://localhost:4545", help="zmq stream")
    args = parser.parse_args()
    
    Rcv = ZmqReceiver(args.stream) 
    
    viewer = ApplicationWindow(Rcv)
    palette = get_palette("dark")
    viewer.setPalette(palette)

    viewer.show()
    QCoreApplication.processEvents()

    sys.exit(app.exec())