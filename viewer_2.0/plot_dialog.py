import pyqtgraph as pg
from collections import deque
from PySide6.QtWidgets import QPushButton, QVBoxLayout, QDialog
from PySide6.QtCore import QTime


class PlotDialog(QDialog):
    def __init__(self, parent=None):
        super(PlotDialog, self).__init__(parent)
        self.setWindowTitle('Fitting \u03C3 over Time')
        self.setGeometry(800, 250, 700, 600)
        self.layout = QVBoxLayout()
        # Upper plot of Sigma_x = f(t)
        self.plotWidget1 = pg.PlotWidget()
        self.plotWidget1.setTitle('<span style="font-size: 12pt">σ<sub>x</sub> = f(Time)</span>',) 
        self.plotWidget1.setLabel('bottom', 'Time', units='s')  
        self.plotWidget1.setLabel('left', 'σ<sub>x</sub>', units='pixels')
        self.plotWidget1.setYRange(0,10)
        self.layout.addWidget(self.plotWidget1)
        # Bottom plot of Sigma_y = f(t)
        self.plotWidget2 = pg.PlotWidget()
        self.plotWidget2.setTitle('<span style="font-size: 12pt">σ<sub>y</sub> = f(Time)</span>',)
        self.plotWidget2.setLabel('bottom', 'Time', units='s')  
        self.plotWidget2.setLabel('left', 'σ<sub>y</sub>', units='pixels')
        self.plotWidget2.setYRange(0,10)
        self.layout.addWidget(self.plotWidget2)
        # Quit button to close the window
        quit_buton = QPushButton("Quit", self)
        quit_buton.clicked.connect(self.close_window)
        self.layout.addWidget(quit_buton)
        self.setLayout(self.layout)

        self.timeElapsed = QTime()
        self.dataX = deque() # Time
        self.dataY1 = deque() # Sigma_x values
        self.dataY2 = deque() # Sigma_y values

    def close_window(self):
        self.close()

    def startPlotting(self, initialValue_x, initialValue_y):                
        self.dataX.append(0)  # Reset time
        self.dataY1.append(initialValue_x)  # Reset sigma_x values
        self.dataY2.append(initialValue_y)  # Reset sigma_y values
        self.timeElapsed = QTime.currentTime() # Start the timer
        # self.updatePlot(initialValue_x, initialValue_y)

    def updatePlot(self, newValue_x, newValue_y, width_max = 60):
        elapsed = self.timeElapsed.msecsTo(QTime.currentTime()) / 1000.0  # Convert milliseconds to seconds
        if elapsed > width_max:  # Shift time window
            # Keep the plot window fixed at a 60-second width
            self.dataX.append(elapsed)
            self.dataY1.append(newValue_x)
            self.dataY2.append(newValue_y)
            self.dataX.popleft() # O(1) 
            self.dataY1.popleft() # O(1) 
            self.dataY2.popleft() # O(1)
        else:
            self.dataX.append(elapsed)
            self.dataY1.append(newValue_x)
            self.dataY2.append(newValue_y)

        self.plotWidget1.clear()
        self.plotWidget2.clear()
        self.plotWidget1.plot(self.dataX, self.dataY1, symbol='o', symbolBrush='b')
        self.plotWidget2.plot(self.dataX, self.dataY2, symbol='d', symbolBrush='r')
