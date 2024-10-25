import math
import logging
import numpy as np
from ... import globals
import pyqtgraph as pg
from datetime import datetime
from PySide6.QtCore import QThread, Qt, QRectF, QMetaObject, Slot, QTimer, Signal
from PySide6.QtGui import QTransform, QFont
from PySide6.QtWidgets import (QGroupBox, QVBoxLayout, QHBoxLayout,
                                QLabel, QDoubleSpinBox, QSpinBox, 
                                QCheckBox, QGraphicsEllipseItem, QLineEdit, QMessageBox,
                                QGraphicsRectItem, QPushButton, QGridLayout, QSpacerItem)

from .toolbox.plot_dialog import PlotDialog
from .gaussian_fitter import GaussianFitter

from ...ui_components.toggle_button import ToggleButton
from .ui_tem_specific import TEMStageCtrl, TEMTasks
from .tem_action import TEMAction

import jungfrau_gui.ui_threading_helpers as thread_manager

from ...ui_components.utils import create_horizontal_line_with_margin
from epoc import JungfraujochWrapper, ConfigurationClient, auth_token, redis_host
from ...ui_components.palette import *
import threading 
from rich import print
from .toolbox.progress_pop_up import ProgressPopup


class TemControls(QGroupBox):
    # trigger_update_full_fname = Signal()

    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.fitter = None
        # self.trigger_update_full_fname.connect(self.update_full_fname)
        self.initUI()

    def initUI(self):

        self.cfg = ConfigurationClient(redis_host(), token=auth_token())
        self.jfjoch_client = None
        
        font_small = QFont("Arial", 10)
        font_small.setBold(True)

        self.palette = get_palette("dark")
        self.setPalette(self.palette)
        self.background_color = self.palette.color(QPalette.Base).name()

        tem_section = QVBoxLayout()
        tem_section.setContentsMargins(10, 10, 10, 10)  # Minimal margins
        tem_section.setSpacing(10) 

        self.ellipse_fit = QGraphicsEllipseItem()
        self.sigma_x_fit = QGraphicsRectItem()
        self.sigma_y_fit = QGraphicsRectItem()

        self.checkbox = QCheckBox("Enable pop-up Window", self)
        self.checkbox.setChecked(False)
        self.plotDialog = None
        
        self.label_gauss_height = QLabel()
        self.label_gauss_height.setText("Gaussian height")
        self.gauss_height_spBx = QDoubleSpinBox()
        self.gauss_height_spBx.setValue(1)
        self.gauss_height_spBx.setMaximum(1e10)
        self.gauss_height_spBx.setReadOnly(True)

        self.label_sigma_x = QLabel()
        self.label_sigma_x.setText("Sigma x (px)")
        self.label_sigma_x.setStyleSheet('color: cyan;')
        self.sigma_x_spBx = QDoubleSpinBox()
        self.sigma_x_spBx.setStyleSheet('color: blue;')
        self.sigma_x_spBx.setValue(1)
        self.sigma_x_spBx.setSingleStep(0.1)
        self.sigma_x_spBx.setReadOnly(True)

        self.label_sigma_y = QLabel()
        self.label_sigma_y.setText("Sigma y (px)")
        self.label_sigma_y.setStyleSheet('color: red;')
        self.sigma_y_spBx = QDoubleSpinBox()
        self.sigma_y_spBx.setStyleSheet('color: red;')
        self.sigma_y_spBx.setValue(1)
        self.sigma_y_spBx.setSingleStep(0.1)
        self.sigma_y_spBx.setReadOnly(True)

        self.label_rot_angle = QLabel()
        self.label_rot_angle.setText("Theta (deg)")
        self.angle_spBx = QDoubleSpinBox()
        self.angle_spBx.setMinimum(-90)
        self.angle_spBx.setMaximum(90)
        self.angle_spBx.setSingleStep(1)
        self.angle_spBx.setReadOnly(True)
        
        font_big = QFont("Arial", 11)
        font_big.setBold(True)

        if globals.tem_mode:
            self.tem_tasks = TEMTasks(self)
            self.tem_stagectrl = TEMStageCtrl()
            tem_section.addWidget(self.tem_tasks)
            self.tem_action = TEMAction(self, self.parent)
            self.tem_action.enabling(False)
            self.tem_action.set_configuration()
            self.tem_action.control.fit_complete.connect(self.updateFitParams)
            self.tem_action.control.remove_ellipse.connect(self.removeAxes)
            tem_section.addWidget(self.tem_stagectrl)
        else: 
            test_fitting_label = QLabel("Test Gaussian Fitting")
            test_fitting_label.setFont(font_big)

            self.btnBeamFocus = ToggleButton("Beam Gaussian Fit", self)
            self.btnBeamFocus.clicked.connect(self.toggle_gaussianFit)

            BeamFocus_layout = QVBoxLayout()
            BeamFocus_layout.addWidget(test_fitting_label)
            BeamFocus_layout.addWidget(self.btnBeamFocus)
            BeamFocus_layout.addWidget(self.checkbox)
            gauss_H_layout = QHBoxLayout()
            gauss_H_layout.addWidget(self.label_gauss_height)  
            gauss_H_layout.addWidget(self.gauss_height_spBx)
            BeamFocus_layout.addLayout(gauss_H_layout)
            sigma_x_layout = QHBoxLayout()
            sigma_x_layout.addWidget(self.label_sigma_x)  
            sigma_x_layout.addWidget(self.sigma_x_spBx)         
            BeamFocus_layout.addLayout(sigma_x_layout)
            sigma_y_layout = QHBoxLayout()
            sigma_y_layout.addWidget(self.label_sigma_y)  
            sigma_y_layout.addWidget(self.sigma_y_spBx)         
            BeamFocus_layout.addLayout(sigma_y_layout)        
            rot_angle_layout = QHBoxLayout()
            rot_angle_layout.addWidget(self.label_rot_angle)  
            rot_angle_layout.addWidget(self.angle_spBx)         
            BeamFocus_layout.addLayout(rot_angle_layout)

            tem_section.addLayout(BeamFocus_layout)
            
        if globals.jfj:

            jfjoch_control_group = QVBoxLayout()
            jfjoch_control_group.addWidget(create_horizontal_line_with_margin(30))

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

            self.nbFrames.valueChanged.connect(lambda value: self.spin_box_modified(self.nbFrames))

            self.nbFrames.editingFinished.connect(self.update_jfjoch_wrapper)

            self.wait_option = QCheckBox("wait", self)
            self.wait_option.setChecked(False)
            self.wait_option.setDisabled(True)

            grid_collection_jfjoch.addWidget(self.nbFrames, 1, 0, 1, 4)
            grid_collection_jfjoch.addWidget(self.wait_option, 1, 4, 1, 1)

            self.fname_label = QLabel("Path to recorded file", self)
            self.full_fname = QLineEdit(self)
            self.full_fname.setReadOnly(True)
            self.full_fname.setText(self.cfg.fpath.as_posix())

            hbox_layout = QHBoxLayout()
            hbox_layout.addWidget(self.fname_label)
            hbox_layout.addWidget(self.full_fname)

            grid_collection_jfjoch.addLayout(hbox_layout, 2, 0, 1, 5)

            self.startCollection = QPushButton('Collect', self)
            self.startCollection.setDisabled(True)
            self.startCollection.clicked.connect(lambda: self.send_command_to_jfjoch('collect'))

            self.stopCollection = QPushButton('Cancel', self)
            self.stopCollection.setDisabled(True)
            self.stopCollection.clicked.connect(lambda: self.send_command_to_jfjoch('cancel'))

            grid_collection_jfjoch.addWidget(self.startCollection, 3, 0, 1, 5)
            grid_collection_jfjoch.addWidget(self.stopCollection, 4, 0, 1, 5)

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

            tem_section.addLayout(jfjoch_control_group)
        
        tem_section.addStretch()
        self.setLayout(tem_section)

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
            if self.parent.visualization_panel.autoContrastBtn.started:
                self.parent.visualization_panel.toggle_autoContrast()

    # TODO Repetition of method in file_operations
    def reset_style(self, field):
        text_color = self.palette.color(QPalette.Text).name()
        if isinstance(field, QLineEdit):
            field.setStyleSheet(f"QLineEdit {{ color: {text_color}; background-color: {self.background_color}; }}")
        elif isinstance(field,QSpinBox):
            field.setStyleSheet(f"QSpinBox {{ color: {text_color}; background-color: {self.background_color}; }}")

    def update_jfjoch_wrapper(self):
        if self.jfjoch_client is not None:
            self.jfjoch_client._lots_of_images = self.nbFrames.value()
            self.reset_style(self.nbFrames)
            logging.info(f'Updated Jungfraujoch client...\nNumber of frames per trigger is equal to: {self.jfjoch_client._lots_of_images}')

    # TODO Repetition of method in file_operations
    def spin_box_modified(self, spin_box):
        spin_box.setStyleSheet(f"QSpinBox {{ color: orange; background-color: {self.background_color}; }}")

    def enable_jfjoch_controls(self, enables=False):
        self.startCollection.setEnabled(enables)
        self.stopCollection.setEnabled(enables)
        self.live_stream_button.setEnabled(enables)
        
        self.nbFrames.setEnabled(enables)
        self.wait_option.setEnabled(enables) 

        self.recordPedestalBtn.setEnabled(enables)

    def connect_and_start_jfjoch_client(self):
        if self.connectTojfjoch.started == False:
                if self.parent.visualization_panel.stream_view_button.started:
                    try:
                        # TODO Avoid hard code: JungfraujochWrapper(self.cfg.jfjoch_frontend_address)
                        self.jfjoch_client = JungfraujochWrapper('http://noether:5232')

                        self.connectTojfjoch.started = True
                        # TODO crate a setter method 'lots_of_images' for in epoc.JungfraujochWrapper ?  
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
        # def thread_command_relay():
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

                    """ ************************************************************************************* """
                    # OPTION 1: Use wait=True
                    # logging.warning(f"Starting to collect the pedestal... This operation blocks the main thread")
                    # self.jfjoch_client.collect_pedestal(wait=True)
                    
                    # OPTION 2: Create a pop up showing progress
                    logging.warning(f"Starting to collect the pedestal... This operation blocks the main thread")

                    # Create and show the progress popup
                    self.progress_popup = ProgressPopup("Pedestal Collection", "Collecting pedestal...", self)
                    self.progress_popup.show()

                    def update_progress_bar():
                        # Fetch real-time status from the API directly
                        status = self.jfjoch_client.status()
                        
                        if status is None:
                            logging.warning(f"Received {status} from status_get(). Progress cannot be updated.")
                            return

                        # Check if the 'progress' attribute exists in the status object
                        try:
                            progress = int(status.progress * 100)
                            self.progress_popup.update_progress(progress)

                            if progress >= 100:
                                self.progress_popup.close_on_complete()
                                self.progress_timer.stop()  # Stop the timer when complete
                        except AttributeError as e:
                            logging.error(f"Progress attribute missing in status response: {e}")
                        except TypeError as e:
                            logging.error(f"Unexpected type for progress: {e}")

                    self.progress_timer = QTimer(self)
                    self.progress_timer.timeout.connect(update_progress_bar)
                    self.progress_timer.start(500)  # Update every 50ms      

                    # Start collecting pedestal (blocks the main thread)
                    self.jfjoch_client.collect_pedestal(wait=False)
                    self.jfjoch_client.wait_until_idle(progress=True)

                    # OPTION 3: Non-blocking operation: Ref. logic in the case above [command == "collect"]
                    """ ************************************************************************************* """
                    logging.warning("Full pedestal collected!")

                except Exception as e:
                    logging.error(f"Error occured during pedestal collection: {e}")

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

            # Increment file_id in Redis and update GUI
            self.cfg.after_write()
            self.parent.file_operations.trigger_update_h5_index_box.emit()

            s = self.jfjoch_client.api_instance.statistics_data_collection_get()
            print(s)
            logging.info(f"Data has been saved in the following file:\n{self.cfg.fpath.as_posix()}")

            self.startCollection.setEnabled(True)

            logging.warning(f"Resuming Live Stream now...")
            # TODO Create a generic method to use for [Live Stream (re)start] after operation ends
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

    """ ***************************************** """
    """ Threading Version of the gaussian fitting """
    """ ***************************************** """
    def toggle_gaussianFit(self):
        if not self.btnBeamFocus.started:
            self.thread_fit = QThread()
            self.fitter = GaussianFitter()
            self.parent.threadWorkerPairs.append((self.thread_fit, self.fitter))                              
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
            self.parent.timer_fit.start(10)
        else:
            self.btnBeamFocus.setText("Beam Gaussian Fit")
            self.btnBeamFocus.started = False
            self.parent.timer_fit.stop()  
            # Close Pop-up Window
            if self.plotDialog != None:
                self.plotDialog.close()
            self.parent.stopWorker(self.thread_fit, self.fitter)
            self.removeAxes()

    def initializeWorker(self, thread, worker):
        thread_manager.move_worker_to_thread(thread, worker)
        worker.finished.connect(self.updateFitParams)
        worker.finished.connect(self.getFitterReady)


    def getFitterReady(self):
        self.fitterWorkerReady = True

    def updateWorkerParams(self, imageItem, roi):
        if self.thread_fit.isRunning():
            # Emit the update signal with the new parameters
            self.fitter.updateParamsSignal.emit(imageItem, roi)  

    #@profile
    def getFitParams(self):
        if self.fitterWorkerReady:
            # Prevent new tasks until the current one is finished
            self.fitterWorkerReady = False
            # Make sure to update the fitter's parameters right before starting the computation
            self.updateWorkerParams(self.parent.imageItem, self.parent.roi)
            # Trigger the "run" computation in the thread where self.fitter" lives
            QMetaObject.invokeMethod(self.fitter, "run", Qt.QueuedConnection)
    
    """ ***************************************** """
    """ **** END OF THREADING VERSION METHODS *** """        
    """ ***************************************** """

    def showPlotDialog(self):
        self.plotDialog = PlotDialog(self)
        self.plotDialog.startPlotting(self.gauss_height_spBx.value(), self.sigma_x_spBx.value(), self.sigma_y_spBx.value())
        self.plotDialog.show() 

    @Slot()
    def updateFitParams(self, fit_result_best_values):
        logging.info(datetime.now().strftime(" START UPDATING GUI @ %H:%M:%S.%f")[:-3])
        amplitude = float(fit_result_best_values['amplitude'])
        xo = float(fit_result_best_values['xo'])
        yo = float(fit_result_best_values['yo'])        
        sigma_x = float(fit_result_best_values['sigma_x'])
        sigma_y = float(fit_result_best_values['sigma_y'])
        theta_deg = float(fit_result_best_values['theta'])
        # Show fitting parameters 
        self.gauss_height_spBx.setValue(amplitude)
        self.sigma_x_spBx.setValue(sigma_x)
        self.sigma_x_spBx.setValue(sigma_x)
        self.sigma_y_spBx.setValue(sigma_y)
        self.angle_spBx.setValue(theta_deg)
        # Update graph in pop-up Window
        if self.plotDialog != None:
            self.plotDialog.updatePlot(amplitude, sigma_x, sigma_y)
        # Draw the fitting line at the FWHM of the 2d-gaussian
        self.drawFittingEllipse(xo,yo,sigma_x, sigma_y, theta_deg)

    def drawFittingEllipse(self, xo, yo, sigma_x, sigma_y, theta_deg):
        # p = 0.5 is equivalent to using the Full Width at Half Maximum (FWHM)
        # where FWHM = 2*sqrt(2*ln(2))*sigma ~ 2.3548*sigma
        p = 0.368 #0.2
        alpha = 2*np.sqrt(-2*math.log(p))
        width = alpha * max(sigma_x, sigma_y) # Use 
        height = alpha * min(sigma_x, sigma_y) # 
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
        """ rotationTransform = QTransform().translate(xo, yo).rotate(theta_deg).translate(-xo, -yo) """
        rotationTransform = QTransform().translate(xo, yo).rotate(-1*theta_deg).translate(-xo, -yo)
        # Create the symmetry (vertical flip) transform
        """ symmetryTransform = QTransform().translate(xo, yo).scale(1, -1).translate(-xo, -yo) """
        # Combine the rotation and symmetry transforms
        """ combinedTransform = rotationTransform * symmetryTransform  """

        self.ellipse_fit.setPen(pg.mkPen('b', width=3))
        """ self.ellipse_fit.setTransform(combinedTransform) """
        self.ellipse_fit.setTransform(rotationTransform)
        self.parent.plot.addItem(self.ellipse_fit)

        self.sigma_x_fit.setPen(pg.mkPen('b', width=2))
        """ self.sigma_x_fit.setTransform(combinedTransform) """
        self.sigma_x_fit.setTransform(rotationTransform)
        self.parent.plot.addItem(self.sigma_x_fit)

        self.sigma_y_fit.setPen(pg.mkPen('r', width=2))
        """ self.sigma_y_fit.setTransform(combinedTransform) """
        self.sigma_y_fit.setTransform(rotationTransform)
        self.parent.plot.addItem(self.sigma_y_fit)

        logging.info(datetime.now().strftime(" END UPDATING GUI @ %H:%M:%S.%f")[:-3])

    def removeAxes(self):
        logging.info("Removing gaussian fitting ellipse and axis!")
        if self.ellipse_fit.scene():
            logging.debug("Removing ellipse_fit from scene")
            self.ellipse_fit.scene().removeItem(self.ellipse_fit)
        if self.sigma_x_fit.scene():
            logging.debug("Removing sigma_x_fit from scene")
            self.sigma_x_fit.scene().removeItem(self.sigma_x_fit)
        if self.sigma_y_fit.scene():
            logging.debug("Removing sigma_y_fit from scene")
            self.sigma_y_fit.scene().removeItem(self.sigma_y_fit)
