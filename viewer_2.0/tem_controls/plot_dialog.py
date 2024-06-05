import pyqtgraph as pg
from collections import deque
from PySide6.QtWidgets import QPushButton, QVBoxLayout, QDialog
from PySide6.QtCore import QTime

import palette


class PlotDialog(QDialog):
    def __init__(self, parent=None):
        super(PlotDialog, self).__init__(parent)
        win_pal = palette.get_palette("dark")
        self.setPalette(win_pal)
        self.setWindowTitle('Fitting \u03C3 over Time')
        self.setGeometry(800, 250, 800, 700)
        self.layout = QVBoxLayout()
        # Upper plot of Gaussian height = f(t)
        self.plotWidget0 = pg.PlotWidget()
        self.plotWidget0.setLabel('bottom', '<span style="font-size: 13pt">Time</span>', units='s')  
        self.plotWidget0.setLabel('left', '<span style="font-size: 12pt">Amplitude</span>')
        self.layout.addWidget(self.plotWidget0)
        # Middle plot of Sigma_x and Sigma_y = f(t)
        self.plotWidget1 = pg.PlotWidget()
        self.plotWidget1.setLabel('bottom', '<span style="font-size: 13pt">Time</span>', units='s')  
        self.plotWidget1.setLabel('left', '<span style="font-size: 13pt">σ</span>', units='<span style="font-size: 13pt">pixels</span>')
        self.plotWidget1.setYRange(0,12)
        self.layout.addWidget(self.plotWidget1)
        # Bottom plot of Sigma_x/Sigma_y = f(t)
        self.plotWidget2 = pg.PlotWidget()
        self.plotWidget2.setLabel('bottom', '<span style="font-size: 13pt">Time</span>', units='s')  
        self.plotWidget2.setLabel('left', '<span style="font-size: 13pt"> σ<sub>x</sub>/σ<sub>y</sub> </span>')
        self.plotWidget2.setYRange(0,2)
        self.layout.addWidget(self.plotWidget2)
        # Legend
        self.legend = self.plotWidget1.addLegend()
        self.legend.anchor(itemPos=(1,0), parentPos=(1,0), offset=(-5,5))
        # Quit button to close the window
        quit_buton = QPushButton("Quit", self)
        quit_buton.clicked.connect(self.close_window)
        self.layout.addWidget(quit_buton)
        self.setLayout(self.layout)

        self.timeElapsed = QTime()
        self.dataX = deque() # Time
        self.dataY0 = deque() # Amplitude values
        self.dataY1 = deque() # Sigma_x values
        self.dataY2 = deque() # Sigma_y values
        self.dataY3 = deque() # Sigma_x/Sigma_y values

    def close_window(self):
        self.close()

    def startPlotting(self, initialValue_H, initialValue_x, initialValue_y):                
        self.dataX.append(0)  # Reset time
        self.dataY0.append(initialValue_H)  # Reset Gaussian Height values
        self.dataY1.append(initialValue_x)  # Reset sigma_x values
        self.dataY2.append(initialValue_y)  # Reset sigma_y values
        self.dataY3.append(initialValue_x/initialValue_y)
        self.timeElapsed = QTime.currentTime() # Start the timer
        # self.updatePlot(initialValue_x, initialValue_y)

    def updatePlot(self, newValue_H, newValue_x, newValue_y, width_max = 60):
        elapsed = self.timeElapsed.msecsTo(QTime.currentTime()) / 1000.0  # Convert milliseconds to seconds
        if elapsed > width_max:  # Shift time window
            # Keep the plot window fixed at a 60-second width
            self.dataX.append(elapsed)
            self.dataY0.append(newValue_H)
            # self.plotWidget0.setYRange(0.1*newValue_H,5*newValue_H)
            self.dataY1.append(newValue_x)
            self.dataY2.append(newValue_y)
            self.dataY3.append(newValue_x/newValue_y)
            self.dataX.popleft() # O(1) 
            self.dataY0.popleft()
            self.dataY1.popleft() # O(1) 
            self.dataY2.popleft() # O(1)
            self.dataY3.popleft()
        else:
            self.dataX.append(elapsed)
            self.dataY0.append(newValue_H)
            # self.plotWidget0.setYRange(0.1*newValue_H,5*newValue_H)
            self.dataY1.append(newValue_x)
            self.dataY2.append(newValue_y)
            self.dataY3.append(newValue_x/newValue_y)
        
        self.plotWidget0.setTitle(f'<span style="font-size: 16pt">Gaussian Height = {newValue_H:12.4f}</span>',)
        
        self.plotWidget1.setTitle(f'<span style="font-size: 16pt">σ<sub>x</sub> = {newValue_x:12.4f}   \
                                        σ<sub>y</sub> = {newValue_y:12.4f} </span>',) 
        
        self.plotWidget2.setTitle(f'<span style="font-size: 16pt">σ<sub>x</sub>/σ<sub>y</sub> = {(newValue_x/newValue_y):12.4f}</span>',)

        self.plotWidget0.clear()
        self.plotWidget1.clear()
        self.plotWidget2.clear()

        self.plotWidget0.plot(self.dataX, self.dataY0,
                              pen=pg.mkPen(color='w', width=2),
                              symbol='x', symbolBrush='w')
        self.plotWidget1.plot(self.dataX, self.dataY1, 
                              pen=pg.mkPen(color='b', width=2),
                              symbol='o', symbolBrush='b', 
                              name='<span style="font-size: 12pt">σ<sub>x</sub></span>')
        self.plotWidget1.plot(self.dataX, self.dataY2,
                              pen=pg.mkPen(color='r', width=2),
                              symbol='d', symbolBrush='r', 
                              name='<span style="font-size: 12pt">σ<sub>y</sub></span>')
        self.plotWidget2.plot(self.dataX, self.dataY3,
                              pen=pg.mkPen(color='g', width=2),
                              symbol='star', symbolBrush='g')
