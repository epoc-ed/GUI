import time
import logging
import numpy as np
import threading
from PySide6.QtGui import QFont, QPalette
from PySide6.QtCore import Qt, QThread, QMetaObject, Signal, QTimer, QThreadPool, QRunnable
from PySide6.QtWidgets import ( QGroupBox, QVBoxLayout, QHBoxLayout, QLineEdit, 
                                QLabel, QPushButton, QSpinBox, QCheckBox,
                                QGridLayout, QSizePolicy, QSpacerItem, QMessageBox)

from epoc import ConfigurationClient, auth_token, redis_host

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
from jungfrau_gui.ui_components.tem_controls.toolbox import config as cfg_jf

class BrokerCheckTask(QRunnable):
    def __init__(self, check_function, complete_callback):
        super().__init__()
        self.check_function = check_function
        self.complete_callback = complete_callback

    def run(self):
        # Run the provided check function in a separate thread
        self.check_function()
        # Signal that the task is complete
        self.complete_callback()

class VisualizationPanel(QGroupBox):
    assess_gui_jfj_communication_and_display_state = Signal(bool)

    def __init__(self, parent):
        # super().__init__("Visualization Panel")
        super().__init__()
        self.parent = parent
        self.assess_gui_jfj_communication_and_display_state.connect(self.update_gui_with_jfj_state)
        self.initUI()

    def initUI(self):

        self.cfg =  ConfigurationClient(redis_host(), token=auth_token())
        self.receiver_client =  None
        self.jfjoch_client = None

        # Thread pool for running check tasks in separate threads
        self.thread_pool = QThreadPool()
        self.checked_jfj_task_running = False  # Flag to ensure no overlapping tasks
        
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
        
        # Set the initial theme
        self.current_theme = 'viridis'
        self.change_theme(self.current_theme)
        
        #self.change_theme('viridis')
        
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

        view_contrast_group = QVBoxLayout()
        view_contrast_label = QLabel("Streaming")
        view_contrast_label.setFont(font_big)
        view_contrast_group.addWidget(view_contrast_label)

        grid_1 = QGridLayout()
        grid_1.addWidget(self.stream_view_button, 0, 0, 2, 5)  # Span two rows two columns
 
        view_contrast_group.addLayout(grid_1)
        section_visual.addLayout(view_contrast_group)
        # section_visual.addWidget(create_horizontal_line_with_margin())

        time_interval = QLabel("Display Interval (ms):", self)
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

        # if globals.jfj:

        jfjoch_control_group = QVBoxLayout()
        # jfjoch_control_group.addWidget(create_horizontal_line_with_margin(15))

        jfjoch_control_label = QLabel("Jungfraujoch Control Panel")
        jfjoch_control_label.setFont(font_big)
        jfjoch_control_group.addWidget(jfjoch_control_label)

        self.connectTojfjoch = ToggleButton('Connect to Jungfraujoch', self)
        self.connectTojfjoch.setMaximumHeight(50)
        self.connectTojfjoch.clicked.connect(self.connect_and_start_jfjoch_client)
        
        self.check_jfj_timer = QTimer()
        self.check_jfj_timer.timeout.connect(self.run_check_jfj_ready_in_thread)
        self.jfj_broker_is_ready = False

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

        self.thresholdBox = QSpinBox(self)
        self.thresholdBox.setMinimum(0)
        self.thresholdBox.setMaximum(200)
        self.thresholdBox.setValue(self.cfg.threshold)
        self.thresholdBox.setDisabled(True)
        self.thresholdBox.setSingleStep(10)
        self.thresholdBox.setPrefix("Threshold: ")

        self.last_threshold_value = self.thresholdBox.value()
        self.thresholdBox.valueChanged.connect(lambda value: (
            self.track_threshold_value(value),
            self.spin_box_modified(self.thresholdBox)
        ))
        self.thresholdBox.editingFinished.connect(self.update_threshold_for_jfjoch)

        self.wait_option = QCheckBox("wait", self)
        self.wait_option.setChecked(False)
        self.wait_option.setDisabled(True)

        self.wait_option.setToolTip("Check this option to block the GUI when collecting data.")

        # grid_collection_jfjoch.addWidget(self.nbFrames, 1, 0, 1, 3)
        grid_collection_jfjoch.addWidget(self.thresholdBox, 1, 0, 1, 3)
        grid_collection_jfjoch.addWidget(self.wait_option, 1, 3, 1, 1)

        self.fname_label = QLabel("Path to recorded file", self)
        self.full_fname = QLineEdit(self)
        self.full_fname.setReadOnly(True)
        self.full_fname.setText(self.cfg.fpath.as_posix())

        hbox_layout = QHBoxLayout()
        hbox_layout.addWidget(self.fname_label)
        hbox_layout.addWidget(self.full_fname)

        grid_collection_jfjoch.addLayout(hbox_layout, 2, 0, 1, 6)

        self.startCollection = QPushButton('Collect', self)
        self.startCollection.setDisabled(True)
        self.jfj_is_collecting = False
        self.startCollection.clicked.connect(lambda: self.send_command_to_jfjoch('collect'))

        self.stop_jfj_measurement = QPushButton('Cancel', self)
        self.stop_jfj_measurement.setDisabled(True)
        self.stop_jfj_measurement.clicked.connect(lambda: self.send_command_to_jfjoch('cancel'))

        grid_collection_jfjoch.addWidget(self.startCollection, 3, 0, 1, 6)
        grid_collection_jfjoch.addWidget(self.stop_jfj_measurement, 4, 0, 1, 6)

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
            logging.debug(f"Result of send_command_to_jfjoch('live'): {result}")
        
            # Only proceed if "live" command was successful
            if result is not True:
                logging.warning("Exiting toggle_LiveStream due to failed 'live' command.")
                return  # Exit early if the "live" command failed
            
            self.live_stream_button.setText("Stop")
            self.parent.plot.setTitle("View of the stream from the Jungfraujoch broker")
            self.live_stream_button.started = True
        else:
            # self.send_command_to_jfjoch("cancel")
            logging.info(f"Stopping the stream...") 
            self.live_stream_button.setText("Live Stream")
            self.parent.plot.setTitle("Stream stopped")
            self.jfjoch_client.cancel()
            self.live_stream_button.started = False
            if self.parent.autoContrastBtn.started:
                self.parent.toggle_autoContrast()

    # TODO Repetition of method in file_operations
    def reset_style(self, field):
        text_color = self.palette.color(QPalette.Text).name()
        if isinstance(field, QLineEdit):
            field.setStyleSheet(f"QLineEdit {{ color: {text_color}; background-color: {self.background_color}; }}")
        elif isinstance(field,QSpinBox):
            field.setStyleSheet(f"QSpinBox {{ color: {text_color}; background-color: {self.background_color}; }}")

    def update_threshold_for_jfjoch(self):
        if self.cfg.threshold != self.last_threshold_value:            
            self.cfg.threshold = self.thresholdBox.value()
            self.reset_style(self.thresholdBox)
            logging.info(f"Threshold energy set to: {self.cfg.threshold} keV")
            self.resume_live_stream() # Restarting the stream automatically

    # Helper method to track the latest value for threshold
    def track_threshold_value(self, value):
        self.last_threshold_value = value
        
    # TODO Repetition of method in file_operations
    def spin_box_modified(self, spin_box):
        spin_box.setStyleSheet(f"QSpinBox {{ color: orange; background-color: {self.background_color}; }}")

    def enable_jfjoch_controls(self, enables=False):
        if not self.jfj_is_collecting:
            self.startCollection.setEnabled(enables)
        self.stop_jfj_measurement.setEnabled(enables)
        self.live_stream_button.setEnabled(enables)
        self.wait_option.setEnabled(enables) 
        self.thresholdBox.setEnabled(enables)
        self.recordPedestalBtn.setEnabled(enables)

    def on_check_jfj_task_complete(self):
        # Reset the running flag once the task is complete
        self.checked_jfj_task_running = False

    def run_check_jfj_ready_in_thread(self):
        if not self.checked_jfj_task_running:
            # Set the flag to indicate that the task is running
            self.checked_jfj_task_running = True

            # Create a runnable task to run the check function in a separate thread
            check_task = BrokerCheckTask(self.check_jfj_broker_ready, self.on_check_jfj_task_complete)
            self.thread_pool.start(check_task)

    def update_gui_with_jfj_state(self, jfj_broker_is_ready):
        self.jfj_broker_is_ready = jfj_broker_is_ready
        if jfj_broker_is_ready:
            self.update_gui_with_JFJ_ON()
        else:
            self.update_gui_with_JFJ_OFF()

    def update_gui_with_JFJ_ON(self):
        self.connectTojfjoch.setStyleSheet('background-color: green; color: white;')
        self.connectTojfjoch.setText("Communication OK")
        self.enable_jfjoch_controls(True)
        if self.jfjoch_client.status().state == "Idle": # So that the [Live Stream] button reflects the actual operating state
            if self.live_stream_button.started: # When the stream ends, the button has to reflect that
                    self.toggle_LiveStream() # toggle OFF

    def update_gui_with_JFJ_OFF(self):
        self.connectTojfjoch.setStyleSheet('background-color: red; color: white;')
        self.connectTojfjoch.setText("Connection Failed")
        self.enable_jfjoch_controls(False)
        logging.warning("The JFJ broker current state is in {Inactive, Error}... State needs to be 'Idle' for communication ot work")

    def check_jfj_broker_ready(self):
        logging.debug("Checking broker...")
        try:
            self.assess_gui_jfj_communication_and_display_state.emit(self.jfjoch_client.status().state not in {"Inactive", "Error"}) 

        except Exception as e:
            logging.error(f"Error occured when checking the operating state of the wrapper [jfjoch_client.status().state]: {e}")
            self.assess_gui_jfj_communication_and_display_state.emit(False)

        logging.debug("Check finished")

    def connect_and_start_jfjoch_client(self):
        if self.connectTojfjoch.started == False:
                if self.stream_view_button.started:
                    try:
                        self.connectTojfjoch.started = True

                        # Create an instance of the API wrapper
                        self.jfjoch_client = JungfraujochWrapper(self.cfg.jfjoch_host)
                        logging.info("Created a Jungfraujoch client for communication...")

                        # Trigger immediately for the first time
                        self.run_check_jfj_ready_in_thread()

                        # Then check the JFJ state of operation every 5 seconds
                        self.check_jfj_timer.start(5000)

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
            self.check_jfj_timer.stop()
            self.thread_pool.waitForDone()  # Wait for all tasks to finish
            self.connectTojfjoch.started = False
            self.connectTojfjoch.setStyleSheet('background-color: rgb(53, 53, 53); color: white;')
            self.connectTojfjoch.setText('Connect to Jungfraujoch')
            self.send_command_to_jfjoch("cancel") # For now, the easiest way to keep up with the JFJ state
            
            """ 
            The following forces the user to have the GUI continuously check the JFJ operating state.
            If the button [Connect to Jungfraujoch] is OFFed, controls are disabled as a percaution,
            since the JFJ state is unknown to GUI at that point.
            """ 
            self.jfjoch_client = None # Reset the wrapper to None
            self.enable_jfjoch_controls(False) # Need to disable controls as the wrapper is None

            # Reset the flag if a task is still running
            self.checked_jfj_task_running = False

    def send_command_to_jfjoch(self, command):
        try:
            if command == "live":
                try:
                    # Cancel current task
                    self.send_command_to_jfjoch("cancel") 
                    self.jfjoch_client.wait_until_idle()

                    logging.info(f"Nb of frames per trigger: {self.jfjoch_client._lots_of_images}") # 72000
                    logging.info(f"Threshold (in keV) set to: {self.thresholdBox.value()}")
                    self.jfjoch_client.start(n_images = self.jfjoch_client._lots_of_images,
                                            fname = "",
                                            th = self.thresholdBox.value(),
                                            beam_x_pxl = self.cfg.beam_center[0],
                                            beam_y_pxl = self.cfg.beam_center[1],
                                            # detector_distance_mm = cfg_jf.lookup(cfg_jf.lut.distance, self.cfg.mag_value_diff[2], 'displayed', 'calibrated'), #100
                                            detector_distance_mm = cfg_jf.lookup(cfg_jf.lut.distance, globals.mag_value_diff[2], 'displayed', 'calibrated'), #100
                                            incident_energy_ke_v = self.parent.tem_controls.voltage_spBx.value(), # 200,
                                            wait = self.wait_option.isChecked())
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
                    self.formatted_filename = self.cfg.fpath
                    
                    self.jfjoch_client.start(n_images = self.jfjoch_client._lots_of_images,
                                            fname = self.formatted_filename.as_posix(),
                                            th = self.thresholdBox.value(),
                                            beam_x_pxl = self.cfg.beam_center[0],
                                            beam_y_pxl = self.cfg.beam_center[1],
                                            # detector_distance_mm = cfg_jf.lookup(cfg_jf.lut.distance, self.cfg.mag_value_diff[2], 'displayed', 'calibrated'), #100
                                            detector_distance_mm = cfg_jf.lookup(cfg_jf.lut.distance, globals.mag_value_diff[2], 'displayed', 'calibrated'), #100
                                            incident_energy_ke_v = self.parent.tem_controls.voltage_spBx.value(), # 200,
                                            wait = self.wait_option.isChecked())
                    self.jfj_is_collecting = True
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
                    self.toggle_LiveStream() # toggle OFF
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
            self.jfj_is_collecting = False
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

    """ ******************************************** """
    """ Methods for Streaming/Contrasting operations """
    """ ******************************************** """
    def change_theme(self, theme):
        self.current_theme = theme
        self.parent.histogram.gradient.loadPreset(theme)
        self.applyCustomColormap()

    def applyCustomColormap(self):
        # Get the LUT from the gradient
        # Could be of shape 512 x 3 or 512 x 4
        lut = self.parent.histogram.gradient.getLookupTable(512)

        # Ensure the LUT has an alpha channel i.e. 512 x 4
        if lut.shape[1] == 4:
            pass
        else:
            alpha = np.ones((lut.shape[0], 1), dtype=lut.dtype) * 255
            lut = np.hstack((lut, alpha))

        # Only do this if you truly want the LUT index 0 to be invisible.
        # Meaning that all low value pixels that map to the first row (index 0)
        # of the LUT, will be represented as [R0, G0, B0, A0] with A0 = 0;
        # where 0=TRANSPARENT VS 255=OPAQUE 
        # If it kills valid data, comment it out.
               
        # lut[0, 3] = 0 

        # Apply the modified LUT to the ImageItem
        self.parent.imageItem.setLookupTable(lut)

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
        else:
            self.stream_view_button.setText("View Stream")
            self.parent.plot.setTitle("Stream stopped at the current Frame")
            self.stream_view_button.started = False
            self.parent.timer.stop()
            # Properly stop and cleanup worker and thread  
            self.parent.stopWorker(self.thread_read, self.streamReader)
            # Wait for thread to actually stop
            if self.thread_read is not None:
                logging.info("** Read-thread forced to sleep **")
                time.sleep(0.1) 
            if self.parent.autoContrastBtn.started:
                self.parent.toggle_autoContrast()

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