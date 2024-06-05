import logging
import globals
import numpy as np
import pyqtgraph as pg
from overlay import draw_overlay 
from pyqtgraph.dockarea import Dock
from PySide6.QtWidgets import (QMainWindow, QVBoxLayout, QWidget,
                                QHBoxLayout, QFrame, QPushButton,
                                QMessageBox)
from PySide6.QtCore import QTimer
from visualization_panel.visualization_panel import VisualizationPanel
from tem_controls.tem_controls import TemControls
from file_operations.file_operations import FileOperations

class ApplicationWindow(QMainWindow):
    def __init__(self, receiver, app):
        super().__init__()
        self.app = app
        self.receiver = receiver
        self.threadWorkerPairs = []
        self.initUI()

    def initUI(self):
        self.setWindowTitle("Viewer 2.0")
        self.setGeometry(50, 50, 1500, 1000)
        
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
        self.glWidget.addItem(self.histogram)
        self.histogram.setLevels(0, 255)
        self.plot.setAspectLocked(True)
        self.roi = pg.RectROI([450, 200], [150, 100], pen=(9,6))
        self.plot.addItem(self.roi)
        self.roi.addScaleHandle([0.5, 1], [0.5, 0.5])
        self.roi.addScaleHandle([0, 0.5], [0.5, 0.5])
        self.roi.sigRegionChanged.connect(self.roiChanged)
        # Initial data (optional)
        data = np.random.rand(globals.nrow,globals.ncol).astype(globals.dtype)
        logging.debug(f"type(data) is {type(data[0,0])}")
        self.imageItem.setImage(data, autoRange = False, autoLevels = False, autoHistogramRange = False)
        # Plot overlays from .reussrc          
        draw_overlay(self.plot)
        # Mouse hovering
        self.imageItem.hoverEvent = self.imageHoverEvent
        
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.dock)

        h_line_1 = QFrame()
        h_line_1.setFrameShape(QFrame.HLine)
        h_line_1.setFrameShadow(QFrame.Plain)
        h_line_1.setStyleSheet("""QFrame {border: none; border-top: 1px solid grey;}""")

        sections_layout = QHBoxLayout()

        self.visualization_panel = VisualizationPanel(self)
        self.tem_controls = TemControls(self)
        self.file_operations = FileOperations(self)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.visualization_panel.captureImage)

        self.timer_fit = QTimer()
        self.timer_fit.timeout.connect(self.tem_controls.getFitParams)

        sections_layout.addWidget(self.visualization_panel, 1)
        sections_layout.addWidget(self.tem_controls, 1)
        sections_layout.addWidget(self.file_operations, 1)

        main_layout.addLayout(sections_layout)

        self.exit_button = QPushButton("Exit", self)
        self.exit_button.clicked.connect(self.do_exit)
        main_layout.addWidget(self.exit_button)
        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        logging.info("Viewer ready!")

    def roiChanged(self):
        roiPos = self.roi.pos()
        roiSize = self.roi.size()
        imageShape = self.imageItem.image.shape
        maxPosX = max(0, imageShape[1] - roiSize[0])
        maxPosY = max(0, imageShape[0] - roiSize[1])
        correctedPosX = min(max(roiPos[0], 0), maxPosX)
        correctedPosY = min(max(roiPos[1], 0), maxPosY)
        correctedSizeX = min(roiSize[0], imageShape[1])
        correctedSizeY = min(roiSize[1], imageShape[0])
        self.roi.setPos([correctedPosX, correctedPosY], update=False)
        self.roi.setSize([correctedSizeX, correctedSizeY], update=False)
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

    def do_exit(self):
        running_threadWorkerPairs = [(thread, worker) for thread, worker in self.threadWorkerPairs if thread.isRunning()]
        if running_threadWorkerPairs:
            # Show warning dialog
            reply = QMessageBox.question(self, 'Thread still running',
                                        "A process is still running. Are you sure you want to exit?",
                                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                globals.exit_flag.value = True
                if self.file_operations.streamWriter is not None:
                    if self.file_operations.streamWriter.write_process.is_alive():
                        self.file_operations.streamWriter.stop()
                if self.file_operations.frameAccumulator is not None:
                    if self.file_operations.frameAccumulator.accumulate_process.is_alive():
                        self.file_operations.frameAccumulator.accumulate_process.terminate()
                        self.file_operations.frameAccumulator.accumulate_process.join()
                if self.tem_controls.fitter is not None:
                    # if self.tem_controls.fitter.fitting_process is not None and self.tem_controls.fitter.fitting_process.is_alive():
                    self.tem_controls.fitter.stop()
                for thread, worker in running_threadWorkerPairs:
                    logging.debug(f'Stopping Thread-Worker pair = ({thread}-{worker}).')
                    self.stopWorker(thread, worker) 
            else: 
                return
                
        logging.info("Exiting app!") 
        self.app.quit()
        