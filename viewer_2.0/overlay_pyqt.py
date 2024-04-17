import json
import logging
import numpy as np
import pyqtgraph as pg
from reuss import config as cfg
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsRectItem
from PySide6.QtCore import QRectF

def draw_overlay(image_item):
    for key, value in cfg.parser['overlay'].items():
        s = json.loads(value)
        logging.debug(key," = ", s)
        if 'circle' in key:
            x, y = s['xy']
            r = s['radius']
            # QGraphicsEllipseItem takes QRectF as argument, which defines the bounding rectangle.
            # QRectF(x, y, width, height)
            item = QGraphicsEllipseItem(QRectF(x-r, y-r, 2*r, 2*r))
        elif 'rectangle' in key:
            x, y = s['xy']
            w = s['width']
            h = s['height']
            item = QGraphicsRectItem(QRectF(x, y, w, h))
        else:
            raise ValueError("Only circle or rectangle is currently supported")
        
        item.setPen(pg.mkPen('r', width=2))

        image_item.addItem(item)

if __name__ == "__main__":
    format = "%(message)s"
    logging.basicConfig(format=format, level=logging.DEBUG)

    app = pg.mkQApp()  # Ensure that a QApplication exists
    
    plotWidget = pg.PlotWidget()
    image_item = pg.ImageItem()
    plotWidget.addItem(image_item)

    # Create a sample image to display
    image = np.random.rand(cfg.nrows(), cfg.ncols())

    image_item.setImage(image.T)
    draw_overlay(plotWidget)
    plotWidget.show()

    pg.exec()  # Start the Qt event loop
