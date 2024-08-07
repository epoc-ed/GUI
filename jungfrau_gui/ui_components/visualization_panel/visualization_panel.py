import time
import logging
import numpy as np
from boost_histogram import Histogram
from boost_histogram.axis import Regular
from PySide6.QtCore import Qt, QThread, QMetaObject
from PySide6.QtWidgets import (QWidget, QGroupBox, QVBoxLayout, QHBoxLayout,
                                QLabel, QPushButton, QFrame, QSpinBox,
                                QGridLayout, QSizePolicy)

from .reader import Reader

from reuss import config as cfg
from ...ui_components.toggle_button import ToggleButton
from ... import globals
from ...ui_components.tem_controls.ui_temspecific import TEMDetector
from ...ui_components.utils import create_horizontal_line_with_margin

class VisualizationPanel(QGroupBox):
    def __init__(self, parent):
        # super().__init__("Visualization Panel")
        super().__init__()
        self.parent = parent
        self.initUI()

    def initUI(self):
        section_visual = QVBoxLayout()
        section_visual.setContentsMargins(10, 10, 10, 10)  # Minimal margins
        section_visual.setSpacing(10) 

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
        for name, button in self.color_buttons.items():
            colors_layout.addWidget(button)
            button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            button.clicked.connect(lambda checked=False, b=name: self.change_theme(b))
        colors_group.addLayout(colors_layout)
        self.change_theme('viridis')
        section_visual.addLayout(colors_group)
        section_visual.addWidget(create_horizontal_line_with_margin(15))

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
        self.stream_view_button.clicked.connect(self.toggle_viewStream)
        """ contrast_box = QVBoxLayout() """
        self.autoContrastBtn = ToggleButton('Apply Auto Contrast', self)
        self.autoContrastBtn.setStyleSheet('background-color: green; color: white;')
        self.autoContrastBtn.clicked.connect(self.toggle_autoContrast)
        self.resetContrastBtn = QPushButton("Reset Contrast")
        self.resetContrastBtn.clicked.connect(self.resetContrast)
        
        view_contrast_group = QVBoxLayout()
        view_contrast_label = QLabel("Streaming & Contrast")
        view_contrast_group.addWidget(view_contrast_label)

        grid_1 = QGridLayout()
        grid_1.addWidget(self.stream_view_button, 0, 0, 2, 2)  # Span two rows two columns
        grid_1.addWidget(self.autoContrastBtn, 0, 2)
        grid_1.addWidget(self.resetContrastBtn, 1, 2)

        view_contrast_group.addLayout(grid_1)
        section_visual.addLayout(view_contrast_group)
        # section_visual.addWidget(create_horizontal_line_with_margin())

        time_interval = QLabel("Acquisition Interval (ms):", self)
        self.update_interval = QSpinBox(self)
        self.update_interval.setMaximum(5000)
        self.update_interval.setSuffix(' ms')
        self.update_interval.setValue(cfg.viewer.interval)
        self.update_interval.valueChanged.connect(lambda x: self.parent.timer.setInterval(x))
        time_interval_layout = QHBoxLayout()
        time_interval_layout.addWidget(time_interval)
        time_interval_layout.addWidget(self.update_interval)
        section_visual.addLayout(time_interval_layout)
        section_visual.addWidget(create_horizontal_line_with_margin(15))

        if globals.tem_mode:
            tem_detector_layout = QVBoxLayout()
            tem_detector_label = QLabel("Detector")

            self.tem_detector = TEMDetector()
            tem_detector_layout.addWidget(tem_detector_label)
            tem_detector_layout.addWidget(self.tem_detector)

            section_visual.addLayout(tem_detector_layout)
        else: 
            pass
        
        section_visual.addStretch()
        self.setLayout(section_visual)

    def change_theme(self, theme):
        self.parent.histogram.gradient.loadPreset(theme)

    def resetContrast(self):
        self.parent.histogram.setLevels(0, 255)

    def toggle_autoContrast(self):
        if not self.autoContrastBtn.started:
            self.autoContrastBtn.setStyleSheet('background-color: red; color: white;')
            self.autoContrastBtn.setText('Stop Auto Contrast')
            self.autoContrastBtn.started = True
            self.parent.timer_contrast.start(10) # Assuming 100Hz streaming frequency at most
        else:
            self.parent.timer_contrast.stop()
            self.autoContrastBtn.started = False
            self.autoContrastBtn.setStyleSheet('background-color: green; color: white;')
            self.autoContrastBtn.setText('Apply Auto Contrast')
    
    # @profile
    def applyAutoContrast(self, histo_boost = False):
        if histo_boost:
            data_flat = self.parent.imageItem.image.flatten()
            histogram = Histogram(Regular(1000000, data_flat.min(), data_flat.max()))
            histogram.fill(data_flat)
            cumsum = np.cumsum(histogram.view())
            total = cumsum[-1]
            low_thresh = np.searchsorted(cumsum, total * 0.01)
            high_thresh = np.searchsorted(cumsum, total * 0.99999)
        else:
            low_thresh, high_thresh = np.percentile(self.parent.imageItem.image, (1, 99.999))
        
        self.parent.histogram.setLevels(low_thresh, high_thresh)

    def toggle_viewStream(self):
        if not self.stream_view_button.started:
            self.thread_read = QThread()
            self.streamReader = Reader(self.parent.receiver)
            self.parent.threadWorkerPairs.append((self.thread_read, self.streamReader))                              
            self.initializeWorker(self.thread_read, self.streamReader) # Initialize the worker thread and fitter
            self.thread_read.start()
            self.readerWorkerReady = True # Flag to indicate worker is ready
            logging.info("Starting reading process")
            # Adjust button display according to ongoing state of process
            self.stream_view_button.setText("Stop")
            self.parent.plot.setTitle("View of the Stream")
            self.parent.timer.setInterval(self.update_interval.value())
            self.stream_view_button.started = True
            logging.info(f"Timer interval: {self.parent.timer.interval()}")
            # Start timer and enable file operation buttons
            self.parent.timer.start()
            self.parent.file_operations.accumulate_button.setEnabled(True)
            self.parent.file_operations.streamWriterButton.setEnabled(True)
        else:
            self.stream_view_button.setText("View Stream")
            self.parent.plot.setTitle("Stream stopped at the current Frame")
            self.stream_view_button.started = False
            self.parent.timer.stop()
            # Properly stop and cleanup worker and thread  
            self.parent.stopWorker(self.thread_read, self.streamReader)
            # Disable buttons
            self.parent.file_operations.accumulate_button.setEnabled(False)
            self.parent.file_operations.streamWriterButton.setEnabled(False)
            # Wait for thread to actually stop
            if self.thread_read is not None:
                logging.info("** Read-thread forced to sleep **")
                time.sleep(0.1) 
            self.autoContrastBtn.setStyleSheet('background-color: red; color: white;')

    def initializeWorker(self, thread, worker):
        worker.moveToThread(thread)
        logging.info(f"{worker.__str__()} is Ready!")
        thread.started.connect(worker.run)
        worker.finished.connect(self.updateUI)
        worker.finished.connect(self.getReaderReady)

    def getReaderReady(self):
        self.readerWorkerReady = True

    def captureImage(self):
        if self.readerWorkerReady:
            self.readerWorkerReady = False
            QMetaObject.invokeMethod(self.streamReader, "run", Qt.QueuedConnection)

    def updateUI(self, image, frame_nr):
        self.parent.imageItem.setImage(image, autoRange = False, autoLevels = False, autoHistogramRange = False)
        self.parent.statusBar().showMessage(f'Frame: {frame_nr}')
