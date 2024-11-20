import time
import logging
import numpy as np
import threading
from boost_histogram import Histogram
from boost_histogram.axis import Regular
from PySide6.QtGui import QFont, QPalette
from PySide6.QtCore import Qt, QThread, QMetaObject, Signal, QTimer
from PySide6.QtWidgets import ( QGroupBox, QVBoxLayout, QHBoxLayout, QLineEdit, 
                                QLabel, QPushButton, QSpinBox, QCheckBox,
                                QGridLayout, QSizePolicy, QSpacerItem, QMessageBox)

from epoc import ConfigurationClient, auth_token, redis_host
from reuss import ReceiverClient
# from ...summing_receiver.ReceiverClient import ReceiverClient

from .reader import Reader

from ... import globals
from ...ui_components.toggle_button import ToggleButton
from ..tem_controls.ui_tem_specific import TEMDetector
from ...ui_components.utils import create_horizontal_line_with_margin

import jungfrau_gui.ui_threading_helpers as thread_manager

from epoc import JungfraujochWrapper, ConfigurationClient, auth_token, redis_host
from ...ui_components.palette import *
from rich import print
from ..tem_controls.toolbox.progress_pop_up import ProgressPopup

class VisualizationPanel(QGroupBox):
    trigger_update_frames_to_sum = Signal(int)
    trigger_disable_receiver_controls = Signal()
    trigger_idle_srecv_btn = Signal()

    def __init__(self, parent):
        # super().__init__("Visualization Panel")
        super().__init__()
        self.parent = parent
        self.trigger_update_frames_to_sum.connect(self.update_frames_to_sum)
        self.trigger_disable_receiver_controls.connect(self.enable_receiver_controls)
        self.trigger_idle_srecv_btn.connect(self.srecv_btn_toggle_OFF)
        self.initUI()

    def initUI(self):

        self.cfg =  ConfigurationClient(redis_host(), token=auth_token())
        self.receiver_client =  None
        self.jfjoch_client = None
        
        font_big = QFont("Arial", 11)
        font_big.setBold(True)
        font_small = QFont("Arial", 10)  # Specify the font name and size

        self.palette = get_palette("dark")
        self.setPalette(self.palette)
        self.background_color = self.palette.color(QPalette.Base).name()
    
        section_visual = QVBoxLayout()
        section_visual.setContentsMargins(10, 10, 10, 10)  # Minimal margins
        section_visual.setSpacing(10) 

        colors_group = QVBoxLayout()
        colors_layout = QHBoxLayout()

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

        if globals.jfj:

            jfjoch_control_group = QVBoxLayout()
            # jfjoch_control_group.addWidget(create_horizontal_line_with_margin(15))

            jfjoch_control_label = QLabel("Jungfraujoch Control Panel")
            jfjoch_control_label.setFont(font_big)
            jfjoch_control_group.addWidget(jfjoch_control_label)

            self.connectTojfjoch = ToggleButton('Connect to Jungfraujoch', self)
            self.connectTojfjoch.setMaximumHeight(50)
            self.connectTojfjoch.clicked.connect(self.connect_and_start_jfjoch_client)

            grid_connection_jfjoch = QGridLayout()
            grid_connection_jfjoch.addWidget(self.connectTojfjoch, 0, 0, 2, 5)

            spacer1 = QSpacerItem(10, 10)  # 20 pixels wide, 40 pixels tall
            grid_connection_jfjoch.addItem(spacer1)

            jfjoch_control_group.addLayout(grid_connection_jfjoch)

            grid_streaming_jfjoch = QGridLayout()

            grid_stream_label = QLabel("Live streaming")
            grid_stream_label.setFont(font_small)

            grid_streaming_jfjoch.addWidget(grid_stream_label)

            self.live_stream_button = ToggleButton('Live Stream', self)
            self.live_stream_button.setDisabled(True)
            self.live_stream_button.clicked.connect(self.toggle_LiveStream)

            grid_streaming_jfjoch.addWidget(self.live_stream_button, 4, 0, 1, 5)   # Stop button spanning all 4 columns at row 3

            jfjoch_control_group.addLayout(grid_streaming_jfjoch)


            grid_collection_jfjoch = QGridLayout()

            grid_collection_label = QLabel("Data Collection")
            grid_collection_label.setFont(font_small)

            grid_collection_jfjoch.addWidget(grid_collection_label)

            self.nbFrames = QSpinBox(self)
            self.nbFrames.setMaximum(1000000000)
            self.nbFrames.setValue(72000)
            self.nbFrames.setDisabled(True)
            self.nbFrames.setSingleStep(1000)
            self.nbFrames.setPrefix("Nb Frames per trigger: ")

            self.last_nbFrames_value = self.nbFrames.value()
            self.nbFrames.valueChanged.connect(lambda value: (
                self.track_nbFrames_value(value),  # Store the latest value
                self.spin_box_modified(self.nbFrames)  # Update the spin box style
            ))
            self.nbFrames.editingFinished.connect(self.update_jfjoch_wrapper)

            self.thresholdBox = QSpinBox(self)
            self.thresholdBox.setMaximum(200)
            self.thresholdBox.setValue(self.cfg.threshold)
            self.thresholdBox.setDisabled(True)
            self.thresholdBox.setSingleStep(10)
            self.thresholdBox.setPrefix("Threshold: ")

            self.thresholdBox.valueChanged.connect(lambda value: self.spin_box_modified(self.thresholdBox))
            self.thresholdBox.editingFinished.connect(self.update_threshold_for_jfjoch)

            self.wait_option = QCheckBox("wait", self)
            self.wait_option.setChecked(False)
            self.wait_option.setDisabled(True)

            grid_collection_jfjoch.addWidget(self.nbFrames, 1, 0, 1, 4)
            grid_collection_jfjoch.addWidget(self.wait_option, 1, 4, 1, 1)
            grid_collection_jfjoch.addWidget(self.thresholdBox, 2, 0, 1, 1)

            self.fname_label = QLabel("Path to recorded file", self)
            self.full_fname = QLineEdit(self)
            self.full_fname.setReadOnly(True)
            self.full_fname.setText(self.cfg.fpath.as_posix())

            hbox_layout = QHBoxLayout()
            hbox_layout.addWidget(self.fname_label)
            hbox_layout.addWidget(self.full_fname)

            grid_collection_jfjoch.addLayout(hbox_layout, 3, 0, 1, 5)

            self.startCollection = QPushButton('Collect', self)
            self.startCollection.setDisabled(True)
            self.startCollection.clicked.connect(lambda: self.send_command_to_jfjoch('collect'))

            self.stopCollection = QPushButton('Cancel', self)
            self.stopCollection.setDisabled(True)
            self.stopCollection.clicked.connect(lambda: self.send_command_to_jfjoch('cancel'))

            grid_collection_jfjoch.addWidget(self.startCollection, 4, 0, 1, 5)
            grid_collection_jfjoch.addWidget(self.stopCollection, 5, 0, 1, 5)

            spacer2 = QSpacerItem(10, 10)  # 20 pixels wide, 40 pixels tall
            grid_collection_jfjoch.addItem(spacer2)

            jfjoch_control_group.addLayout(grid_collection_jfjoch)

            pedestal_layout = QVBoxLayout()
            pedestal_section_label = QLabel("Dark Frame controls")
            pedestal_section_label.setFont(font_small)

            self.recordPedestalBtn = QPushButton('Record Full Pedestal', self)
            self.recordPedestalBtn.setDisabled(True)
            self.recordPedestalBtn.clicked.connect(lambda: self.send_command_to_jfjoch('collect_pedestal'))

            pedestal_layout.addWidget(pedestal_section_label)
            pedestal_layout.addWidget(self.recordPedestalBtn)

            jfjoch_control_group.addLayout(pedestal_layout)

            section_visual.addLayout(jfjoch_control_group)

        else:

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

        section_visual.addWidget(create_horizontal_line_with_margin(15))

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

    """ ***************************************************** """
    """ Methods for the Jungfraujoch receiver (FPGA Solution) """
    """ ***************************************************** """
    def toggle_LiveStream(self):
        if not self.live_stream_button.started:
            result = self.send_command_to_jfjoch("live")
            logging.warning(f"Result of send_command_to_jfjoch('live'): {result}")
        
            # Only proceed if "live" command was successful
            if result is not True:
                logging.warning("Exiting toggle_LiveStream due to failed 'live' command.")
                return  # Exit early if the "live" command failed
            
            self.live_stream_button.setText("Stop")
            self.parent.plot.setTitle("View of the stream from the Jungfraujoch broker")
            self.live_stream_button.started = True
            """ 
            self.parent.file_operations.accumulate_button.setEnabled(True)
            self.parent.file_operations.streamWriterButton.setEnabled(True) 
            """
        else:
            # self.send_command_to_jfjoch("cancel")
            logging.info(f"Stopping the stream...") 
            self.live_stream_button.setText("Live Stream")
            self.parent.plot.setTitle("Stream stopped")
            self.jfjoch_client.cancel()
            self.live_stream_button.started = False
            """ 
            self.parent.file_operations.accumulate_button.setEnabled(False)
            self.parent.file_operations.streamWriterButton.setEnabled(False) 
            """
            if self.autoContrastBtn.started:
                self.toggle_autoContrast()

    # TODO Repetition of method in file_operations
    def reset_style(self, field):
        text_color = self.palette.color(QPalette.Text).name()
        if isinstance(field, QLineEdit):
            field.setStyleSheet(f"QLineEdit {{ color: {text_color}; background-color: {self.background_color}; }}")
        elif isinstance(field,QSpinBox):
            field.setStyleSheet(f"QSpinBox {{ color: {text_color}; background-color: {self.background_color}; }}")

    def update_threshold_for_jfjoch(self):
        if globals.jfj:
            self.cfg.threshold = self.thresholdBox.value()
            self.reset_style(self.thresholdBox)
            logging.info(f"Threshold energy set to: {self.cfg.threshold} keV")

    def update_jfjoch_wrapper(self):
        if self.jfjoch_client is not None:
            if self.jfjoch_client._lots_of_images != self.last_nbFrames_value:
                self.jfjoch_client._lots_of_images = self.nbFrames.value()
                self.reset_style(self.nbFrames)
                logging.info(f'Updated Jungfraujoch client...\nNumber of frames per trigger is equal to: {self.jfjoch_client._lots_of_images}')

    # Helper method to track the latest value for nbFrames
    def track_nbFrames_value(self, value):
        self.last_nbFrames_value = value
        
    # TODO Repetition of method in file_operations
    def spin_box_modified(self, spin_box):
        spin_box.setStyleSheet(f"QSpinBox {{ color: orange; background-color: {self.background_color}; }}")

    def enable_jfjoch_controls(self, enables=False):
        self.startCollection.setEnabled(enables)
        self.stopCollection.setEnabled(enables)
        self.live_stream_button.setEnabled(enables)
        
        self.nbFrames.setEnabled(enables)
        self.wait_option.setEnabled(enables) 

        self.thresholdBox.setEnabled(enables)

        self.recordPedestalBtn.setEnabled(enables)

    def connect_and_start_jfjoch_client(self):
        if self.connectTojfjoch.started == False:
                if self.stream_view_button.started:
                    try:
                        self.jfjoch_client = JungfraujochWrapper(self.cfg.jfjoch_host)
                        self.connectTojfjoch.started = True
                        # TODO create a setter method 'lots_of_images' for in epoc.JungfraujochWrapper ?  
                        logging.info("Created a Jungfraujoch client for communication...")
                        self.connectTojfjoch.setStyleSheet('background-color: green; color: white;')
                        self.connectTojfjoch.setText("Communication OK")
                        self.enable_jfjoch_controls(True)
                        self.jfjoch_client._lots_of_images = self.nbFrames.value()  # 1 hour of stream for a 20 Hz frame rate
                    except TimeoutError as e:
                        logging.error(f"Connection attempt timed out: {e}")
                        self.connectTojfjoch.setStyleSheet('background-color: red; color: white;')
                        self.connectTojfjoch.setText("Connection Timed Out")
                        return
                    except ConnectionError as e:
                        logging.error(f"Connection failed: {e}")
                        self.connectTojfjoch.setStyleSheet('background-color: red; color: white;')
                        self.connectTojfjoch.setText("Connection Failed")
                        return
                    except ValueError as e:
                        logging.error(f"Unexpected server response: {e}")
                        self.connectTojfjoch.setStyleSheet('background-color: red; color: white;')
                        self.connectTojfjoch.setText("Connection Failed")
                        return
                else:
                    logging.warning(
                        f"Cannot create a Jungfraujoch client unless GUI starts "
                         "to receive and correctly decode streamed ZMQ messages from the Jungfraujoch Broker...\n"
                         "Click on the [View Stream] button in the [Visualization Panel] to enable proper decoding of frames."
                    )

                    # Show a popup message box to notify the user of the error
                    error_msg = QMessageBox()
                    error_msg.setIcon(QMessageBox.Warning)
                    error_msg.setWindowTitle("Streamed frames are not being properly decoded")
                    error_msg.setText(
                        "To allow instantiation of Jungfraujoch client, please click on the [View Stream] button in the [Visualization Panel]"
                    )
                    error_msg.setStandardButtons(QMessageBox.Ok)
                    error_msg.exec()
                    
                    return 
        else:
            self.connectTojfjoch.started = False
            self.connectTojfjoch.setStyleSheet('background-color: rgb(53, 53, 53); color: white;')
            self.connectTojfjoch.setText('Connect to Jungfraujoch')

    def send_command_to_jfjoch(self, command):
        try:
            if command == "live":
                try:
                    self.jfjoch_client.live()

                    logging.warning("Live stream started successfully.")
                    
                    return True  # Indicate success
                
                except Exception as e:
                    logging.warning(f"Error occured after Live stream request: {e}")

                    # Show a popup message box to notify the user of the error
                    error_msg = QMessageBox()
                    error_msg.setIcon(QMessageBox.Warning)
                    error_msg.setWindowTitle("Live Stream Error")
                    error_msg.setText("Failed to start live stream due to server error.")
                    error_msg.setInformativeText(f"Details:\n{str(e)}")
                    error_msg.setStandardButtons(QMessageBox.Ok)
                    error_msg.exec()
                    
                    logging.warning("Returning False due to live stream error.")

                    return False  # Indicate failure

            elif command == "collect":
                # Deals with reclicking on [Collect] before ongoing "collect' request ends
                self.startCollection.setDisabled(True)
                try:
                    self.send_command_to_jfjoch("cancel") 
                    
                    self.jfjoch_client.wait_until_idle()
                    
                    logging.warning(f"Starting to collect data...")
                    self.jfjoch_client.start(self.nbFrames.value(), fname = self.cfg.fpath.as_posix(), wait=self.wait_option.isChecked())

                    # Create and start the wait_until_idle thread for asynchronous monitoring
                    self.idle_thread = threading.Thread(target=self.jfjoch_client.wait_until_idle, args=(True,), daemon=True)
                    self.idle_thread.start()
                    
                    # Set up a QTimer to periodically check if the idle_thread has finished
                    self.check_idle_timer = QTimer()
                    self.check_idle_timer.timeout.connect(self.check_if_idle_complete)
                    self.check_idle_timer.start(100)  # Check every 100 ms

                except Exception as e:
                    logging.error(f"Error occured during data collection: {e}")
                    self.startCollection.setEnabled(True)

            elif command == 'collect_pedestal':
                logging.warning("Collecting the pedestal...")
                try:
                    self.send_command_to_jfjoch("cancel")
                    self.jfjoch_client.wait_until_idle()

                    logging.warning(f"Starting to collect the pedestal... This is a blocking operation so please wait until it completes.")
                    
                    # Disable the visualization panel to freeze the GUI
                    self.parent.setEnabled(False)

                    # Create and show the progress popup
                    self.progress_popup = ProgressPopup("Pedestal Collection", "Collecting pedestal...", self)
                    self.progress_popup.show()

                    def update_progress_bar():
                        # Fetch real-time status from the API directly
                        status = self.jfjoch_client.status()
                        logging.debug(f"******** State of api is: {status.state} ***********")
                        
                        if status is None:
                            logging.warning(f"Received {status} from status_get(). Progress cannot be updated.")
                            return

                        try:
                            if status.state == 'Idle':
                                # Operation complete
                                self.progress_popup.update_progress(100)
                                self.progress_popup.close_on_complete()
                                self.progress_timer.stop()
                                logging.warning("Full pedestal collected!")
                                self.resume_live_stream()
                                self.parent.setEnabled(True)
                            else:
                                if status.progress is not None:
                                    progress = int(status.progress * 100)
                                    self.progress_popup.update_progress(progress)
                                else:
                                    logging.warning("Progress is None while state is not Idle.")

                        except AttributeError as e:
                            logging.error(f"Progress attribute missing in status response: {e}")
                        except TypeError as e:
                            logging.error(f"Unexpected type for progress: {e}")

                    self.progress_timer = QTimer(self)
                    self.progress_timer.timeout.connect(update_progress_bar)

                    # Start collecting pedestal (blocks the main thread)
                    self.jfjoch_client.collect_pedestal(wait=False)

                    self.progress_timer.start(100)  # Update every 10ms      

                except Exception as e:
                    logging.error(f"Error occured during pedestal collection: {e}")
                    # Re-enable the main window in case of error
                    self.setEnabled(True)

            elif command == 'cancel':
                # Stop of live stream always reflected on the [Live Stream] button
                if self.live_stream_button.started:
                    self.toggle_LiveStream()
                else:
                    logging.info(f"Cancel request forwarded to JFJ...") 
                    self.jfjoch_client.cancel()  

        except Exception as e:
            logging.error(f"GUI caught relayed error: {e}")

    def check_if_idle_complete(self):
        if not self.idle_thread.is_alive():  # Check if wait_until_idle thread has finished
            self.check_idle_timer.stop()  # Stop the timer since the thread has completed
            
            # Now proceed with the remaining code in "collect"
            logging.info("Measurement ended")

            logging.info(f"Data has been saved in the following file:\n{self.cfg.fpath.as_posix()}")
            s = self.jfjoch_client.api_instance.statistics_data_collection_get()
            print(s)

            # Increment file_id in Redis and update GUI
            self.cfg.after_write()
            self.parent.file_operations.trigger_update_h5_index_box.emit()

            if globals.tem_mode:
                if self.parent.tem_controls.tem_tasks.rotation_button.started:
                    self.parent.tem_controls.tem_tasks.rotation_button.setText("Rotation")
                    self.parent.tem_controls.tem_tasks.rotation_button.started= False

            self.startCollection.setEnabled(True)
            self.resume_live_stream()

    def resume_live_stream(self):
        logging.warning(f"Resuming Live Stream now...")
        if not self.live_stream_button.started:
            # Trigger the stream after collection ends
            QTimer.singleShot(100, self.toggle_LiveStream)  # Delay to ensure sequential execution
        else:
            # If "Live" button is ON, turn it off, then re-start the stream
            self.send_command_to_jfjoch("cancel")  # Stop the stream first

            def restart_stream():
                if not self.live_stream_button.started:
                    self.toggle_LiveStream()  # Start the stream after stopping
            QTimer.singleShot(200, restart_stream)  # Additional delay to ensure cancel completes

    # def update_full_fname(self):
    #     self.full_fname.setText(self.cfg.fpath.as_posix())


    """ ********************************************* """
    """ Methods for the REUSS receiver (CPU Solution) """
    """ ********************************************* """
    def enable_receiver_controls(self, enables=False):
        self.startReceiverStream.setEnabled(enables)
        self.stopSreceiverBtn.setEnabled(enables)
        
        #TODO! Fix changing frames to sum
        # At the moment not safe to change while the receiver is running
        self.setFramesToSumBtn.setEnabled(False)
        self.frames_to_sum.setEnabled(False) 

        self.recordPedestalBtn.setEnabled(enables)
        self.recordGain0Btn.setEnabled(enables)   

    def is_receiver_running(self):
        try:
            # Try creating a ReceiverClient, which pings in its constructor
            self.receiver_client = ReceiverClient(host="localhost", port=5555)
            return True
        except Exception as e:
            logging.warning(f"The summing receiver is not running: {e}")
            return False
        
    def connect_and_start_receiver_client(self):
        if self.connectToSreceiver.started == False:
            self.connectToSreceiver.started = True
            if self.is_receiver_running():  # Use ping instead of process checking
                logging.info("Sreceiver already running!!")
                # self.receiver_client = ReceiverClient(host="localhost", port=5555, verbose=True)
                try:
                    # if self.receiver_client.ping():
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
            # self.trigger_idle_srecv_btn.emit() # To toggle OFF the receiver button after 5 seconds
        else:
            self.connectToSreceiver.started = False
            self.connectToSreceiver.setStyleSheet('background-color: rgb(53, 53, 53); color: white;')
            self.connectToSreceiver.setText('Connect to Receiver')

    def srecv_btn_toggle_OFF(self):
        if self.connectToSreceiver.started:
            # Use QTimer to introduce a 5-second delay -> Non-blocking operation
            QTimer.singleShot(5000, self.connect_and_start_receiver_client)

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

        if self.receiver_client is not None:
            # Start the network operation in a new thread
            threading.Thread(target=thread_command_relay, daemon=True).start()
        else: 
            logging.warning(
                f'Failed attempt to relay the command "{command}" as ReceiverClient instance is None...'
                '\nPlease check that the receiver is up and running before sending further commands!'
            )

    def send_set_frames_command(self):
        value = self.frames_to_sum.value()
        command = f"set_frames_to_sum({value})"
        self.send_command_to_srecv(command)

    def update_frames_to_sum(self, value):
        self.frames_to_sum.setValue(value)

    """ ******************************************** """
    """ Methods for Streaming/Contrasting operations """
    """ ******************************************** """
    def change_theme(self, theme):
        self.parent.histogram.gradient.loadPreset(theme)

    def resetContrast(self):
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
                self.toggle_autoContrast()

    def initializeWorker(self, thread, worker):
        thread_manager.move_worker_to_thread(thread, worker)
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
        if frame_nr is not None:
            self.parent.statusBar().showMessage(f'Frame: {frame_nr}')
