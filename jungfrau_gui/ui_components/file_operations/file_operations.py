import logging
from PySide6.QtGui import QIcon, QFont, QRegularExpressionValidator
from PySide6.QtCore import Signal, Qt, QRegularExpression, QTimer, Slot
from PySide6.QtWidgets import (QGroupBox, QVBoxLayout, QHBoxLayout,
                                QLabel, QLineEdit, QSpinBox, QButtonGroup,
                                QPushButton, QFileDialog, QCheckBox,
                                QMessageBox, QGridLayout, QRadioButton)

# from .stream_writer import StreamWriter
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

font_big = QFont("Arial", 11)
font_big.setBold(True)

class XtalInfo(QGroupBox):
    def __init__(self):
        super().__init__() # "DataProcessing"
        self.initUI()

    def initUI(self):
        xtal_section = QVBoxLayout()
        xtal_label = QLabel("Result of Processing", self)
        xtal_label.setFont(font_big)

        xtal_section.addWidget(xtal_label)

        hbox_process = QHBoxLayout()
        xds_label = QLabel("XDS:", self)
        # dials_label = QLabel("DIALS:", self)
        self.xds_results = QLineEdit(self)
        self.xds_results.setReadOnly(True)
        # self.dials_results = QLineEdit(self)
        # self.dials_results.setReadOnly(True)
        hbox_process.addWidget(xds_label)
        hbox_process.addWidget(self.xds_results)
        # hbox_process.addWidget(dials_label)
        # hbox_process.addWidget(self.dials_results)
        xtal_section.addLayout(hbox_process)

        # self.hbox_command = QHBoxLayout()
        # command_label = QLabel("TEMcmd:", self)
        # self.command_input = QComboBox(self)
        # # self.command_input.addItems(['#more', 'lens.SetNtrl(0)', 'stage.SetMovementValueMeasurementMethod(0)', 'stage.SetOrg()'])
        # self.command_input.setEditable(True)
        # self.send_button = QPushButton("Send", self)
        # self.hbox_command.addWidget(command_label, 1)
        # self.hbox_command.addWidget(self.command_input, 7)
        # self.hbox_command.addWidget(self.send_button, 1)
        # xtal_section.addLayout(self.hbox_command)

        self.setLayout(xtal_section)

class FileOperations(QGroupBox):
    trigger_update_h5_index_box = Signal()
    update_xtalinfo_signal = Signal(str, str)

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

        redis_experiment_class_layout = QHBoxLayout()
        redis_experiment_class_layout.addWidget(self.experiment_class)
        for rb in self.rb_experiment_class.buttons():
            redis_experiment_class_layout.addWidget(rb, 1)
        # redis_experiment_class_layout.addWidget(self.get_experiment_class)

        section3.addLayout(redis_experiment_class_layout)
        
        #################
        # User Name Field
        #################
        self.userName = QLabel("PI name", self)
        self.userName_input = QLineEdit(self)
        self.redis_fields.append(self.userName_input)
        self.userName_input.setText(f'{self.cfg.PI_name}')

        self.userName_input.returnPressed.connect(self.update_userName)

        redis_UserName_layout = QHBoxLayout()
        redis_UserName_layout.addWidget(self.userName)
        redis_UserName_layout.addWidget(self.userName_input)

        section3.addLayout(redis_UserName_layout)

        ##################
        # Project ID Field
        ##################
        self.projectID = QLabel("Project ID", self)
        self.projectID_input = QLineEdit(self)
        self.redis_fields.append(self.projectID_input)
        self.projectID_input.setText(f'{self.cfg.project_id}')

        self.projectID_input.returnPressed.connect(self.update_projectID)

        redis_projectID_layout = QHBoxLayout()
        redis_projectID_layout.addWidget(self.projectID)
        redis_projectID_layout.addWidget(self.projectID_input)

        section3.addLayout(redis_projectID_layout)

        section3.addSpacing(20)

        ###########################
        # Base Data Directory Field
        ###########################
        self.base_directory = QLabel("Base Data Directory", self)
        self.base_directory_input = QLineEdit(self)
        self.base_directory_input.setText(f'{self.cfg.base_data_dir}')
        self.base_directory_input.setReadOnly(True)

        redis_base_directory_layout = QHBoxLayout()
        redis_base_directory_layout.addWidget(self.base_directory)
        redis_base_directory_layout.addWidget(self.base_directory_input)

        section3.addLayout(redis_base_directory_layout)
        
        section3.addWidget(create_horizontal_line_with_margin(15))

        # Define a regex that matches only valid Unix filename characters
        valid_regex = QRegularExpression("^[a-zA-Z0-9_.-]+$")

        #####################
        # HDF5 Writer Section
        #####################
        HDF5_section_label = QLabel("HDF5 output", self)
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

        # Change text color to orange when text is modified
        for field in self.redis_fields:
            if isinstance(field, QLineEdit):
                field.textChanged.connect(lambda _, le=field: self.text_modified(le))  # Pass QLineEdit reference directly
            elif isinstance(field, QSpinBox):
                field.valueChanged.connect(lambda value: self.spin_box_modified(field))
            else:
                logging.error("Only QLineEdit and QSpinBox objects are supported!")

        #####################
        # Snapshot Writer Section !!!! aimed only for temporal use !!!!
        #####################

        section3.addWidget(create_horizontal_line_with_margin(15))
        self.pre_text = "dummy"

        snapshot_section_label = QLabel("Snapshot Writer", self)
        snapshot_section_label.setFont(font_big)

        section3.addWidget(snapshot_section_label)

        self.prefix_label = QLabel("Snapshot file prefix", self)
        self.prefix_input = QLineEdit(self)
        self.prefix_input.setText('xtal')
        # self.prefix_input.setReadOnly(True)

        self.snapshot_index_input = QSpinBox(self)
        self.snapshot_index_input.setValue(self.cfg.file_id)
        self.snapshot_index_input.setEnabled(False)

        snapshot_layout = QHBoxLayout()
        snapshot_layout.addWidget(self.prefix_label, 3)
        snapshot_layout.addWidget(self.prefix_input, 6)
        snapshot_layout.addWidget(self.snapshot_index_input, 1)

        section3.addLayout(snapshot_layout)

        self.snapshot_button = ToggleButton("Write Stream as a snapshot-H5", self)
        self.snapshot_button.clicked.connect(self.toggle_snapshot_btn)
        self.snapshot_spin = QSpinBox(self)
        self.snapshot_spin.setMaximum(60000) # 1min
        self.snapshot_spin.setValue(1000)
        self.snapshot_spin.setSuffix(' msec')

        snapshot_btn_layout = QHBoxLayout()
        snapshot_btn_layout.addWidget(self.snapshot_button)
        snapshot_btn_layout.addWidget(self.snapshot_spin)

        section3.addLayout(snapshot_btn_layout)
        section3.addWidget(create_horizontal_line_with_margin(15))
        
        #####################
        # XDS Processing
        #####################

        self.tem_xtalinfo = XtalInfo()
        self.update_xtalinfo_signal.connect(self.update_xtalinfo)
        section3.addWidget(self.tem_xtalinfo)

        section3.addStretch()
        self.setLayout(section3)

    @Slot(str, str)
    def update_xtalinfo(self, progress, software='XDS'):
        try:
            if software == 'XDS':
                self.tem_xtalinfo.xds_results.setText(progress)
            # elif software == 'DIALS':
            #     self.tem_xtalinfo.dials_results.setText(progress)
        except AttributeError:
            pass 

    def toggle_snapshot_btn(self):
        if not self.parent.visualization_panel.jfj_broker_is_ready:
            logging.warning('JFJ is not ready!!')
            return
        if not self.snapshot_button.started:
            self.pre_text = self.tag_input.text()
            self.tag_input.setText(self.prefix_input.text())
            self.update_measurement_tag()
            self.snapshot_button.setText("Stop")
            self.snapshot_button.started = True
            self.parent.visualization_panel.send_command_to_jfjoch('collect')
            logging.info(f'Snapshot duration: {int(self.snapshot_spin.value())*1e-3} sec')
            QTimer.singleShot(self.snapshot_spin.value(), self.toggle_snapshot_btn)
        else:
            self.parent.visualization_panel.send_command_to_jfjoch('cancel')
            if self.parent.tem_controls.tem_action.temConnector is not None: ## to be checked again
                self.parent.tem_controls.tem_action.control.send_to_tem("#more", asynchronous = False)
                logging.info(" ******************** Adding Info to H5 over Server...")
                try:
                    send_with_retries(self.metadata_notifier.notify_metadata_update, 
                                        self.parent.visualization_panel.formatted_filename, 
                                        self.parent.tem_controls.tem_action.control.tem_status, #self.control.tem_status, 
                                        self.cfg.beam_center, 
                                        None, # self.rotations_angles,
                                        self.cfg.threshold,
                                        retries=3, 
                                    delay=0.1) 
                except Exception as e:
                    logging.error(f"Metadata Update Error: {e}")
            logging.info(f'Snapshot duration end: {int(self.snapshot_spin.value())*1e-3} sec')
            self.tag_input.setText(self.pre_text) # reset the tag to value before snapshot
            self.update_measurement_tag()
            self.snapshot_button.setText("Write Stream as a snapshot-H5")
            self.snapshot_button.started = False
           
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
        # if globals.jfj:
        self.parent.visualization_panel.full_fname.setText(self.cfg.fpath.as_posix())

    def update_base_data_directory(self):
        self.base_directory_input.setText(self.cfg.base_data_dir.as_posix())
        logging.info(f"Root directory has been changed to: {self.cfg.data_dir}")
        self.update_data_directory()

    def update_data_directory(self):
        if self.outPath_input.text() != self.cfg.data_dir.as_posix():
            self.outPath_input.setText(self.cfg.data_dir.as_posix())
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
        self.snapshot_index_input.setValue(self.index_box.value())
        self.update_full_fname_for_jfjoch()
        self.reset_style(self.index_box)
        logging.info(f'H5 file index manually updated by user. Value of "file_id" equal to: {self.cfg.file_id}')

    def update_index_box(self, verbose=True):
        self.index_box.setValue(self.cfg.file_id)
        self.snapshot_index_input.setValue(self.index_box.value())
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
