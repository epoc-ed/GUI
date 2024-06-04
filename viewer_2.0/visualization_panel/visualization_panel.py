import time
import logging
import numpy as np
from boost_histogram import Histogram
from boost_histogram.axis import Regular
from PySide6.QtCore import Qt, QThread, QMetaObject
from PySide6.QtWidgets import (QGroupBox, QVBoxLayout, QHBoxLayout,
                                QLabel, QPushButton, QFrame, QSpinBox,
                                QGridLayout)

from .reader import Reader

from reuss import config as cfg
from toggle_button import ToggleButton


class VisualizationPanel(QGroupBox):
    def __init__(self, parent):
        super().__init__("Visualization Panel")
        self.parent = parent
        self.initUI()

    def initUI(self):
        section1 = QVBoxLayout()

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
            button.clicked.connect(lambda checked=False, b=name: self.change_theme(b))
        colors_group.addLayout(colors_layout)
        self.change_theme('viridis')
        section1.addLayout(colors_group)

        h_line_1 = QFrame()
        h_line_1.setFrameShape(QFrame.HLine)
        h_line_1.setFrameShadow(QFrame.Plain)
        h_line_1.setStyleSheet("""QFrame {border: none; border-top: 1px solid grey;}""")
        section1.addWidget(h_line_1)

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
        
        view_contrast_group = QVBoxLayout()
        view_contrast_label = QLabel("Streaming & Contrast")
        view_contrast_group.addWidget(view_contrast_label)

        grid_1 = QGridLayout()
        grid_1.addWidget(self.stream_view_button, 0, 0, 2, 2)  # Span two rows two columns
        grid_1.addWidget(self.autoContrastBtn, 0, 2)
        grid_1.addWidget(self.contrast_status, 1, 2)

        view_contrast_group.addLayout(grid_1)
        section1.addLayout(view_contrast_group)

        time_interval = QLabel("Acquisition Interval (ms):", self)
        self.update_interval = QSpinBox(self)
        self.update_interval.setMaximum(5000)
        self.update_interval.setSuffix(' ms')
        self.update_interval.setValue(cfg.viewer.interval)
        time_interval_layout = QHBoxLayout()
        time_interval_layout.addWidget(time_interval)
        time_interval_layout.addWidget(self.update_interval)
        section1.addLayout(time_interval_layout)
        self.setLayout(section1)

    def change_theme(self, theme):
        self.parent.histogram.gradient.loadPreset(theme)

    # @profile
    def applyAutoContrast(self, histo_boost = False):
        self.autoContrastON = True
        self.autoContrastBtn.setStyleSheet('background-color: green; color: white;')
        self.contrast_status.setText("Auto Contrast is ON")
        self.contrast_status.setStyleSheet('color: green;')
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
            self.autoContrastON = False
            self.autoContrastBtn.setStyleSheet('background-color: red; color: white;')
            self.contrast_status.setText("Auto Contrast is OFF")
            self.contrast_status.setStyleSheet('color: red;')

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
        if self.autoContrastON:
                self.applyAutoContrast()
        self.parent.statusBar().showMessage(f'Frame: {frame_nr}')
