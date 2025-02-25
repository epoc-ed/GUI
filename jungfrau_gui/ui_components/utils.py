
import numpy as np
from PySide6.QtWidgets import (QVBoxLayout, QWidget, QFrame)

def create_gaussian(amplitude, size_x, size_y, sigma_x, sigma_y, theta):
    """
    Create a 2D Gaussian distribution tilted by an angle theta.
    
    Parameters:
    size_x (int): Width of the array
    size_y (int): Height of the array
    sigma_x (float): Standard deviation in the x direction
    sigma_y (float): Standard deviation in the y direction
    theta (float): Angle of rotation in radians
    
    Returns:
    np.array: 2D array representing the Gaussian distribution
    """
    x = np.linspace(-size_x//2, size_x//2, size_x)
    y = np.linspace(-size_y//2, size_y//2, size_y)
    x, y = np.meshgrid(x, y)
    
    a = (np.cos(theta)**2)/(2*sigma_x**2) + (np.sin(theta)**2)/(2*sigma_y**2)
    b = -(np.sin(2*theta))/(4*sigma_x**2) + (np.sin(2*theta))/(4*sigma_y**2)
    c = (np.sin(theta)**2)/(2*sigma_x**2) + (np.cos(theta)**2)/(2*sigma_y**2)
    
    gaussian = amplitude * np.exp(-(a*x**2 + 2*b*x*y + c*y**2))
    return gaussian.astype(np.float32)

def create_horizontal_line_with_margin(margin=10):
    line_widget = QWidget()
    layout = QVBoxLayout(line_widget)
    layout.setContentsMargins(0, margin, 0, 0)  # Add margin below the line
    layout.setSpacing(0)  # No spacing between the line and the margin

    h_line = QFrame()
    h_line.setFrameShape(QFrame.HLine)
    h_line.setFrameShadow(QFrame.Plain)
    h_line.setStyleSheet("""QFrame {border: none; border-top: 1px solid grey;}""")

    layout.addWidget(h_line)
    
    return line_widget