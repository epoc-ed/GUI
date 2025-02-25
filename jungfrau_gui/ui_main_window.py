import logging
from . import globals
import numpy as np
import pyqtgraph as pg
from .ui_components.overlay import draw_overlay 
from pyqtgraph.dockarea import Dock
from PySide6.QtWidgets import (QMainWindow, QVBoxLayout, QWidget,
                                QHBoxLayout, QPushButton, QGridLayout,
                                QMessageBox, QTabWidget, QLabel)
from PySide6.QtCore import Qt, QObject, QEvent, QTimer
from PySide6.QtGui import QShortcut, QKeySequence
from .ui_components.visualization_panel.visualization_panel import VisualizationPanel
from .ui_components.tem_controls.tem_controls import TemControls
from .ui_components.file_operations.file_operations import FileOperations
from .ui_components.utils import create_gaussian
from .ui_components.toggle_button import ToggleButton

import jungfrau_gui.ui_threading_helpers as thread_manager

from importlib import resources

from boost_histogram import Histogram
from boost_histogram.axis import Regular

from epoc import ConfigurationClient, auth_token, redis_host

from PySide6.QtGui import QFont

font_big = QFont("Arial", 11)
font_big.setBold(True)

def get_git_info():
    # Load version from installed package resources
    try:
        version = resources.read_text('jungfrau_gui', 'version.txt').strip()
        return f"Viewer {version}"
    except FileNotFoundError as e:
        logging.debug(f"File not found: {e}")
        pass  # Fall back to Git if the file is not found
    
    try:
        # Fall back to git if version.txt is not available
        return f"Viewer {globals.tag}/{globals.branch}"
    except Exception as e:
        return "Viewer x.x.x"

class EventFilter(QObject):
    def __init__(self, histogram, parent=None):
        super().__init__(parent)
        self.histogram = histogram

    def eventFilter(self, obj, event):
        logging.debug(f"Event detected: {event.type()}")  # More general debug statement
        if event.type() == QEvent.HoverEnter:
            logging.debug("Hover Enter Detected")
            self.histogram.show()
        elif event.type() == QEvent.HoverLeave:
            logging.debug("Hover Leave Detected")
            self.histogram.hide()
        return super().eventFilter(obj, event)
    
class ApplicationWindow(QMainWindow):
    def __init__(self, receiver, app):
        super().__init__()
        self.app = app
        self.receiver = receiver
        self.threadWorkerPairs = []
        self.version = get_git_info()
        self.initUI()

    def initUI(self):
        self.cfg =  ConfigurationClient(redis_host(), token=auth_token())

        # Window Geometry
        self.setWindowTitle(self.version)
        self.setGeometry(50, 50, 1500, 1000)

        # pyqtgraph config params
        pg.setConfigOptions(imageAxisOrder='row-major')
        pg.mkQApp()
        
        self.dock = Dock("Image", size=(1000, 350))
        self.glWidget = pg.GraphicsLayoutWidget(self)
        self.plot = self.glWidget.addPlot(title="")
        self.dock.addWidget(self.glWidget)
        
        self.histogram = pg.HistogramLUTItem()
        self.imageItem = pg.ImageItem()
        # self.imageItem.setOpts(nanMask=True)
        self.plot.addItem(self.imageItem)
        self.histogram.setImageItem(self.imageItem)
        self.glWidget.addItem(self.histogram)
        self.histogram.setLevels(0, 5000)
        self.histogram.setHistogramRange(0, 5000, padding=0)
        self.histogram.autoHistogramRange = False
        self.histogram.hide()  # Start hidden
        self.plot.setAspectLocked(True)

        # Set up event filter for hover and apply it correctly
        self.hoverFilter = EventFilter(self.histogram, self)
        self.glWidget.setAttribute(Qt.WA_Hover, True)  # Explicitly enable hover events
        self.glWidget.installEventFilter(self.hoverFilter)

        # ROI setup
        # self.roi = pg.RectROI([450, 200], [150, 100], pen=(9,6))
        self.roi = pg.RectROI([globals.ncol//2+1-75, globals.nrow//2+1-50], [150, 100], pen=(9,6))
        self.plot.addItem(self.roi)
        self.roi.addScaleHandle([0.5, 1], [0.5, 0.5])
        self.roi.addScaleHandle([0, 0.5], [0.5, 0.5])
        self.roi.addScaleHandle([0.5, 0], [0.5, 0.5])
        self.roi.addScaleHandle([1, 0.5], [0.5, 0.5])
        self.roi.sigRegionChanged.connect(self.roiChanged)

        # Initial data (optional)
        data = create_gaussian(1000, globals.ncol, globals.nrow, 30, 15, np.deg2rad(35))
        logging.debug(f"type(data) is {type(data[0,0])}")
        self.imageItem.setImage(data, autoRange = False, autoLevels = False, autoHistogramRange = False)
        
        # Plot overlays         
        draw_overlay(self.plot)
        
        # Mouse hovering
        self.imageItem.hoverEvent = self.imageHoverEvent
        
        """ *********** """
        """ Main Layout """
        """ *********** """

        main_layout = QVBoxLayout()
        tools_layout = QHBoxLayout()

        dock_layout = QVBoxLayout()

        contrast_section = QVBoxLayout()

        contrast_group = QGridLayout()
        contrast_label = QLabel("Contrast Controls")
        contrast_label.setFont(font_big)

        contrast_section.addWidget(contrast_label)

        self.autoContrastBtn = ToggleButton('Apply Auto Contrast', self)
        self.autoContrastBtn.setStyleSheet('background-color: green; color: white;')
        self.autoContrastBtn.clicked.connect(self.toggle_autoContrast)
        self.resetContrastBtn = QPushButton("Reset Contrast")
        self.resetContrastBtn.clicked.connect(lambda: self.set_contrast(self.cfg.viewer_cmin, self.cfg.viewer_cmax))

        self.contrast_0_Btn = QPushButton("-50 - 50")
        self.contrast_1_Btn = QPushButton("0 - 100")
        self.contrast_2_Btn = QPushButton("0 - 500")
        self.contrast_3_Btn = QPushButton("0 - 1000")
        self.contrast_4_Btn = QPushButton("0 - 1e5")

        self.contrast_0_Btn.clicked.connect(lambda: self.set_contrast(-50, 50))
        self.contrast_1_Btn.clicked.connect(lambda: self.set_contrast(0, 100))
        self.contrast_2_Btn.clicked.connect(lambda: self.set_contrast(0, 500))
        self.contrast_3_Btn.clicked.connect(lambda: self.set_contrast(0, 1000))
        self.contrast_4_Btn.clicked.connect(lambda: self.set_contrast(0, 100000))

        contrast_group.addWidget(self.autoContrastBtn, 0, 0,  1, 4)
        contrast_group.addWidget(self.resetContrastBtn, 0, 4, 1, 4)

        contrast_group.addWidget(self.contrast_0_Btn, 0, 8,  1, 1 )
        contrast_group.addWidget(self.contrast_1_Btn, 0, 9,  1, 1 )
        contrast_group.addWidget(self.contrast_2_Btn, 0, 10, 1, 1 )
        contrast_group.addWidget(self.contrast_3_Btn, 0, 11, 1, 1 )
        contrast_group.addWidget(self.contrast_4_Btn, 0, 12, 1, 1 )

        contrast_section.addLayout(contrast_group)

        dock_layout.addWidget(self.dock)
        dock_layout.addLayout(contrast_section)

        tools_layout.addLayout(dock_layout,3)

        tab_widget = QTabWidget()

        self.visualization_panel = VisualizationPanel(self)
        self.file_operations = FileOperations(self)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.visualization_panel.captureImage)

        self.timer_contrast = QTimer(self)
        self.timer_contrast.timeout.connect(self.applyAutoContrast)

        self.tem_controls = TemControls(self)
        
        self.timer_fit = QTimer()
        self.timer_fit.timeout.connect(self.tem_controls.getFitParams)
        
        # self.imageItem.mouseClickEvent = self.tem_controls.tem_action.imageMouseClickEvent
        
        tab_widget.addTab(self.visualization_panel, "Visualization Panel")
        tab_widget.addTab(self.tem_controls, "TEM Controls")
        tab_widget.addTab(self.file_operations, "File operations")

        tools_layout.addWidget(tab_widget, 1)

        main_layout.addLayout(tools_layout)

        self.exit_button = QPushButton("Exit", self)
        main_layout.addWidget(self.exit_button)
        self.exit_button.clicked.connect(self.do_exit)

        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)
        
        # Create a keyboard shortcut for Auto Range
        self.shortcut_autorange = QShortcut(QKeySequence("A"), self)
        self.shortcut_autorange.activated.connect(self.auto_range)

        logging.info("Viewer ready!")

    def auto_range(self):
        """Trigger the Auto Range (center image and scale view)."""
        self.plot.autoRange()

    def set_contrast(self, lower, upper):
        self.timer_contrast.stop()
        self.autoContrastBtn.started = False
        self.autoContrastBtn.setStyleSheet('background-color: green; color: white;')
        self.autoContrastBtn.setText('Apply Auto Contrast')
        self.histogram.setLevels(lower, upper)
    
    def toggle_autoContrast(self):
        if not self.autoContrastBtn.started:
            self.autoContrastBtn.setStyleSheet('background-color: red; color: white;')
            self.autoContrastBtn.setText('Stop Auto Contrast')
            self.autoContrastBtn.started = True
            self.timer_contrast.start(10) # Assuming 100Hz streaming frequency at most
        else:
            self.timer_contrast.stop()
            self.autoContrastBtn.started = False
            self.autoContrastBtn.setStyleSheet('background-color: green; color: white;')
            self.autoContrastBtn.setText('Apply Auto Contrast')
    
    # @profile
    def applyAutoContrast(self, histo_boost = False):
        if histo_boost:
            data_flat = self.imageItem.image.flatten()
            histogram = Histogram(Regular(1000000, data_flat.min(), data_flat.max()))
            histogram.fill(data_flat)
            cumsum_pre = np.cumsum(histogram.view())
            cumsum = cumsum_pre[np.where(cumsum_pre < np.iinfo('int32').max-1)]
            total = cumsum[-1]
            low_thresh = np.searchsorted(cumsum, total * 0.01)
            high_thresh = np.searchsorted(cumsum, total * 0.99999)
        else:
            image_data = self.imageItem.image
            image_data_deloverflow = image_data[np.where(image_data < np.iinfo('int32').max-1)]
            low_thresh, high_thresh = np.percentile(image_data_deloverflow, (1, 99.999))

        self.histogram.setLevels(low_thresh, high_thresh)

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
        if globals.tem_mode:
            logging.debug(f"Control has - \033[1m{self.tem_controls.tem_action.control.task.task_name}\033[0m\033[34m - task alive!")
            thread_manager.handle_tem_task_cleanup(self.tem_controls.tem_action.control)
        thread_manager.disconnect_worker_signals(worker)
        thread_manager.terminate_thread(thread)
        thread_manager.remove_worker_thread_pair(self.threadWorkerPairs, thread)
        thread_manager.reset_worker_and_thread(worker, thread)

    def do_exit(self):
        # Prevent closing the GUI while JFJ is not Idle
        # TODO Add flexibily as a function of the nature of the ongoing JFJ operation
        if self.visualization_panel.jfjoch_client:
            if self.visualization_panel.jfjoch_client.status().state == 'Measuring':
                reply = QMessageBox.question(
                    self,
                    "Jungfraujoch is not Idle",
                    "The Jungfraujoch is currently measuring...Do you want to proceed anyway?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.No:
                    return

        # Dealing with ongoing operation of the GUI after premature 'Exit' request
        running_threadWorkerPairs = [(thread, worker) for thread, worker in self.threadWorkerPairs if thread and thread.isRunning()]
        if running_threadWorkerPairs:
            # Show warning dialog
            reply = QMessageBox.question(self, 'Thread still running',
                                        "A process is still running. Are you sure you want to exit?",
                                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                globals.exit_flag.value = True
                """ if self.file_operations.streamWriter is not None:
                    if self.file_operations.streamWriter.write_process.is_alive():
                        self.file_operations.streamWriter.stop() """
                # if self.file_operations.frameAccumulator is not None:
                #     if self.file_operations.frameAccumulator.accumulate_process.is_alive():
                #         self.file_operations.frameAccumulator.accumulate_process.terminate()
                #         self.file_operations.frameAccumulator.accumulate_process.join()
                # if self.tem_controls.fitter is not None:
                #     self.tem_controls.fitter.stop()
                for thread, worker in running_threadWorkerPairs:
                    logging.warning(f'Stopping Thread-Worker pair = ({thread}-{worker}).')
                    self.stopWorker(thread, worker) 
            else: 
                return

        if globals.tem_mode:
            if self.tem_controls.tem_tasks.connecttem_button.started:
                self.tem_controls.tem_action.control.trigger_shutdown.emit()

        logging.info("Exiting app!") 
        self.app.quit()
        
