import os
import logging
from PySide6.QtGui import QIcon
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (QGroupBox, QVBoxLayout, QHBoxLayout,
                                QLabel, QLineEdit, QSpinBox, QFrame,
                                QPushButton, QFileDialog, QCheckBox,
                                QMessageBox, QGridLayout)

from .stream_writer import StreamWriter
# from .frame_accumulator import FrameAccumulator
from .frame_accumulator_mp import FrameAccumulator

# import reuss
# import tifffile
from ... import globals
from ...ui_components.toggle_button import ToggleButton
from ...ui_components.utils import create_horizontal_line_with_margin

from epoc import ConfigurationClient, auth_token, redis_host


""" #Useful for Threading version of TIFF file Writing (below)
def save_captures(fname, data):
    logging.info(f'Saving: {fname}')
    # reuss.io.save_tiff(fname, data)
    tifffile.imwrite(fname, data.astype(np.int32)) """

class FileOperations(QGroupBox):
    trigger_update_h5_index_box = Signal()
    start_H5_recording = Signal()
    stop_H5_recording = Signal()
    
    def __init__(self, parent):
        super().__init__("File Operations")
        self.parent = parent
        self.cfg = ConfigurationClient(redis_host(), token=auth_token())
        self.trigger_update_h5_index_box.connect(self.update_index_box)
        self.initUI()
        

    def initUI(self):
        section3 = QVBoxLayout()

        self.fname = QLabel("TIFF file name", self)
        self.fname_input = QLineEdit(self)
        self.fname_input.setText('file')
        self.findex = QLabel("index:", self)
        self.findex_input = QSpinBox(self)  

        tiff_file_layout = QHBoxLayout()
        tiff_file_layout.addWidget(self.fname)
        tiff_file_layout.addWidget(self.fname_input)
        tiff_file_layout.addWidget(self.findex)
        tiff_file_layout.addWidget(self.findex_input)

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

        # Initialize 
        self.h5_file_index = 0
        # Hdf5 file operations
        h5_file_ops_layout = QHBoxLayout()
        self.prefix = QLabel("HDF5 tag", self)
        self.prefix_input = QLineEdit(self)
        self.prefix_input.setText(self.cfg.measurement_tag)
        self.prefix_input.textChanged.connect(self.update_measurement_tag)

        self.index_label = QLabel("index")
        self.index_box = QSpinBox(self)
        self.index_box.setValue( self.cfg.file_id )
        self.index_box.setDisabled(True)
        # self.index_box.valueChanged.connect(self.update_h5_file_index)

        h5_file_ops_layout.addWidget(self.prefix) 
        h5_file_ops_layout.addWidget(self.prefix_input)
        h5_file_ops_layout.addWidget(self.index_label)
        h5_file_ops_layout.addWidget(self.index_box)

        section3.addLayout(h5_file_ops_layout)

        output_folder_layout = QHBoxLayout()
        self.outPath = QLabel("H5 Output Path", self)
        self.outPath_input = QLineEdit(self)
        self.outPath_input.setText(self.cfg.data_dir.as_posix())
        self.outPath_input.textChanged.connect(self.modify_path_manually)
        self.h5_folder_name = self.outPath_input.text()
        self.folder_button = QPushButton()
        icon_path = os.path.join(os.path.dirname(__file__), "folder_icon.png")

        self.folder_button.setIcon(QIcon(icon_path))
        self.folder_button.setDisabled(True)
        # self.folder_button.clicked.connect(self.open_directory_dialog)
        
        output_folder_layout.addWidget(self.outPath, 2)
        output_folder_layout.addWidget(self.outPath_input, 7)
        output_folder_layout.addWidget(self.folder_button, 1)

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

        # self.nb_frame = QLabel("Number Written Frames:", self)
        # self.total_frame_nb = QSpinBox(self)
        # self.total_frame_nb.setMaximum(100000000)
        # hdf5_writer_layout.addWidget(self.nb_frame)
        # hdf5_writer_layout.addWidget(self.total_frame_nb)

        section3.addLayout(hdf5_writer_layout)
        section3.addStretch()
        self.setLayout(section3)

    """ ****************************************** """
    """ Threading Version of the TIFF file Writing """
    """ ****************************************** """        
    """ def start_accumulate(self):
        self.file_index = self.findex_input.value()
        f_name = self.fname_input.text()
        nb_frames_to_take = self.acc_spin.value()
        # Construct the (thread, worker) pair
        self.thread_acc = QThread()
        self.accumulator = FrameAccumulator(nb_frames_to_take)
        self.parent.threadWorkerPairs.append((self.thread_acc, self.accumulator))
        self.initializeWorker(self.thread_acc, self.accumulator)
        # Connect signals to relevant slots for operations
        self.accumulator.finished.connect(self.thread_acc.quit)
        self.accumulator.finished.connect(lambda: self.parent.stopWorker(self.thread_acc, self.accumulator))
        self.thread_acc.start()
        # Upadate file number for next take
        self.findex_input.setValue(self.file_index+1)
    
    def initializeWorker(self, thread, worker):
        worker.moveToThread(thread)
        logging.info(f"{worker.__str__()} is Ready!")
        thread.started.connect(worker.run)
        worker.finished.connect(lambda x: save_captures(f'{self.fname_input.text()}_{self.file_index}', x))
    """

    """ ************************************************ """
    """ Multiprocessing Version of the TIFF file Writing """
    """ ************************************************ """
    def start_accumulate(self):
        file_index = self.findex_input.value()
        full_fname = f'{self.fname_input.text()}_{self.findex_input.value()}.tiff'
        nb_frames_to_take = self.acc_spin.value()
        self.frameAccumulator = FrameAccumulator(endpoint=globals.stream,
                                                                  dtype= globals.dtype,
                                                                  image_size=(globals.nrow, globals.ncol),
                                                                  nframes=nb_frames_to_take,
                                                                  fname=full_fname)
        self.frameAccumulator.start()
        # Upadate file number for next take
        self.findex_input.setValue(file_index+1)

    def modify_path_manually(self):
        path = self.outPath_input.text()
        if os.path.exists(path): 
            self.h5_folder_name = path

    def open_directory_dialog(self):
        initial_dir = self.h5_folder_name or self.outPath_input.text()
        folder_name = QFileDialog.getExistingDirectory(self, "Select Directory", initial_dir)
        if not folder_name:
            return
        self.h5_folder_name = folder_name
        self.outPath_input.setText(self.h5_folder_name)
        logging.info(f"H5 output path set to: {self.h5_folder_name}")
    
    def toggle_hdf5Writer_ON(self):
        if not self.streamWriterButton.started:
            self.toggle_hdf5Writer()

    def toggle_hdf5Writer_OFF(self):
        if self.streamWriterButton.started:
            self.toggle_hdf5Writer()

    def toggle_hdf5Writer(self):
        if not self.streamWriterButton.started:
            # prefix = self.prefix_input.text().strip()
            # if not prefix:
            #     logging.error("Error: Prefix is missing! Please specify prefix of the written file(s).")# Handle error: Prefix is mandatory
            #     QMessageBox.critical(self, "Prefix Missing", "Prefix of written files is missing!\nPlease specify one under the field 'HDF5 prefix'.", QMessageBox.Ok)
            #     return
            
            logging.debug("TCP address for Hdf5 writer to bind to is ", globals.stream)
            logging.debug("Data type to build the streamWriter object ", globals.dtype)

            # """ If manually entered path is wrong, back to the latest correct path """
            # if self.outPath_input.text() != self.h5_folder_name:
            #     self.outPath_input.setText(self.h5_folder_name)

            # self.formatted_filename = self.generate_h5_filename(prefix)
            self.cfg.data_dir.mkdir(parents=True, exist_ok=True) #TODO! do we need any checks here?
            self.formatted_filename = self.cfg.data_dir/self.cfg.fname
            self.streamWriter = StreamWriter(filename=self.formatted_filename, 
                                             endpoint=globals.stream, 
                                             image_size = (globals.nrow,globals.ncol),
                                             dtype=globals.dtype)
            self.streamWriter.start()
            self.streamWriterButton.setText("Stop Writing")
            self.streamWriterButton.started = True
        else:
            self.streamWriterButton.setText("Write Stream in H5")
            self.streamWriterButton.started = False
            self.streamWriter.stop()
            if not self.parent.tem_controls.tem_tasks.rotation_button.started:
                self.cfg.file_id += 1 
                self.update_index_box()
            # self.total_frame_nb.setValue(self.streamWriter.number_frames_witten)
            logging.info(f"Last written frame number is   {self.streamWriter.last_frame_number.value}")
            # logging.info(f"Total number of frames written in H5 file:   {self.streamWriter.number_frames_witten}")
    
    def update_h5_file_index(self, index):
            self.h5_file_index = index
            
    def update_measurement_tag(self):
        self.cfg.measurement_tag = self.prefix_input.text()

    def update_index_box(self):
        self.index_box.setValue(self.cfg.file_id)
