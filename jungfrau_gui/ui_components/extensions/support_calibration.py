import logging
from PySide6.QtGui import QIcon, QFont, QRegularExpressionValidator, QTransform
from PySide6.QtCore import Signal, Qt, QRegularExpression, QTimer, Slot, QObject
from PySide6.QtWidgets import (QGroupBox, QVBoxLayout, QHBoxLayout,
                                QLabel, QLineEdit, QSpinBox, QDoubleSpinBox, QButtonGroup,
                                QPushButton, QFileDialog, QCheckBox,
                                QMessageBox, QGridLayout, QRadioButton,
                                QTableWidgetItem, QHeaderView, QGraphicsEllipseItem)
import pyqtgraph as pg

from ...ui_components.utils import create_horizontal_line_with_margin, CopyableTableWidget
from ...ui_components.palette import *
from ...ui_components.toggle_button import ToggleButton
from ... import globals
from ...ui_components.tem_controls.toolbox import config as cfg_jf
from ...ui_components.tem_controls.toolbox import tool
from epoc import ConfigurationClient, auth_token, redis_host

import os
import re
import threading
import numpy as np
import json
import time
from scipy.interpolate import splprep, splev

font_big = QFont("Arial", 11)
font_big.setBold(True)
font_small = QFont("Arial", 8)

class SupportCalibration(QGroupBox):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent # ui_main_window
        self.ndata = 0
        self.cfg = ConfigurationClient(redis_host(), token=auth_token())
        self.initUI()

    def initUI(self):

        self.palette = get_palette("dark")
        self.setPalette(self.palette)
        self.scatter_overlays = []
        self.ellipse = None
        self.reference = globals.al_std        

        section5 = QVBoxLayout()

        #####################
        # Collected data table
        #####################

        hbox_headline = QHBoxLayout()
        still_label = QLabel("TEM parameters defined", self)
        still_label.setFont(font_big)
        lens_checkbox = QCheckBox('Lens values', self)
        lens_checkbox.setChecked(True)
        lens_checkbox.stateChanged.connect(self.toggle_columns)
        hbox_headline.addWidget(still_label)
        hbox_headline.addWidget(lens_checkbox)
        section5.addLayout(hbox_headline)
        
        items = ['', 'ID', 'HT', 'spot', 'Mag', 'Dist', 'Dist_cal', 'Dist_adj',
                 'e/A2/s', 'xo', 'yo', 'σx', 'σy', 'ellip', 'CL3', 'IL1', 'ILsx', 'ILsy', 'PLAx', 'PLAy']
        self.valuetable = CopyableTableWidget(3, len(items))
        self.valuetable.setFont(font_small)
        self.valuetable.setHorizontalHeaderLabels(items)
        for row in range(3):
            name_item = QTableWidgetItem(f"ID {row+1}")
            checkbox_item = QTableWidgetItem()
            checkbox_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            checkbox_item.setCheckState(Qt.Unchecked)
            self.valuetable.setItem(row, 0, checkbox_item)
            self.valuetable.setItem(row, 1, name_item)

        # self.datatable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.valuetable.horizontalHeader().setStretchLastSection(True)
        section5.addWidget(self.valuetable)

        hbox_control = QHBoxLayout()
        self.center_button = ToggleButton("Center", self)
        self.center_button.clicked.connect(self.toggle_centering)
        save_button = QPushButton("Save", self)
        save_button.clicked.connect(self.save_values)
        remove_button = QPushButton("Remove", self)
        remove_button.clicked.connect(self.remove_values)
        # restore_button.clicked.connect(self.launch_restoration)
        dump_button = QPushButton("Dump", self)
        dump_button.clicked.connect(lambda: self.export_table_to_json())
        hbox_control.addWidget(self.center_button)
        hbox_control.addWidget(save_button)
        hbox_control.addWidget(remove_button)
        hbox_control.addWidget(dump_button)
        section5.addLayout(hbox_control)

        section5.addWidget(create_horizontal_line_with_margin(15))

        #####################
        # Editable distance display
        #####################
        
        # radial integration plotter
        self.radialplot = pg.PlotWidget()
        freqs = np.linspace(0, 1000, 512)
        signals = np.random.randn(512)
        self.curve_prev = self.radialplot.plot(freqs, signals, pen='b')
        self.curve_ellp = self.radialplot.plot(freqs, signals, pen='m')
        self.curve = self.radialplot.plot(freqs, signals, pen='c')
        peakids = np.random.randint(0, high=511, size=20)
        self.peaks = pg.ScatterPlotItem(freqs[peakids], signals[peakids], pen=None, brush='w', size=6)
        self.radialplot.addItem(self.peaks)
        
        self.reference_lines = []
        for i in self.reference:
            pos_px = tool.d2radius_in_px(d=i, camlen=750)
            hline = pg.InfiniteLine(pos=pos_px, angle=90, pen=pg.mkPen('gray', width=1))
            self.radialplot.addItem(hline)
            self.reference_lines.append(hline)
            
        section5.addWidget(self.radialplot)

        distance_input = QLabel("Distance adjusted (mm):", self)
        self.distance_input = QDoubleSpinBox(self)
        self.distance_input.setRange(150, 2500)
        self.distance_input.setSingleStep(1)
        self.distance_input.setValue(750) # mm
        self.distance_input.setDecimals(1)
        adjust_button = QPushButton("Adjust in 1D", self)
        adjust_button.clicked.connect(lambda: self.adjust_with_peaks())
        adjust2d_button = QPushButton("Adjust in 2D->1D", self)
        adjust2d_button.clicked.connect(self.refine_with_ellipse)
        reset_button = QPushButton("Reset", self)
        reset_button.clicked.connect(self.remove_2ditems)

        distance_input_layout = QHBoxLayout()
        distance_input_layout.addWidget(distance_input)
        distance_input_layout.addWidget(self.distance_input)
        distance_input_layout.addWidget(adjust_button)
        distance_input_layout.addWidget(adjust2d_button)
        distance_input_layout.addWidget(reset_button)
        section5.addLayout(distance_input_layout)
        spotf_label = QLabel("SNR for spots:", self)
        self.spotf_snr = QDoubleSpinBox(self)
        self.spotf_snr.setRange(1.5, 10)
        self.spotf_snr.setSingleStep(0.1)
        self.spotf_snr.setValue(3)
        self.spotf_snr.setDecimals(1)
        fit_control = QLabel("Fit parameters:", self)
        self.fit_output_values = QLineEdit(self)
        self.fit_output_values.setReadOnly(True)
        fit_control_layout = QHBoxLayout()
        fit_control_layout.addWidget(spotf_label)
        fit_control_layout.addWidget(self.spotf_snr)
        fit_control_layout.addWidget(fit_control)
        fit_control_layout.addWidget(self.fit_output_values)
        section5.addLayout(fit_control_layout)
        self.distance_input.valueChanged.connect(self.redraw_reflines)
            
        section5.addWidget(create_horizontal_line_with_margin(15))
        section5.addStretch()
        self.setLayout(section5)

    def toggle_columns(self):
        ColumnIDs = range(13, 19) # for lense values
        for i in ColumnIDs:
            if self.valuetable.isColumnHidden(i):
                self.valuetable.setColumnHidden(i, False)
            else:
                self.valuetable.setColumnHidden(i, True)
        
    def toggle_centering(self):
        if not self.center_button.started:
            self.parent.tem_controls.tem_action.control.trigger_centerbeam.emit()
        
    def load_preset(self):
        d_input = self.parent.visualization_panel.tem_detector.calib_det_distance.value()
        self.distance_input.setValue(d_input)

    def adjust_with_peaks(self, use_preset=True):
        d_reference=self.reference
        if use_preset:
            self.load_preset()
        peaks = self.peaks.getData()
        peaks_selected = peaks[0][np.argsort(-peaks[1])[:4]]
        peak111_obs = peaks_selected[0]
        l0 = self.distance_input.value()
        peak111_cal = tool.d2radius_in_px(d=d_reference[0], camlen=l0,
                                     ht=self.parent.tem_controls.voltage_spBx.value())
        l1 = peak111_obs / peak111_cal * l0
        l_best, r0 = l1, 100
        for l in np.arange(l1-20, l1+20, 1):
            query, reference = np.meshgrid(peaks_selected, d_reference[:4])
            matrix = np.abs(query
                    - tool.d2radius_in_px(d=reference, camlen=l,
                    ht=self.parent.tem_controls.voltage_spBx.value()))
            r = np.sum(np.min(matrix, axis=-1))
            if r0 > r:
                r0 = r
                l_best = l
        self.distance_input.setValue(l_best)

    def remove_2ditems(self):
        self.ellipse = None
        [self.parent.plot.removeItem(i) for i in self.scatter_overlays]
        self.scatter_overlays = []
        
    def detect_ellipses(self):
        d_reference=self.reference
        thickness = 0.05 # in angstrom
        colors = ['w', 'c', 'b', 'm']
        main_view = self.parent.plot

        [main_view.removeItem(i) for i in self.scatter_overlays]
        self.scatter_overlays = []
        try:
            spots = self.parent.visualization_panel.spots
        except AttributeError:
            logging.error('No spots identified')
            return
        if len(spots) < 10:
            logging.warning(f'Not sufficient spot-detection: {len(spots)}')
            return
        df_spots = tool.update_spots_to_df(spots, self.cfg.beam_center,
                                        camlen=self.distance_input.value(),
                                        ht=self.parent.tem_controls.voltage_spBx.value())
        for id, d in enumerate(d_reference[:4]):
            spots_ext = df_spots[(df_spots['d'] > d-thickness) & (df_spots['d'] < d+thickness)]
            spots_sorted = spots_ext.sort_values(by=['theta'])
            if len(spots_sorted) < 20:
                overlay = pg.ScatterPlotItem(spots_sorted['x'], spots_sorted['y'], pen=None, brush=colors[id], size=3)
                overlay.setZValue(1)
                self.scatter_overlays.append(overlay)
            else:
                tck, u = splprep([spots_sorted['x'], spots_sorted['y']], s=0, per=True)
                u_fine = np.linspace(0, 1, 100)
                interpolated = splev(u_fine, tck)
                new_contour = np.array(interpolated, dtype='int') #.T.reshape(-1,1,2)
                # ellipse = cv2.fitEllipse(new_contour)
                # overlay = pg.ScatterPlotItem(new_contour[0], new_contour[1], pen=None, brush=colors[id], size=6)
                fit_params = tool.fitellipse(new_contour[0], new_contour[1])
                self.ellipse = (fit_params[0:2], fit_params[2:4], fit_params[4])
                self.fit_output_values.setText(f'{fit_params[0]:.0f}, {fit_params[1]:.0f}, {fit_params[2]/fit_params[3]:6.3f}, {np.rad2deg(fit_params[4]):.1f}')
                overlay = QGraphicsEllipseItem(-fit_params[2], -fit_params[3],
                                              fit_params[2]*2, fit_params[3]*2)
                transform = QTransform()
                transform.rotate(np.rad2deg(fit_params[4]))
                overlay.setTransform(transform)
                overlay.setPen(pg.mkPen(colors[id], width=2))
                overlay.setPos(fit_params[0], fit_params[1])
                overlay.setZValue(1)
                self.scatter_overlays.append(overlay)
                break
            
        [main_view.addItem(i) for i in self.scatter_overlays]
        ## restore default setting
        self.parent.visualization_panel.jfjoch_client.set_spotfind(enable=True)

    def refine_with_ellipse(self):
        d_reference=self.reference
        
        self.parent.visualization_panel.jfjoch_client.set_spotfind(
            enable=True,
            signal_to_noise_threshold = self.spotf_snr.value(), # 3
            max_pix_per_spot = 30, # 100
            # min_pix_per_spot = 6,
            high_resolution_limit = d_reference[3]*0.7,
            low_resolution_limit = d_reference[0]*1.3,
        )
        self.parent.visualization_panel.stream_view_button.clicked.emit() # reload beamcenter/distance
        QTimer.singleShot(500, lambda: self.parent.visualization_panel.stream_view_button.clicked.emit())
        QTimer.singleShot(1500, self.detect_ellipses) # delay for update of spots
        QTimer.singleShot(2500, lambda: self.adjust_with_peaks(use_preset=False)) # delay for update of integration
        
    def redraw_reflines(self):
        d_reference=self.reference
        for i in self.reference_lines:
            self.radialplot.removeItem(i)
        self.reference_lines = []
        for id, i in enumerate(d_reference):
            pos_px = tool.d2radius_in_px(d=i, camlen=self.distance_input.value(),
                                         ht=self.parent.tem_controls.voltage_spBx.value())
            hline = pg.InfiniteLine(pos=pos_px, angle=90, pen=pg.mkPen('gray', width=1))
            self.radialplot.addItem(hline)
            self.reference_lines.append(hline)
            if id==0: xmin=pos_px
            xmax=pos_px
        
        x_range = xmin-(xmax-xmin)*0.3, xmax+(xmax-xmin)*0.4
        y_range = np.max(self.peaks.getData()[1])*-0.1, np.max(self.peaks.getData()[1])*1.4
        view = self.radialplot.getViewBox()
        view.setRange(xRange=x_range, yRange=y_range, padding=0)
        
    def save_values(self):
        table = self.valuetable
        taskmanager = self.parent.tem_controls.tem_action.control
        taskmanager.send_to_tem("#more", asynchronous=False)
        tem_status = taskmanager.tem_status
        ht = tem_status['ht.GetHtValue']//globals.KV_TO_V
        d_nominal = tem_status['eos.GetMagValue_DIFF'][2]
        d_calibrated = self.parent.visualization_panel.tem_detector.calib_det_distance.value()
        d_adjusted = self.distance_input.value()
        doserate = taskmanager.beam_intensity["e_per_A2_sample"] # only relative value for specific grid/position
        beamxy = self.cfg.beam_center
        sigmaxy = taskmanager.prev_beamwidth
        if self.ellipse is None:
            ellipticity = 0
        else:
            ellipticity = self.ellipse[1][1]/self.ellipse[1][0]
        values = ['', f'{time.strftime("%H%M%S", time.localtime())}', ht, 
                          tem_status['eos.GetSpotSize']+1, 
                          tem_status['eos.GetMagValue_MAG'][0], 
                          d_nominal, d_calibrated, d_adjusted,
                          f'{doserate:.3f}', f'{beamxy[0]:.1f}', f'{beamxy[1]:.1f}', 
                          sigmaxy[0], sigmaxy[1],
                          f'{ellipticity:6.3f}', 
                          tem_status['lens.GetCL3'], tem_status['lens.GetIL1'], 
                          tem_status['defl.GetILs'][0], tem_status['defl.GetILs'][1],
                          tem_status['defl.GetPLA'][0], tem_status['defl.GetPLA'][1] 
                 ]
        
        if table.rowCount()-1 < self.ndata:
            table.insertRow(table.rowCount())

        for i in range(1, table.columnCount()):
            table.setItem(self.ndata, i, QTableWidgetItem(f"{values[i]}"))
            
        checkbox_item = QTableWidgetItem()
        checkbox_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        checkbox_item.setCheckState(Qt.Unchecked)
        table.setItem(self.ndata, 0, checkbox_item)

        self.ndata+=1

        for col in range(table.columnCount()):
            table.resizeColumnToContents(col)            

    def remove_values(self):
        table = self.valuetable
        rows_checked = self.get_checked_item()
        for i in rows_checked[::-1]:
            table.removeRow(i)
            self.ndata-=1
        
    def get_checked_item(self):
        table = self.valuetable
        rows_checked = []

        for row in range(table.rowCount()):
            if table.item(row, 0).checkState().value != 0:
                rows_checked.append(row)
        return rows_checked
    
    def export_table_to_json(self, file_path=None):
        if file_path is None:
            file_path = f'TEMvalues_{time.strftime("%Y%m%d-%H%M%S.json", time.localtime())}'
        
        table = self.valuetable
        rows = table.rowCount()
        cols = table.columnCount()

        data = []

        # extract headers
        headers = [table.horizontalHeaderItem(c).text() if table.horizontalHeaderItem(c) else f"col{c}" for c in range(cols)]
        for row in range(rows):
            row_data = {}
            for col in range(1, cols):
                item = table.item(row, col)
                if col == 1:
                    value = f"{time.strftime("%Y%m%d-", time.localtime())}" + item.text() if item else ""
                else:
                    value = item.text() if item else ""
                row_data[headers[col]] = value
            data.append(row_data)

        # Write to JSON file
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

        logging.info(f"Table exported to {file_path}")