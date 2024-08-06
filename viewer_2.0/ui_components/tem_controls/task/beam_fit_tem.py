import time
import math
import logging
from datetime import datetime as dt
from ui_components.tem_controls.task.task import Task
import numpy as np
from PySide6.QtGui import QTransform
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsRectItem
from PySide6.QtCore import QRectF
import pyqtgraph as pg

from ..fit_beam_intensity import fit_2d_gaussian_roi, fit_2d_gaussian_roi_test


IL1_0 = 21902 #40345
ILs_0 = [33040, 32688]

class BeamFitTask(Task):
    def __init__(self, control_worker):
        super().__init__(control_worker, "BeamFit")
        self.duration_s = 60 # should be replaced with a practical value
        self.estimateds_duration = self.duration_s + 0.1
        self.control = control_worker 
    
    def run(self, init_IL1=IL1_0):
        logging.info("Start IL1 rough-sweeping.")
        _, il1_guess1 = self.sweep_il1_linear(init_IL1 - 250, init_IL1 + 250, 50)
        self.tem_command("lens", "SetILFocus", [il1_guess1])
        time.sleep(1)

        # logging.info("Start ILs rough-sweeping.")
        # _, _, ils_guess1 = self.sweep_stig_linear(500, 50)
        # self.tem_command("defl", "SetILs", ils_guess1)
        # time.sleep(1)
               
        # logging.info("Start IL1 fine-sweeping.")
        # _, il1_guess2 = self.sweep_il1_linear(il1_guess1 - 50, il1_guess1 + 50, 5)
        # self.tem_command("lens", "SetILFocus", [il1_guess2])
        # time.sleep(1)

        # logging.info("Start ILs fine-sweeping.")
        # _, _, ils_guess2 = self.sweep_stig_linear(50, 5)
        # self.tem_command("defl", "SetILs", ils_guess2)
        # time.sleep(1)
    
    def sweep_il1_linear(self, lower, upper, step, wait_time_s=0.2):
        max_amplitude = 0
        max_il1value = None
        logging.info("before loop")
        for il1_value in range(lower, upper, step):
            self.tem_command("lens", "SetILFocus", [il1_value])
            time.sleep(wait_time_s)
            logging.debug(f"{dt.now()}, il1_value = {il1_value}")

            """ *** Fitting *** """
            # amplitude = self.control.stream_receiver.fit[0] # amplitude
            im = self.control.tem_action.parent.imageItem.image
            roi = self.control.tem_action.parent.roi
            fit_result = fit_2d_gaussian_roi_test(im, roi)
            # Update pop-up plot and drawn ellipse 
            self.updateFitParams(fit_result.best_values)
            # Determine peak value (amplitude)
            amplitude = float(fit_result.best_values['amplitude'])
            """ *************** """
            
            if max_amplitude < amplitude:
                max_amplitude = amplitude
                max_il1value = il1_value
            logging.debug(f"{dt.now()}, amplitude = {amplitude}")
        logging.info("end loop")

        logging.info("Now reset to the initial value (for safety in testing)")
        time.sleep(1)
        self.tem_command("lens", "SetILFocus", [(lower + upper)//2])

        return max_amplitude, max_il1value
        
    def move_to_stigm(self, stigm_x, stigm_y):
        self.tem_command("defl", "SetILs", [stigm_x, stigm_y])
        
    def sweep_stig_linear(self, deviation, step, wait_time_s=0.2, init_stigm=ILs_0):
        min_sigma1 = 1000
        min_stigmvalue = init_stigm
        best_ratio = 2

        for stigmx_value in range(init_stigm[0]-deviation, init_stigm[0]+deviation, step):
            self.tem_command("defl", "SetILs", [stigmx_value, init_stigm[1]])
            time.sleep(wait_time_s)
            logging.debug(f"{dt.now()}, stigmx_value = {stigmx_value}")
            
            """ *** Fitting *** """
            # sigma1 = self.control.stream_receiver.fit[0] # smaller sigma value (shorter axis)
            im = self.control.tem_action.parent.imageItem.image
            roi = self.control.tem_action.parent.roi
            fit_result = fit_2d_gaussian_roi_test(im, roi)
            # Update pop-up plot and drawn ellipse 
            self.updateFitParams(fit_result.best_values)
            # Determine smaller sigma (sigma1)
            sigma_x = float(fit_result.best_values['sigma_x'])
            sigma_y = float(fit_result.best_values['sigma_y'])
            sigma1 = min(sigma_x, sigma_y)
            """ *************** """
            
            if min_sigma1 > sigma1:
                min_sigma1 = sigma1
                min_stigmvalue = [stigmx_value, init_stigm[1]]

        self.tem_command("defl", "SetILs", min_stigmvalue)
        time.sleep(1)
        
        for stigmy_value in range(init_stigm[1]-deviation, init_stigm[1]+deviation, step):
            self.tem_command("defl", "SetILs", [min_stigmvalue[0], stigmy_value])
            time.sleep(wait_time_s)
            logging.debug(f"{dt.now()}, stigmy_value = {stigmy_value}")
            
            """ *** Fitting *** """
            # ratio = self.control.stream_receiver.fit[0] # sigma ratio
            im = self.control.tem_action.parent.imageItem.image
            roi = self.control.tem_action.parent.roi
            fit_result = fit_2d_gaussian_roi_test(im, roi)
            # Update pop-up plot and drawn ellipse 
            self.updateFitParams(fit_result.best_values)
            # Determine sigmas ratio
            sigma_x = float(fit_result.best_values['sigma_x'])
            sigma_y = float(fit_result.best_values['sigma_y'])
            ratio = max(sigma_x, sigma_y)/min(sigma_x, sigma_y)
            """ *************** """
            
            if abs(best_ratio - 1) > abs(ratio - 1):
                best_ratio = ratio
                min_stigmvalue = [min_stigmvalue[0], stigmy_value]
        
        logging.debug("Now reset to the initial value (for safety in testing)")
        time.sleep(1)
        self.tem_command("defl", "SetILs", init_stigm)
        
        return min_sigma1, best_ratio, min_stigmvalue
    
    def updateFitParams(self, fit_result_best_values):
        amplitude = float(fit_result_best_values['amplitude'])
        xo = float(fit_result_best_values['xo'])
        yo = float(fit_result_best_values['yo'])        
        sigma_x = float(fit_result_best_values['sigma_x'])
        sigma_y = float(fit_result_best_values['sigma_y'])
        theta_deg = 180*float(fit_result_best_values['theta'])/np.pi 
        # Update graph in pop-up Window
        if self.control.tem_action.tem_tasks.plotDialog != None:
            self.control.tem_action.tem_tasks.plotDialog.updatePlot(amplitude, sigma_x, sigma_y)
        # Draw the fitting line at the FWHM of the 2d-gaussian
        self.drawFittingEllipse(xo,yo,sigma_x, sigma_y, theta_deg)

    def drawFittingEllipse(self, xo, yo, sigma_x, sigma_y, theta_deg):
        # p = 0.5 is equivalent to using the Full Width at Half Maximum (FWHM)
        # where FWHM = 2*sqrt(2*ln(2))*sigma ~ 2.3548*sigma
        p = 0.2
        alpha = 2*np.sqrt(-2*math.log(p))
        width = alpha * max(sigma_x, sigma_y) # Use 
        height = alpha * min(sigma_x, sigma_y) # 
        # Check if the item is added to a scene, and remove it if so
        scene = self.control.tem_action.tem_tasks.ellipse_fit.scene() 
        scene_x = self.control.tem_action.tem_tasks.sigma_x_fit.scene() 
        scene_y = self.control.tem_action.tem_tasks.sigma_y_fit.scene() 
        if scene:  
            scene.removeItem(self.control.tem_action.tem_tasks.ellipse_fit)
        if scene_x:
            scene_x.removeItem(self.control.tem_action.tem_tasks.sigma_x_fit)
        if scene_y: 
            scene_y.removeItem(self.control.tem_action.tem_tasks.sigma_y_fit)
        # Create the ellipse item with its bounding rectangle
        self.control.tem_action.tem_tasks.ellipse_fit = QGraphicsEllipseItem(QRectF(xo-0.5*width, yo-0.5*height, width, height))
        self.control.tem_action.tem_tasks.sigma_x_fit = QGraphicsRectItem(QRectF(xo-0.5*width, yo, width, 0))
        self.control.tem_action.tem_tasks.sigma_y_fit = QGraphicsRectItem(QRectF(xo, yo-0.5*height, 0, height))
        # First, translate the coordinate system to the center of the ellipse,
        # then rotate around this point and finally translate back to origin.
        rotationTransform = QTransform().translate(xo, yo).rotate(theta_deg).translate(-xo, -yo)
        # Create the symmetry (vertical flip) transform
        symmetryTransform = QTransform().translate(xo, yo).scale(1, -1).translate(-xo, -yo)
        # Combine the rotation and symmetry transforms
        combinedTransform = rotationTransform * symmetryTransform

        self.control.tem_action.tem_tasks.ellipse_fit.setPen(pg.mkPen('b', width=3))
        self.control.tem_action.tem_tasks.ellipse_fit.setTransform(combinedTransform)
        self.control.tem_action.parent.plot.addItem(self.control.tem_action.tem_tasks.ellipse_fit)

        self.control.tem_action.tem_tasks.sigma_x_fit.setPen(pg.mkPen('b', width=2))
        self.control.tem_action.tem_tasks.sigma_x_fit.setTransform(combinedTransform)
        self.control.tem_action.parent.plot.addItem(self.control.tem_action.tem_tasks.sigma_x_fit)

        self.control.tem_action.tem_tasks.sigma_y_fit.setPen(pg.mkPen('r', width=2))
        self.control.tem_action.tem_tasks.sigma_y_fit.setTransform(combinedTransform)
        self.control.tem_action.parent.plot.addItem(self.control.tem_action.tem_tasks.sigma_y_fit)
