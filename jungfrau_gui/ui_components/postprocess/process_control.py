import logging
from PySide6.QtGui import QIcon, QFont, QRegularExpressionValidator
from PySide6.QtCore import Signal, Qt, QRegularExpression, QTimer, Slot, QObject
from PySide6.QtWidgets import (QGroupBox, QVBoxLayout, QHBoxLayout,
                                QLabel, QLineEdit, QSpinBox, QButtonGroup,
                                QPushButton, QFileDialog, QCheckBox,
                                QMessageBox, QGridLayout, QRadioButton,
                                QTableWidgetItem, QHeaderView)

from ...ui_components.utils import create_horizontal_line_with_margin, CopyableTableWidget, CheckBoxHeader
from ...ui_components.palette import *
from .processresult_updater import DataProcessingManager

from ... import globals

import os
import re
import threading
import numpy as np

try:
    from vispy import scene, app
    from vispy.color import get_colormap
    vispy = True
except ModuleNotFoundError:
    vispy = False
    pass

font_big = QFont("Arial", 11)
font_big.setBold(True)
font_small = QFont("Arial", 8)

class XtalInfo(QObject):
    def __init__(self):
        super().__init__() # "DataProcessing"
        self.xtallist = [
            {
                "gui_id": 999,
                "gui_text": None,
                "gui_marker": None,
                "gui_label": None,
                "dataid": "999_9999", # 000_HHMM
                "filepath": None,
                "processor": None,
                "position": [0, 0, 0, 0, 0], #x,y,z,tx,ty
                "status": "dummy",
                "lattice": [10, 10, 10, 90, 90, 90],
                "spots": [5, 10],
                "cell axes": [1,0,0, 0,1,0, 0,0,1],
            }
        ]

class PostprocessControls(QGroupBox):
    update_xtalinfo_signal = Signal()
    update_ccdcinfo_signal = Signal()
    update_mergedinfo_signal = Signal(dict)

    def __init__(self, parent):
        super().__init__()
        self.parent = parent # ui_main_window
        
        self.sampleinfo = globals.sampleinfo
        self.ccdclist = []
        self.scatters = []
        self.savedspots = None
        self.initUI()

    def initUI(self):

        self.palette = get_palette("dark")
        self.setPalette(self.palette)

        section4 = QVBoxLayout()

        sample_label = QLabel("Sample Information", self)
        sample_label.setFont(font_big)
        section4.addWidget(sample_label)
        
        hbox_sample = QHBoxLayout()
        self.formula_input = QLineEdit(self)
        self.formula_input.setText(self.sampleinfo["formula"])
        hbox_sample.addWidget(self.formula_input)
        section4.addLayout(hbox_sample)
        
        #####################
        # XDS Processing
        #####################

        self.tem_xtalinfo = XtalInfo()
        self.xtallist = self.tem_xtalinfo.xtallist
        self.update_xtalinfo_signal.connect(self.update_xtalinfo)
        self.update_ccdcinfo_signal.connect(self.update_ccdcinfo)
        self.update_mergedinfo_signal.connect(self.update_mergedinfo)

        hbox_headline = QHBoxLayout()
        xtal_label = QLabel("Result of Processing", self)
        xtal_label.setFont(font_big)
        self.exp_checkbox = QCheckBox('Exp. values', self)
        self.exp_checkbox.setChecked(True)
        self.exp_checkbox.stateChanged.connect(self.toggle_columns)
        hbox_headline.addWidget(xtal_label, 2)
        hbox_headline.addWidget(self.exp_checkbox, 2)
        self.xds_checkbox = QCheckBox('XDS', self)
        self.xds_checkbox.setChecked(True)
        self.dials_checkbox = QCheckBox('DIALS', self)
        self.dials_checkbox.setChecked(True)
        hbox_headline.addWidget(self.xds_checkbox, 1)
        hbox_headline.addWidget(self.dials_checkbox, 1)
        section4.addLayout(hbox_headline)
        
        if globals.dev:
            lattice_label = QLabel("Preset lattice:", self)
            self.cell_input = QLineEdit(self)
            self.cell_input.setText(" ".join(map(lambda x: f"{float(x):.0f}", self.xtallist[0]["lattice"])))
            sg_label = QLabel("SG#:", self)
            self.sg_input = QSpinBox(self)
            self.sg_input.setValue(0)
            self.sg_input.setMaximum(230)
            self.run_button = QPushButton("Refine", self)
            # self.run_button.setEnabled(False)
            self.run_button.clicked.connect(self.launch_reprocess)
            self.merge_button = QPushButton("Merge & Solve", self)
            # self.merge_button.setEnabled(False)
            self.merge_button.clicked.connect(self.launch_mergeandsolve)

            process_layout = QHBoxLayout()
            process_layout.addWidget(lattice_label, 2)
            process_layout.addWidget(self.cell_input, 6)
            process_layout.addWidget(sg_label, 1)
            process_layout.addWidget(self.sg_input, 1)
            process_layout.addWidget(self.run_button, 1)
            process_layout.addWidget(self.merge_button, 1)
            section4.addLayout(process_layout)

            labels = ['', 'ID', 'Status', 'HT', 'spot', 'Mag', 'CL3', 'Dist', 'dTx', 'Dose', 'Spots', 'Cell', 'SG', 'Comp.', 'CC1/2', f'I/s', 'dmin']
            self.datatable = CopyableTableWidget(3, len(labels))
            self.datatable.setFont(font_small)
            self.header_checkbox = CheckBoxHeader(Qt.Horizontal, self.datatable)
            self.datatable.setHorizontalHeader(self.header_checkbox)
            self.header_checkbox.stateChanged.connect(self.toggle_all)
            self.datatable.setHorizontalHeaderLabels(labels)
            for row in range(3):
                name_item = QTableWidgetItem(f"ID {row+1}")
                checkbox_item = QTableWidgetItem()
                checkbox_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                checkbox_item.setCheckState(Qt.Unchecked)
                self.datatable.setItem(row, 0, checkbox_item)
                self.datatable.setItem(row, 1, name_item)
                

            self.datatable.horizontalHeader().setStretchLastSection(True)
            section4.addWidget(self.datatable)

            labels = ['Processor', 'Ndata', 'Cell', 'SG', 'Comp.', 'CC1/2', f'I/s', 'dmin']
            self.merged_datatable = CopyableTableWidget(2, len(labels))
            self.merged_datatable.setFont(font_small)
            self.merged_datatable.setHorizontalHeaderLabels(labels)
            self.merged_datatable.setMaximumHeight(105)
            self.merged_datatable.setItem(0, 0, QTableWidgetItem("XDS/XSCALE"))
            self.merged_datatable.setItem(1, 0, QTableWidgetItem("DIALS/xia2"))
            self.merged_datatable.horizontalHeader().setStretchLastSection(True)
            section4.addWidget(self.merged_datatable)

            hbox_restoration = QHBoxLayout()
            self.sync_button = QPushButton("Sync session-data", self)
            reload_spots = QPushButton("Reload Spots", self)
            reload_spots.clicked.connect(self.reload_spots_saved)
            self.reorient_checkbox = QCheckBox('reorient', self)
            self.reorient_checkbox.setChecked(False)
            self.reorient_checkbox.stateChanged.connect(lambda: self.plot_saved_spots())
            self.restore_tem = QPushButton("Restore TEM values", self)
            self.restore_tem.clicked.connect(self.launch_restoration)
            hbox_restoration.addWidget(self.sync_button, 3)
            hbox_restoration.addWidget(reload_spots, 2)
            hbox_restoration.addWidget(self.reorient_checkbox, 1)
            if not vispy:
                reload_spots.setEnabled(False)
                self.reorient_checkbox.setEnabled(False)
            hbox_restoration.addWidget(self.restore_tem, 3)
            section4.addLayout(hbox_restoration, 3)
            
            section4.addWidget(create_horizontal_line_with_margin(15))

            hbox_headline_ccdc = QHBoxLayout()
            ccdc_label = QLabel("CCDC hits", self)
            ccdc_label.setFont(font_big)
            self.ccdc_checkbox = QCheckBox('Search on update', self)
            self.ccdc_checkbox.setChecked(True)
            # self.ccdc_checkbox.stateChanged.connect(self.toggle_columns)
            hbox_headline_ccdc.addWidget(ccdc_label)
            hbox_headline_ccdc.addWidget(self.ccdc_checkbox)
            section4.addLayout(hbox_headline_ccdc)

            self.ccdctable = CopyableTableWidget(3, 6)
            self.ccdctable.setFont(font_small)
            self.ccdctable.setHorizontalHeaderLabels(['Match%', 'ID', 'Cell', 'Formula', 'SG', 'ED']) # 'Centering'
            for row in range(3):
                name_item = QTableWidgetItem(f"ID {row+1}")
                self.ccdctable.setItem(row, 1, name_item)

            self.ccdctable.horizontalHeader().setStretchLastSection(True)
            section4.addWidget(self.ccdctable)
            
            section4.addStretch()
            self.setLayout(section4)

    @Slot()
    def update_xtalinfo(self):
        filtered_list = [item for item in self.xtallist if item.get('status') in ['recorded', 'processed']]
        datatable = self.datatable
        logging.debug(filtered_list)
        while datatable.rowCount() < len(filtered_list):
            datatable.insertRow(datatable.rowCount())
            checkbox_item = QTableWidgetItem()
            checkbox_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            checkbox_item.setCheckState(Qt.Unchecked)
            datatable.setItem(datatable.rowCount()-1, 0, checkbox_item)
            
        for row, item in enumerate(filtered_list):
            singleitems = ['dataid', 'status', 'ht', 'spot_size', 'magnification', 'brightness', 'distance_nominal', 'rotation_speed_nominal', 'e_per_A2_sample', 'space group', 'completeness', 'cc1/2', 'ioversigma', 'd_min_est']
            col_ids = [1, 2, 3, 4, 5, 6, 7, 8, 9, 12, 13, 14, 15, 16]
            for id, i in enumerate(singleitems):
                if not i in item:
                    datatable.setItem(row, col_ids[id], QTableWidgetItem(f""))
                elif i == 'e_per_A2_sample':
                    datatable.setItem(row, col_ids[id], QTableWidgetItem(f"{item[i]:.3f}"))
                else:
                    if not i +"_dials" in item:
                        datatable.setItem(row, col_ids[id], QTableWidgetItem(f"{item[i]}"))
                    else:
                        datatable.setItem(row, col_ids[id], QTableWidgetItem(f"{item[i]}\n" + 
                                                                             f"{item[str(i)+"_dials"]}"))
            try:
                if not 'spots_dials' in item:
                    spots_item = QTableWidgetItem(f"{item["spots"][0]} / {item["spots"][1]}")
                else:
                    spots_item = QTableWidgetItem(f"{item["spots"][0]} / {item["spots"][1]}\n" +
                                                  f"{item["spots_dials"][0]} / {item["spots_dials"][1]}")
                datatable.setItem(row, 10, spots_item)
                if not 'lattice_dials' in item:
                    cell_item = QTableWidgetItem("".join(map(lambda x: f"{float(x):.1f} ", item["lattice"])))
                else:
                    cell_item = QTableWidgetItem("".join(map(lambda x: f"{float(x):.1f} ", item["lattice"])) +'\n'+
                                                 "".join(map(lambda x: f"{float(x):.1f} ", item["lattice_dials"])))
                datatable.setItem(row, 11, cell_item)
            except KeyError:
                logging.debug(item)
            
        for col in range(datatable.columnCount()):
            datatable.resizeColumnToContents(col)
        self.exp_checkbox.setChecked(False)

    def toggle_all(self, state):
        for row in range(self.datatable.rowCount()):
            checkbox = self.datatable.item(row, 0)
            if checkbox:
                checkbox.setCheckState(state)
        
    def get_checked_xtalinfo(self):
        datatable = self.datatable
        n_checked = 0
        last_checked = None
        
        for row in range(datatable.rowCount()):
            dataid_selected = datatable.item(row, 1).text()
            match = next((id for id, item in enumerate(self.xtallist) if item.get('dataid') == dataid_selected), None)
            if match is not None:
                if datatable.item(row, 0).checkState().value != 0:
                    self.xtallist[match]["reprocess"] = 'checked'
                    n_checked +=1
                    last_checked = self.xtallist[match]
                else:
                    self.xtallist[match]["reprocess"] = 'unchecked'
        return n_checked, last_checked

    def launch_reprocess(self):
        
        self.get_checked_xtalinfo()
        
        cell_input = self.cell_input.text().split()

        if len(cell_input) != 6:
            logging.error(f"Invalid cell definition: {cell_input}")
            return
       
        reprocess_manager = DataProcessingManager(self, mode=4)
        reprocess_manager.run()
        
    def launch_mergeandsolve(self):
        
        self.get_checked_xtalinfo()
        
        cell_input = self.cell_input.text().split()

        if len(cell_input) != 6:
            logging.error(f"Invalid cell definition: {cell_input}")
            return
       
        mergeandsolve_manager = DataProcessingManager(self, mode=5)
        mergeandsolve_manager.run()

    def reload_spots_saved(self):
        
        self.get_checked_xtalinfo()
        
        spot_loader = DataProcessingManager(self, mode=6, verbose=False)
        spot_loader.run()
        self.plot_saved_spots()

    def plot_saved_spots(self, removeall=False):
        tem_ctrl = self.parent.tem_controls.tem_stagectrl
        for i in self.scatters: i.parent = None
        self.scatters = []
        
        if removeall: return
        
        cmap = get_colormap('coolwarm')
        num_colors = 7
        color_array = cmap.map(np.linspace(0, 1, num_colors))
        color_array[:,-1] = 0.7

        if self.savedspots is not None:
            for id, spots in enumerate(self.savedspots):
                plotdata = np.array(spots['spots_jfj'])
                xyz = plotdata[:3].T
                if self.reorient_checkbox.isChecked():
                    matrix = np.array(spots['cell axes'], dtype=float)
                    abs_matrix = (matrix.T/np.linalg.norm(matrix, axis=-1)).T
                    xyz = (abs_matrix @ plotdata[:3]).T
                color = color_array[id%num_colors]
                size = np.log(plotdata[4])
                scatter = scene.visuals.Markers(parent=tem_ctrl.view.scene)
                scatter.set_gl_state('translucent', depth_test=True)
                scatter.set_data(xyz, edge_color=None, size=size, face_color=color)
                self.scatters.append(scatter)
        
    def toggle_columns(self):
        ColumnIDs = range(3, 10) # for experimental values
        for i in ColumnIDs:
            if self.datatable.isColumnHidden(i):
                self.datatable.setColumnHidden(i, False)
            else:
                self.datatable.setColumnHidden(i, True)

    def launch_restoration(self):
        n_checked, data_checked = self.get_checked_xtalinfo()
        if n_checked != 1:
            logging.error(f"No or multiple selection ({n_checked}) !")
            return
        self.parent.tem_controls.tem_action.trigger_start_restoration.emit(data_checked)
        
    @Slot()
    def update_ccdcinfo(self):
        logging.debug(self.ccdclist)
        datatable = self.ccdctable
        filtered_list = [item for item in self.xtallist if item.get('idxref') in ['Succeeded']]
        while datatable.rowCount() < len(self.ccdclist):
            datatable.insertRow(datatable.rowCount())
            checkbox_item = QTableWidgetItem()
            checkbox_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            checkbox_item.setCheckState(Qt.Unchecked)
            datatable.setItem(datatable.rowCount()-1, 0, checkbox_item)

            self.ccdctable.setHorizontalHeaderLabels(['Match%', 'ID', 'Cell', 'Formula', 'SG', 'ED'])            

        for row, item in enumerate(self.ccdclist):
            datatable.setItem(row, 0, QTableWidgetItem(f"{item['ccdc_count']/len(filtered_list)*100:.1f}"))
            datatable.setItem(row, 1, QTableWidgetItem(f"{item['ccdc_id']}"))
            datatable.setItem(row, 2, QTableWidgetItem("".join(map(lambda x: f"{float(x):.1f} ", item["ccdc_cell"]))))
            datatable.setItem(row, 3, QTableWidgetItem(f"{item['ccdc_formula']}"))
            datatable.setItem(row, 4, QTableWidgetItem(f"{item['ccdc_sg']}"))
            datatable.setItem(row, 5, QTableWidgetItem(f"{item['ed_subset_id']}"))
            # datatable.setItem(row, 6, QTableWidgetItem(f"{item['ccdc_lattice_centring']}"))

        for col in range(datatable.columnCount()):
            datatable.resizeColumnToContents(col)
            
    @Slot(dict)
    def update_mergedinfo(self, info_d):
        datatable = self.merged_datatable
        nrow = 0 if info_d["gui_id"] == 888 else 1
        labels_in_dict = ['N_merged', 'cell_used', 'sg_used', 'completeness', 'cc1/2', 'ioversigma', 'd_min_est']
        
        for col, i in enumerate(labels_in_dict):
            if not i in info_d:
                datatable.setItem(nrow, col+1, QTableWidgetItem(f""))
            elif i == 'cell_used':
                datatable.setItem(nrow, col+1, QTableWidgetItem("".join(map(lambda x: f"{float(x):.1f} ", info_d[i]))))
            else:
                datatable.setItem(nrow, col+1, QTableWidgetItem(f"{info_d[i]}"))
            datatable.resizeColumnToContents(col)
                