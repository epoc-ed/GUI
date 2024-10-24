import math
import logging
import numpy as np
from ... import globals
import pyqtgraph as pg
from datetime import datetime
from PySide6.QtCore import QThread, Qt, QRectF, QMetaObject, Slot
from PySide6.QtGui import QTransform, QFont
from PySide6.QtWidgets import (QGroupBox, QVBoxLayout, QHBoxLayout,
                                QLabel, QDoubleSpinBox, QSpinBox, 
                                QCheckBox, QGraphicsEllipseItem, QLineEdit,
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


class TemControls(QGroupBox):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.fitter = None
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

            self.nbFrames.editingFinished.connect(self.update_jfjoch_wrapper)

            self.nbFrames.valueChanged.connect(lambda value: self.spin_box_modified(self.nbFrames))

            # self.wait_option = QCheckBox("wait", self)
            # self.wait_option.setChecked(False)
            # self.wait_option.setDisabled(True)

            grid_collection_jfjoch.addWidget(self.nbFrames, 1, 0, 1, 5)
            # grid_collection_jfjoch.addWidget(self.wait_option, 1, 4, 1, 1)

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
            self.send_command_to_jfjoch("live")
            self.live_stream_button.setText("Stop")
            self.parent.plot.setTitle("View of the stream from the Jungfraujoch broker")
            self.live_stream_button.started = True
            """ 
            self.parent.file_operations.accumulate_button.setEnabled(True)
            self.parent.file_operations.streamWriterButton.setEnabled(True) 
            """
        else:
            self.send_command_to_jfjoch("cancel")
            self.live_stream_button.setText("Live Stream")
            self.parent.plot.setTitle("Stream stopped")
            self.live_stream_button.started = False
            # Properly stop and cleanup worker and thread  
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
        # self.wait_option.setEnabled(enables) 

        self.recordPedestalBtn.setEnabled(enables)

    def connect_and_start_jfjoch_client(self):
        if self.connectTojfjoch.started == False:
            self.connectTojfjoch.started = True
            try:
                # TODO Avoid hard code: JungfraujochWrapper(self.cfg.jfjoch_frontend_address)
                self.jfjoch_client = JungfraujochWrapper('http://noether:5232')
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
            except ConnectionError as e:
                logging.error(f"Connection failed: {e}")
                self.connectTojfjoch.setStyleSheet('background-color: red; color: white;')
                self.connectTojfjoch.setText("Connection Failed")
            except ValueError as e:
                logging.error(f"Unexpected server response: {e}")
                self.connectTojfjoch.setStyleSheet('background-color: red; color: white;')
                self.connectTojfjoch.setText("Connection Failed")
        else:
            self.connectTojfjoch.started = False
            self.connectTojfjoch.setStyleSheet('background-color: rgb(53, 53, 53); color: white;')
            self.connectTojfjoch.setText('Connect to Jungfraujoch')

    def send_command_to_jfjoch(self, command):
        # def thread_command_relay():
        try:
            if command == "live":
                logging.warning("Starting the live streaming of frames...")
                try:
                    self.jfjoch_client.live()
                except Exception as e:
                    logging.warning(f"Error occured after Live stream request: {e}")

            elif command == "collect":
                logging.warning(f"Starting data collection...\nThe file is saved at: {self.cfg.fpath.as_posix()}")
                try:
                    print("Hit enter to start measuring")
                    input()
                    self.jfjoch_client.cancel()
                    self.jfjoch_client.wait_until_idle()
                    print(f"Starting to record: {self.cfg.fpath.as_posix()}")
                    self.jfjoch_client.start(self.nbFrames.value(), fname = self.cfg.fpath.as_posix())
                    print("Hit enter to stop measuring")
                    input()
                    self.jfjoch_client.cancel()
                    self.jfjoch_client.wait_until_idle()
                    print("Measurement stopped")
                    s = self.jfjoch_client.api_instance.statistics_data_collection_get()
                    print(s)
                    self.jfjoch_client.live()
                    # self.jfjoch_client.collect(self.cfg.fpath.as_posix())
                    logging.info(f"Data has been saved in the following file:\n{self.cfg.fpath.as_posix()}")
                except Exception as e:
                    logging.error(f"Error occured during data collection: {e}")

            elif command == 'collect_pedestal':
                logging.warning("Collecting the pedestal...")
                try:
                    self.jfjoch_client.cancel()
                    self.jfjoch_client.wait_until_idle()
                    self.jfjoch_client.collect_pedestal(wait=True)
                    self.jfjoch_client.live()
                    logging.info("Full pedestal collected!")
                except Exception as e:
                    logging.error(f"Error occured during pedestal collection: {e}")

            elif command == 'cancel':
                logging.info(f"Stopping the stream...") 
                self.jfjoch_client.cancel()  
        except Exception as e:
            logging.error(f"GUI caught relayed error: {e}")

        # Start the network operation in a new thread
        # threading.Thread(target=thread_command_relay, daemon=True).start()

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
