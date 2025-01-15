import logging
from PySide6.QtGui import QIcon, QFont, QRegularExpressionValidator
from PySide6.QtCore import Signal, Qt, QRegularExpression
from PySide6.QtWidgets import (QGroupBox, QVBoxLayout, QHBoxLayout,
                                QLabel, QLineEdit, QSpinBox, QButtonGroup,
                                QPushButton, QFileDialog, QCheckBox,
                                QMessageBox, QGridLayout, QRadioButton)

from .stream_writer import StreamWriter
from .frame_accumulator_mp import FrameAccumulator


from ... import globals
from ...ui_components.toggle_button import ToggleButton
from ...ui_components.utils import create_horizontal_line_with_margin
from ...ui_components.palette import *
from ...ui_components.tem_controls.toolbox.tool import send_with_retries
from ...metadata_uploader.metadata_update_client import MetadataNotifier

from epoc import ConfigurationClient, auth_token, redis_host

from pathlib import Path
import os
import re
import time

class FileOperations(QGroupBox):
    trigger_update_h5_index_box = Signal()
    start_H5_recording = Signal()
    stop_H5_recording = Signal()
    
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.cfg = ConfigurationClient(redis_host(), token=auth_token())
        self.trigger_update_h5_index_box.connect(self.update_index_box)
        self.initUI()
        self.metadata_notifier = MetadataNotifier(host = "noether")
        

    def initUI(self):

        self.palette = get_palette("dark")
        self.setPalette(self.palette)

        section3 = QVBoxLayout()
        font_big = QFont("Arial", 11)
        font_big.setBold(True)

        Redis_section_label = QLabel("Redis Store Settings", self)
        Redis_section_label.setFont(font_big)

        section3.addWidget(Redis_section_label)
        self.redis_fields = []

        ########################
        # Experiment Class Field
        ########################
        self.experiment_class = QLabel("Experiment Class", self)
        self.rb_univie = QRadioButton("UniVie", self)
        self.rb_external = QRadioButton("External", self)
        self.rb_ip = QRadioButton("IP", self)

        self.rb_experiment_class = QButtonGroup()
        self.rb_experiment_class.addButton(self.rb_univie, 0)
        self.rb_experiment_class.addButton(self.rb_external, 1)
        self.rb_experiment_class.addButton(self.rb_ip, 2)
        for rb in self.rb_experiment_class.buttons():
            if rb.text() == self.cfg.experiment_class:
                rb.setChecked(True)
                break

        self.rb_experiment_class.buttonClicked.connect(self.update_experiment_class)

        self.get_experiment_class = QPushButton("Get", self)
        self.get_experiment_class.clicked.connect(lambda: print(f"Experiment Class: {self.cfg.experiment_class}"))

        redis_experiment_class_layout = QHBoxLayout()
        redis_experiment_class_layout.addWidget(self.experiment_class)
        for rb in self.rb_experiment_class.buttons():
            redis_experiment_class_layout.addWidget(rb, 1)
        redis_experiment_class_layout.addWidget(self.get_experiment_class)

        section3.addLayout(redis_experiment_class_layout)
        
        #################
        # User Name Field
        #################
        self.userName = QLabel("PI name", self)
        self.userName_input = QLineEdit(self)
        self.redis_fields.append(self.userName_input)
        self.userName_input.setText(f'{self.cfg.PI_name}')

        self.get_userName = QPushButton("Get", self)
        self.get_userName.clicked.connect(lambda: print(f"PI Name: {self.cfg.PI_name}"))

        self.userName_input.returnPressed.connect(self.update_userName)

        redis_UserName_layout = QHBoxLayout()
        redis_UserName_layout.addWidget(self.userName)
        redis_UserName_layout.addWidget(self.userName_input)
        redis_UserName_layout.addWidget(self.get_userName)

        section3.addLayout(redis_UserName_layout)

        ##################
        # Project ID Field
        ##################
        self.projectID = QLabel("Project ID", self)
        self.projectID_input = QLineEdit(self)
        self.redis_fields.append(self.projectID_input)
        self.projectID_input.setText(f'{self.cfg.project_id}')

        self.get_projectID = QPushButton("Get", self)
        self.get_projectID.clicked.connect(lambda: print(f"Project ID: {self.cfg.project_id}"))

        self.projectID_input.returnPressed.connect(self.update_projectID)

        redis_projectID_layout = QHBoxLayout()
        redis_projectID_layout.addWidget(self.projectID)
        redis_projectID_layout.addWidget(self.projectID_input)
        redis_projectID_layout.addWidget(self.get_projectID)

        section3.addLayout(redis_projectID_layout)

        section3.addSpacing(20)

        ###########################
        # Base Data Directory Field
        ###########################
        self.base_directory = QLabel("Base Data Directory", self)
        self.base_directory_input = QLineEdit(self)
        # self.redis_fields.append(self.base_directory_input)
        self.base_directory_input.setText(f'{self.cfg.base_data_dir}')
        self.base_directory_input.setReadOnly(True)

        self.get_base_directory = QPushButton("Get", self)
        self.get_base_directory.clicked.connect(lambda: print(f"Base Data Directory: {self.cfg.base_data_dir}"))

        redis_base_directory_layout = QHBoxLayout()
        redis_base_directory_layout.addWidget(self.base_directory)
        redis_base_directory_layout.addWidget(self.base_directory_input)
        redis_base_directory_layout.addWidget(self.get_base_directory)

        section3.addLayout(redis_base_directory_layout)
        
        section3.addWidget(create_horizontal_line_with_margin(15))

        #####################
        # TIFF Writer Section
        #####################
        if not globals.jfj:
            TIFF_section_label = QLabel("TIFF Writer", self)
            TIFF_section_label.setFont(font_big)

            section3.addWidget(TIFF_section_label)

            self.fname = QLabel("TIFF file name", self)
            self.tiff_path = QLineEdit(self)
            self.tiff_path.setText(f'{self.cfg.data_dir}')
            self.tiff_path.setReadOnly(True)
            self.fname_input = QLineEdit(self)
            self.fname_input.setText('file_name')

        # Define a regex that matches only valid Unix filename characters
        valid_regex = QRegularExpression("^[a-zA-Z0-9_.-]+$")

        if not globals.jfj:
            self.fname_input.setValidator(QRegularExpressionValidator(valid_regex, self))
            self.findex_input = QSpinBox(self)  

            tiff_file_layout = QHBoxLayout()
            tiff_file_layout.addWidget(self.fname, 2)
            tiff_file_layout.addWidget(self.tiff_path, 7)
            tiff_file_layout.addWidget(self.fname_input, 2)
            tiff_file_layout.addWidget(self.findex_input, 1)

            section3.addLayout(tiff_file_layout)

            self.frameAccumulator = None
            self.accumulate_button = QPushButton("Accumulate in TIFF", self)
            self.accumulate_button.setEnabled(False)
            self.accumulate_button.clicked.connect(self.start_accumulate)
            self.acc_spin = QSpinBox(self)
            self.acc_spin.setValue(10)
            self.acc_spin.setMaximum(1000000)
            self.acc_spin.setSuffix(' frames')

            accumulate_layout = QHBoxLayout()
            accumulate_layout.addWidget(self.accumulate_button)
            accumulate_layout.addWidget(self.acc_spin)

            section3.addLayout(accumulate_layout)

            section3.addWidget(create_horizontal_line_with_margin(15))

        #####################
        # HDF5 Writer Section
        #####################
        HDF5_section_label = QLabel("HDF5 Writer", self)
        HDF5_section_label.setFont(font_big)

        section3.addWidget(HDF5_section_label)

        # Initialize 
        self.h5_file_index = 0
        # Hdf5 file operations
        h5_file_ops_layout = QHBoxLayout()
        self.tag = QLabel("HDF5 tag", self)
        self.tag_input = QLineEdit(self)
        self.redis_fields.append(self.tag_input)
        self.tag_input.setText(self.cfg.measurement_tag)

        self.tag_input.setValidator(QRegularExpressionValidator(valid_regex, self))

        self.tag_input.returnPressed.connect(self.update_measurement_tag)

        self.index_label = QLabel("index")
        self.index_box = QSpinBox(self)
        self.redis_fields.append(self.index_box)
        self.index_box.setValue(self.cfg.file_id)
        self.index_box.setEnabled(False)

        self.index_box.editingFinished.connect(self.update_file_index)
        # self.index_box.valueChanged.connect(self.update_file_index) #Immediate change (better??)

        self.edit_checkbox = QCheckBox("Edit", self)
        self.edit_checkbox.stateChanged.connect(self.toggle_editability)

        h5_file_ops_layout.addWidget(self.tag) 
        h5_file_ops_layout.addWidget(self.tag_input)
        h5_file_ops_layout.addWidget(self.index_label)
        h5_file_ops_layout.addWidget(self.index_box)
        h5_file_ops_layout.addWidget(self.edit_checkbox)

        section3.addLayout(h5_file_ops_layout)

        output_folder_layout = QHBoxLayout()
        self.outPath = QLabel("H5 Output Path", self)
        self.outPath_input = QLineEdit(self)
        self.outPath_input.setText(self.cfg.data_dir.as_posix())
        self.outPath_input.setReadOnly(True)
        self.background_color = self.palette.color(QPalette.Base).name()
        
        output_folder_layout.addWidget(self.outPath, 2)
        output_folder_layout.addWidget(self.outPath_input, 7)

        section3.addLayout(output_folder_layout)

        hdf5_writer_layout = QGridLayout()
        self.streamWriter = None
        self.streamWriterButton = ToggleButton("Write Stream in H5", self)
        self.streamWriterButton.setEnabled(False)
        self.streamWriterButton.clicked.connect(self.toggle_hdf5Writer)
        self.start_H5_recording.connect(self.toggle_hdf5Writer_ON)
        self.stop_H5_recording.connect(self.toggle_hdf5Writer_OFF)
        # self.xds_checkbox = QCheckBox("Prepare for XDS processing", self)
        # self.xds_checkbox.setChecked(True)
        hdf5_writer_layout.addWidget(self.streamWriterButton, 0, 0, 1, 2)
        # hdf5_writer_layout.addWidget(self.xds_checkbox, 1, 0)

        # Change text color to orange when text is modified
        for field in self.redis_fields:
            if isinstance(field, QLineEdit):
                field.textChanged.connect(lambda _, le=field: self.text_modified(le))  # Pass QLineEdit reference directly
            elif isinstance(field, QSpinBox):
                field.valueChanged.connect(lambda value: self.spin_box_modified(field))
            else:
                logging.error("Only QLineEdit and QSpinBox objects are supported!")

        section3.addLayout(hdf5_writer_layout)
        # section3.addStretch()
        # self.setLayout(section3)

        #####################
        # Snapshot Writer Section !!!! aimed only for temporal use !!!!
        #####################

        if globals.jfj:
            section3.addWidget(create_horizontal_line_with_margin(15))
            self.visualization_panel = self.parent.visualization_panel
            self.pre_text = "dummy"
        
            snapshot_section_label = QLabel("Snapshot Writer", self)
            snapshot_section_label.setFont(font_big)

            section3.addWidget(snapshot_section_label)

            self.prefix_label = QLabel("Snapshot file prefix", self)
            self.prefix_input = QLineEdit(self)
            self.prefix_input.setText('xtal')
            # self.prefix_input.setReadOnly(True)

            self.pindex_input = QSpinBox(self)
            self.pindex_input.setValue(self.cfg.file_id)
            self.pindex_input.setEnabled(False)

            snapshot_layout = QHBoxLayout()
            snapshot_layout.addWidget(self.prefix_label, 3)
            snapshot_layout.addWidget(self.prefix_input, 6)
            snapshot_layout.addWidget(self.pindex_input, 1)

            section3.addLayout(snapshot_layout)

            self.snapshot_button = ToggleButton("Write Stream as a snapshot-H5", self)
            # self.snapshot_button.setEnabled(False)
            self.snapshot_button.clicked.connect(lambda: self.toggle_snapshot_btn())
            self.snapshot_spin = QSpinBox(self)
            self.snapshot_spin.setMaximum(60000) # 1min
            self.snapshot_spin.setValue(1000)
            self.snapshot_spin.setSuffix(' msec')

            snapshot_btn_layout = QHBoxLayout()
            snapshot_btn_layout.addWidget(self.snapshot_button)
            snapshot_btn_layout.addWidget(self.snapshot_spin)

            section3.addLayout(snapshot_btn_layout)
            section3.addStretch()
            self.setLayout(section3)

    def toggle_snapshot_btn(self):
        if not self.visualization_panel.stop_jfj_measurement.isEnabled():
            logging.warning('JFJ is not ready!!')
            return
        if not self.snapshot_button.started:
            self.pre_text = self.tag_input.text()
            self.tag_input.setText(self.prefix_input.text())
            self.update_measurement_tag()
            self.snapshot_button.setText("Stop")
            self.snapshot_button.started = True
            self.visualization_panel.send_command_to_jfjoch('collect')
            logging.info(f'Snapshot duration: {int(self.snapshot_spin.value())*1e-3} sec')
            time.sleep(int(self.snapshot_spin.value())*1e-3)
            self.toggle_snapshot_btn()
        else:
            self.visualization_panel.send_command_to_jfjoch('cancel')
            if self.parent.tem_controls.tem_action.temConnector: ## to be checked again
                self.parent.tem_controls.tem_action.control.send_to_tem("#more")
                time.sleep(0.2)
                logging.info(" ******************** Adding Info to H5 over Server...")
                send_with_retries(self.metadata_notifier.notify_metadata_update, 
                                    self.visualization_panel.formatted_filename, 
                                    self.parent.tem_controls.tem_action.control.tem_status, #self.control.tem_status, 
                                    self.cfg.beam_center, 
                                    None, # self.rotations_angles,
                                    self.cfg.threshold,
                                    retries=3, 
                                    delay=0.1) 
            logging.info(f'Snapshot duration end: {int(self.snapshot_spin.value())*1e-3} sec')
            self.pindex_input.setValue(self.cfg.file_id+1)
            self.tag_input.setText(self.pre_text)
            self.update_measurement_tag()
            self.snapshot_button.setText("Write Stream as a snapshot-H5")
            self.snapshot_button.started = False
        
    """ ************************************************ """
    """ Multiprocessing Version of the TIFF file Writing """
    """ ************************************************ """
    def start_accumulate(self):
        try:
            # Retrieve the file index and file path
            file_index = self.findex_input.value()
            self.update_base_data_directory() # update in case base_dir is manually changed after gui start
            fpath = Path(self.tiff_path.text())
            
            # Attempt to create the directory path if it doesn't exist
            fpath.mkdir(parents=True, exist_ok=True)
            
            # Construct the full filename
            full_fname = (fpath / f'{self.fname_input.text()}_{file_index}.tiff').as_posix()
            
            # If the folder and file name were successfully created, proceed with accumulation
            nb_frames_to_take = self.acc_spin.value()

            # Initialize FrameAccumulator and start accumulation
            self.frameAccumulator = FrameAccumulator(endpoint=globals.stream,
                                                    dtype=globals.dtype,
                                                    image_size=(globals.nrow, globals.ncol),
                                                    nframes=nb_frames_to_take,
                                                    fname=full_fname)
            self.frameAccumulator.start()
            
            # Wait for the process to finish
            self.frameAccumulator.accumulate_process.join()

            # Check if any error was reported in the error queue
            if not self.frameAccumulator.error_queue.empty():
                error = self.frameAccumulator.error_queue.get_nowait()
                raise error
        
            # Update file number for the next take
            self.findex_input.setValue(file_index + 1)

        except OSError as e:
            # Handle file system-related errors (e.g., permission denied, invalid path...)
            error_message = f"File system error: {e}"
            QMessageBox.critical(self, "Error", error_message)
            
        except Exception as e:
            # Handle any other unexpected errors
            error_message = f"An unexpected error occurred: {e}"
            QMessageBox.critical(self, "Error", error_message)

    # def modify_path_manually(self):
    #     path = self.outPath_input.text()
    #     if os.path.exists(path): 
    #         self.h5_folder_name = path
    
    def toggle_hdf5Writer_ON(self):
        if not self.streamWriterButton.started:
            self.toggle_hdf5Writer()

    def toggle_hdf5Writer_OFF(self):
        if self.streamWriterButton.started:
            self.toggle_hdf5Writer()

    def toggle_hdf5Writer(self):
        if not self.streamWriterButton.started:
            logging.debug("TCP address for Hdf5 writer to bind to is ", globals.stream)
            logging.debug("Data type to build the streamWriter object ", globals.file_dt)

            self.update_base_data_directory() # update GUI in case base_dir is manually changed after gui start

            try:
                self.cfg.data_dir.mkdir(parents=True, exist_ok=True) #TODO! do we need any checks here?
           
                self.formatted_filename = self.cfg.data_dir/self.cfg.fname # <-> self.cfg.fpath
                self.streamWriter = StreamWriter(filename=self.formatted_filename, 
                                                endpoint=globals.stream, 
                                                image_size = (globals.nrow,globals.ncol),
                                                dtype=globals.file_dt)
                self.streamWriter.start()
                self.streamWriterButton.setText("Stop Writing")
                self.streamWriterButton.started = True
            except Exception as e:
                # Handle any unexpected errors
                error_message = f"An unexpected error occurred: {e}"
                QMessageBox.critical(self, "Error", error_message)
        else:
            self.streamWriter.stop()
            if globals.tem_mode:
                tem_tasks = self.parent.tem_controls.tem_tasks
                logging.warning(f" rotation_button.started = True ? {tem_tasks.rotation_button.started == True}")
                if not tem_tasks.rotation_button.started:
                    logging.info(" -------------------- Updating file_id in DB...")
                    self.cfg.file_id += 1 
                    self.update_index_box()
                else:
                    tem_tasks.rotation_button.setText("Rotation")
                    tem_tasks.rotation_button.started= False
                    self.streamWriterButton.setEnabled(True) 
            else:
                logging.info(" ++++++++++++++++++++ Updating file_id in DB...")
                self.cfg.file_id += 1 
                self.update_index_box()
            # self.total_frame_nb.setValue(self.streamWriter.number_frames_witten)
            logging.info(f"Last written frame number is   {self.streamWriter.last_frame_number.value}")
            logging.info(f"Total number of frames written in H5 file:   {self.streamWriter.number_frames_witten}")

            self.streamWriterButton.setText("Write Stream in H5")
            self.streamWriterButton.started = False
    
    def text_modified(self, line_edit): 
        line_edit.setStyleSheet(f"QLineEdit {{ color: orange; background-color: {self.background_color}; }}")

    def spin_box_modified(self, spin_box):
        spin_box.setStyleSheet(f"QSpinBox {{ color: orange; background-color: {self.background_color}; }}")

    def update_userName(self):
        self.cfg.PI_name = self.userName_input.text() # Update the configuration when button is clicked
        self.reset_style(self.userName_input) # Reset style to default
        logging.info(f"User name (PI_name): {self.cfg.PI_name}")
        self.update_data_directory()

    def update_projectID(self):
        self.cfg.project_id = self.projectID_input.text()
        self.reset_style(self.projectID_input)
        logging.info(f"Project ID: {self.cfg.project_id}")
        self.update_data_directory()

    def update_experiment_class(self, button):
        self.cfg.experiment_class = button.text()
        logging.info(f"Experiment Class updated to: {self.cfg.experiment_class}")
        self.update_data_directory()

    def update_full_fname_for_jfjoch(self):
        # TODO Which logic is better to keep
        if globals.jfj:
            # self.parent.tem_controls.trigger_update_full_fname.emit()
            # self.parent.tem_controls.full_fname.setText(self.cfg.fpath.as_posix())
            self.parent.visualization_panel.full_fname.setText(self.cfg.fpath.as_posix())

    def update_base_data_directory(self):
        self.base_directory_input.setText(self.cfg.base_data_dir.as_posix())
        logging.info(f"Root directory has been changed to: {self.cfg.data_dir}")
        self.update_data_directory()

    def update_data_directory(self):
        if self.outPath_input.text() != self.cfg.data_dir.as_posix():
            self.outPath_input.setText(self.cfg.data_dir.as_posix())
            if not globals.jfj:            
                self.tiff_path.setText(self.cfg.data_dir.as_posix())
            logging.info(f"Data directory is: {self.cfg.data_dir.as_posix()}")
            
            # Check if folder exists and contains .h5 files to update file index
            self.reset_file_index_based_on_folder_contents()

    def update_measurement_tag(self):
        self.cfg.measurement_tag = self.tag_input.text()
        self.update_full_fname_for_jfjoch()
        self.reset_style(self.tag_input)
        logging.info(f"Measurement Tag: {self.cfg.measurement_tag}")

    def toggle_editability(self, state):
        self.index_box.setEnabled(state == 2) # 0 (Unchecked), 1 (PartiallyChecked), or 2 (Checked)

    def update_file_index(self):
        self.cfg.file_id = self.index_box.value()
        self.update_full_fname_for_jfjoch()
        self.reset_style(self.index_box)
        logging.info(f'H5 file index manually updated by user. Value of "file_id" equal to: {self.cfg.file_id}')

    def update_index_box(self, verbose=True):
        self.index_box.setValue(self.cfg.file_id)
        self.update_full_fname_for_jfjoch()
        self.reset_style(self.index_box)
        if verbose:
            logging.info(f"H5 file index updated after writing process. Next file will have index: {self.cfg.file_id}")

    def reset_file_index_based_on_folder_contents(self):
        data_dir = self.cfg.data_dir
        # Set default file index to 0
        max_index = -1
        
        # Check if directory exists and contains .h5 files
        if data_dir.exists() and data_dir.is_dir():
            h5_files = [f for f in os.listdir(data_dir) if f.endswith('.h5')]
            
            # Extract indices from filenames
            index_pattern = re.compile(r'^(\d{3})_')
            for file in h5_files:
                match = index_pattern.match(file)
                if match:
                    file_index = int(match.group(1))
                    max_index = max(max_index, file_index)
        
        # Update file_id with the highest index found + 1 i.e. zero if not files or new folder
        self.cfg.file_id = max_index + 1

        self.update_index_box(verbose=False)
        logging.info(f"File index has been reset to {self.cfg.file_id}!")
        logging.warning(f"self.cfg.file_id = {self.cfg.file_id}")
        logging.warning(f"self.index_box.value = {self.index_box.value()}")
        logging.info(f"The full path for the next saved file is:\n{self.cfg.fpath}")
        

    def reset_style(self, field):
        text_color = self.palette.color(QPalette.Text).name()
        if isinstance(field, QLineEdit):
            field.setStyleSheet(f"QLineEdit {{ color: {text_color}; background-color: {self.background_color}; }}")
        elif isinstance(field,QSpinBox):
            field.setStyleSheet(f"QSpinBox {{ color: {text_color}; background-color: {self.background_color}; }}")
