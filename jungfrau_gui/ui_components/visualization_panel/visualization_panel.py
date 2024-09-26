import time
import logging
import numpy as np
import threading
from boost_histogram import Histogram
from boost_histogram.axis import Regular
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt, QThread, QMetaObject, Signal
from PySide6.QtWidgets import ( QGroupBox, QVBoxLayout, QHBoxLayout,
                                QLabel, QPushButton, QSpinBox,
                                QGridLayout, QSizePolicy, QSpacerItem)

from epoc import ConfigurationClient, auth_token, redis_host
# from reuss import ReceiverClient
from ...summing_receiver.ReceiverClient import ReceiverClient

from .reader import Reader

from ... import globals
from ...ui_components.toggle_button import ToggleButton
from ..tem_controls.ui_tem_specific import TEMDetector
from ...ui_components.utils import create_horizontal_line_with_margin

import psutil

def is_process_running(process_name):
    for proc in psutil.process_iter(['cmdline']):  # Fetch command line arguments for each process
        try:
            # Check each command line argument to find for e.g. 'ReceiverServer' when running 'python ReceiverServer.py -t 12'
            if any(process_name in arg for arg in proc.info['cmdline']):
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            # TODO Handle exceptions if the process terminates or if access is denied
            continue
    return False

class VisualizationPanel(QGroupBox):
    trigger_update_frames_to_sum = Signal(int)
    trigger_disable_receiver_controls = Signal()

    def __init__(self, parent):
        # super().__init__("Visualization Panel")
        super().__init__()
        self.parent = parent
        self.cfg =  ConfigurationClient(redis_host(), token=auth_token())
        # self.receiver_client = ReceiverClient(host="localhost", port = 5555, verbose=True)
        self.trigger_update_frames_to_sum.connect(self.update_frames_to_sum)
        self.trigger_disable_receiver_controls.connect(self.enable_receiver_controls)
        self.initUI()

    def initUI(self):
        section_visual = QVBoxLayout()
        section_visual.setContentsMargins(10, 10, 10, 10)  # Minimal margins
        section_visual.setSpacing(10) 

        colors_group = QVBoxLayout()
        colors_layout = QHBoxLayout()

        font_big = QFont("Arial", 11)
        font_big.setBold(True)

        theme_label = QLabel("Color map", self)
        theme_label.setFont(font_big)

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
        self.autoContrastBtn = ToggleButton('Apply Auto Contrast', self)
        self.autoContrastBtn.setStyleSheet('background-color: green; color: white;')
        self.autoContrastBtn.clicked.connect(self.toggle_autoContrast)
        self.resetContrastBtn = QPushButton("Reset Contrast")
        self.resetContrastBtn.clicked.connect(self.resetContrast)
        
        view_contrast_group = QVBoxLayout()
        view_contrast_label = QLabel("Streaming & Contrast")
        view_contrast_label.setFont(font_big)
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
        self.update_interval.setValue(self.cfg.viewer_interval)
        self.update_interval.valueChanged.connect(lambda x: self.parent.timer.setInterval(x))
        time_interval_layout = QHBoxLayout()
        time_interval_layout.addWidget(time_interval)
        time_interval_layout.addWidget(self.update_interval)
        section_visual.addLayout(time_interval_layout)
        section_visual.addWidget(create_horizontal_line_with_margin(15))

        receiver_control_group = QVBoxLayout()
        receiver_control_label = QLabel("Summming Receiver Controls")
        receiver_control_label.setFont(font_big)
        receiver_control_group.addWidget(receiver_control_label)

        self.connectToSreceiver = ToggleButton('Connect to Receiver', self)
        self.connectToSreceiver.setMaximumHeight(50)
        self.connectToSreceiver.clicked.connect(self.connect_and_start_receiver_client)

        self.startReceiverStream = QPushButton('Start Stream', self)
        self.startReceiverStream.setDisabled(True)
        self.startReceiverStream.clicked.connect(lambda: self.send_command_to_srecv('start'))
        
        self.stopSreceiverBtn = QPushButton('Stop Receiver', self)
        self.stopSreceiverBtn.setDisabled(True)
        self.stopSreceiverBtn.clicked.connect(lambda: self.send_command_to_srecv('stop'))

        grid_comm_receiver = QGridLayout()
        grid_comm_receiver.addWidget(self.connectToSreceiver, 0, 0, 2, 2)
        grid_comm_receiver.addWidget(self.startReceiverStream, 0, 2, 2, 2)
        grid_comm_receiver.addWidget(self.stopSreceiverBtn, 0, 4, 2, 2)

        spacer = QSpacerItem(20, 20)  # 20 pixels wide, 40 pixels tall
        grid_comm_receiver.addItem(spacer)

        receiver_control_group.addLayout(grid_comm_receiver)

        Frames_Sum_layout=QVBoxLayout() 
        Frames_Sum_section_label = QLabel("Summming Parameters")
        font_small = QFont("Arial", 10)  # Specify the font name and size
        Frames_Sum_section_label.setFont(font_small)

        Frame_number_layout = QHBoxLayout()

        self.frames_to_sum_lb = QLabel("Summing Factor:", self)
        self.frames_to_sum = QSpinBox(self)
        self.frames_to_sum.setMaximum(200)
        self.frames_to_sum.setDisabled(True)
        self.frames_to_sum.setSingleStep(10)

        Frame_number_layout.addWidget(self.frames_to_sum_lb)
        Frame_number_layout.addWidget(self.frames_to_sum)

        Frame_buttons_layout = QHBoxLayout()
        # self.getFramesToSumBtn = QPushButton('Get Frames Number', self)
        # self.getFramesToSumBtn.clicked.connect(lambda: self.send_command_to_srecv("get_frames_to_sum"))

        self.setFramesToSumBtn = QPushButton('Set Frames Number', self)
        self.setFramesToSumBtn.setDisabled(True) 
        self.setFramesToSumBtn.clicked.connect(self.send_set_frames_command)

        # Frame_buttons_layout.addWidget(self.getFramesToSumBtn)
        Frame_buttons_layout.addWidget(self.setFramesToSumBtn)

        Frames_Sum_layout.addWidget(Frames_Sum_section_label)
        Frames_Sum_layout.addLayout(Frame_number_layout)
        Frames_Sum_layout.addLayout(Frame_buttons_layout)

        spacer2 = QSpacerItem(20, 20)  # 20 pixels wide, 40 pixels tall
        Frames_Sum_layout.addItem(spacer2)
        
        receiver_control_group.addLayout(Frames_Sum_layout) 
       
        pedestal_layout = QVBoxLayout()
        pedestal_section_label = QLabel("Dark Frame controls")
        pedestal_section_label.setFont(font_small)

        self.recordPedestalBtn = QPushButton('Record Full Pedestal', self)
        self.recordPedestalBtn.setDisabled(True)
        self.recordPedestalBtn.clicked.connect(lambda: self.send_command_to_srecv('collect_pedestal'))
        
        self.recordGain0Btn = QPushButton('Record Gain G0', self)
        self.recordGain0Btn.setDisabled(True)
        self.recordGain0Btn.clicked.connect(lambda: self.send_command_to_srecv('tune_pedestal'))

        pedestal_layout.addWidget(pedestal_section_label)
        pedestal_layout.addWidget(self.recordPedestalBtn)
        pedestal_layout.addWidget(self.recordGain0Btn)

        receiver_control_group.addLayout(pedestal_layout)

        section_visual.addLayout(receiver_control_group)

        if globals.tem_mode:
            tem_detector_layout = QVBoxLayout()
            tem_detector_label = QLabel("Detector")
            tem_detector_label.setFont(font_big)

            self.tem_detector = TEMDetector()
            tem_detector_layout.addWidget(tem_detector_label)
            tem_detector_layout.addWidget(self.tem_detector)

            section_visual.addLayout(tem_detector_layout)
        else: 
            pass
        
        section_visual.addStretch()
        self.setLayout(section_visual)

    # TODO: rewrite in a better way
    def enable_receiver_controls(self, enables=False):
        if enables==True:
            self.startReceiverStream.setEnabled(enables)
            self.stopSreceiverBtn.setEnabled(enables)
            self.setFramesToSumBtn.setEnabled(enables)
            self.frames_to_sum.setEnabled(enables)
            self.recordPedestalBtn.setEnabled(enables)
            self.recordGain0Btn.setEnabled(enables)
        else:
            self.startReceiverStream.setDisabled(True)
            self.stopSreceiverBtn.setDisabled(True)
            self.setFramesToSumBtn.setDisabled(True)
            self.frames_to_sum.setDisabled(True)
            self.recordPedestalBtn.setDisabled(True)
            self.recordGain0Btn.setDisabled(True)     

    def is_summingReceiver_running(self, process_name):
        if not is_process_running(process_name):
            logging.warning("Summing Receiver (Server) is not running...\nSumming Receiver controls are only available if the receiver's server is already running!")
            return False
        else:
            return True

    def connect_and_start_receiver_client(self):
        if self.connectToSreceiver.started == False:
            self.connectToSreceiver.started = True
            if self.is_summingReceiver_running('ReceiverServer'):
                logging.info("Sreceiver already running!!")
                self.receiver_client = ReceiverClient(host="localhost", port = 5555, verbose=True)
                try:
                    if self.receiver_client.ping():
                        self.connectToSreceiver.setStyleSheet('background-color: green; color: white;')
                        self.connectToSreceiver.setText("Communication OK")
                        self.enable_receiver_controls(True)
                        time.sleep(0.01)
                        self.send_command_to_srecv("get_frames_to_sum")
                except TimeoutError as e:
                    logging.error(f"Connection attempt timed out: {e}")
                    self.connectToSreceiver.setStyleSheet('background-color: red; color: white;')
                    self.connectToSreceiver.setText("Connection Timed Out")
                except ConnectionError as e:
                    logging.error(f"Connection failed: {e}")
                    self.connectToSreceiver.setStyleSheet('background-color: red; color: white;')
                    self.connectToSreceiver.setText("Connection Failed")
                except ValueError as e:
                    logging.error(f"Unexpected server response: {e}")
                    self.connectToSreceiver.setStyleSheet('background-color: red; color: white;')
                    self.connectToSreceiver.setText("Connection Failed")
            else:
                logging.warning("ReceiverServer not running")
                self.connectToSreceiver.setStyleSheet('background-color: red; color: white;')
                self.connectToSreceiver.setText("Receiver Not Running")
        else:
            self.connectToSreceiver.started = False
            self.connectToSreceiver.setStyleSheet('background-color: rgb(53, 53, 53); color: white;')
            self.connectToSreceiver.setText('Connect to Receiver')

    def send_command_to_srecv(self, command):
        def thread_command_relay():
            try:
                if command == 'start':
                    self.receiver_client.start()
                    logging.info("Communication with the Receiver Server is established.\nPlease proceed with desired operation through availbale buttons... ")
                elif command == 'collect_pedestal':
                    self.receiver_client.collect_pedestal()
                    logging.info("Full pedestal collected!")
                elif command == 'tune_pedestal':
                    self.receiver_client.tune_pedestal()
                    logging.info("Pedestal tuned i.e. collected pedestal for gain G0")
                elif command == 'get_frames_to_sum':
                    summing_factor = self.receiver_client.frames_to_sum
                    self.trigger_update_frames_to_sum.emit(int(summing_factor))
                    logging.info(f"Recorded the default summing factor {summing_factor}")
                elif command[:10] == 'set_frames':
                    new_summing_factor = int(command.split('(')[1].split(')')[0])
                    self.receiver_client.frames_to_sum = new_summing_factor
                    logging.info(f"Summing factor in receiver set to {new_summing_factor}")
                elif command == 'stop':
                    self.trigger_disable_receiver_controls.emit()      
                    logging.info(f"Stopping Receiver...") 
                    self.receiver_client.stop()
            except Exception as e:
                logging.error(f"GUI caught relayed error: {e}")

        # Start the network operation in a new thread
        threading.Thread(target=thread_command_relay, daemon=True).start()

    def send_set_frames_command(self):
        value = self.frames_to_sum.value()
        command = f"set_frames_to_sum({value})"
        self.send_command_to_srecv(command)

    def update_frames_to_sum(self, value):
        self.frames_to_sum.setValue(value)

    def change_theme(self, theme):
        self.parent.histogram.gradient.loadPreset(theme)

    def resetContrast(self):
        # self.parent.histogram.setLevels(0, 255)
        self.parent.timer_contrast.stop()
        self.autoContrastBtn.started = False
        self.autoContrastBtn.setStyleSheet('background-color: green; color: white;')
        self.autoContrastBtn.setText('Apply Auto Contrast')
        self.parent.histogram.setLevels(self.cfg.viewer_cmin, self.cfg.viewer_cmax)

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
            if self.autoContrastBtn.started:
                # self.autoContrastBtn.setStyleSheet('background-color: red; color: white;')
                self.toggle_autoContrast()

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
        # self.parent.histogram.setLevels(0, 5000)  # Reinforce level settings
        # self.parent.histogram.setHistogramRange(0, 5000, padding=0) 
        self.parent.statusBar().showMessage(f'Frame: {frame_nr}')
