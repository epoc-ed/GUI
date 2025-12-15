
import numpy as np
from PySide6.QtWidgets import (QVBoxLayout, QWidget, QFrame, QPushButton, QApplication, QTableWidget, QHeaderView, QStyleOptionButton, QStyle)
from PySide6.QtGui import QKeySequence
from PySide6.QtCore import Qt, Signal, QRect

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


class CopyableTableWidget(QTableWidget):
    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Copy):
            self.copy_selection_to_clipboard()
        else:
            super().keyPressEvent(event)

    def copy_selection_to_clipboard(self):
        selected_ranges = self.selectedRanges()
        if not selected_ranges:
            return

        copied_text = ""
        for r in selected_ranges:
            for row in range(r.topRow(), r.bottomRow() + 1):
                row_data = []
                for col in range(r.leftColumn(), r.rightColumn() + 1):
                    item = self.item(row, col)
                    row_data.append(item.text() if item else "")
                copied_text += "\t".join(row_data) + "\n"

        QApplication.clipboard().setText(copied_text)


class CheckBoxHeader(QHeaderView):
    stateChanged = Signal(Qt.CheckState)  # Emit checkbox state (Qt.Checked, etc.)

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.isChecked = False
        self.setSectionsClickable(True)

    def paintSection(self, painter, rect, logicalIndex):
        super().paintSection(painter, rect, logicalIndex)

        if logicalIndex == 0:  # First column only
            option = QStyleOptionButton()
            option.rect = QRect(
                rect.x() + (rect.width() - 20) // 2,  # center horizontally
                rect.y() + (rect.height() - 20) // 2, # center vertically
                20,
                20
            )
            option.state = QStyle.State_Enabled | (
                QStyle.State_On if self.isChecked else QStyle.State_Off
            )
            self.style().drawControl(QStyle.CE_CheckBox, option, painter)

    def mousePressEvent(self, event):
        index = self.logicalIndexAt(event.pos())
        if index == 0:  # First column
            self.isChecked = not self.isChecked
            self.stateChanged.emit(Qt.Checked if self.isChecked else Qt.Unchecked)
            self.updateSection(0)
        super().mousePressEvent(event)