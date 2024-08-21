
import logging
import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsRectItem
from PySide6.QtCore import QRectF

# from reuss import config as cfg
from epoc import ConfigurationClient, auth_token, redis_host


def draw_overlay(image_item):
    cfg = ConfigurationClient(redis_host(), token=auth_token())
    for shape in cfg.overlays:
        if shape['type'] == 'circle':
            x, y = shape['xy']
            r = shape['radius']
            item = QGraphicsEllipseItem(QRectF(x-r, y-r, 2*r, 2*r))
        elif shape['type'] == 'rectangle':
            x, y = shape['xy']
            w = shape['width']
            h = shape['height']
            item = QGraphicsRectItem(QRectF(x, y, w, h))
        else:
            raise ValueError("Only circle or rectangle is currently supported")
        
        item.setPen(pg.mkPen('r', width=2))
        image_item.addItem(item)

if __name__ == "__main__":
    format = "%(message)s"
    logging.basicConfig(format=format, level=logging.INFO)

    app = pg.mkQApp()  # Ensure that a QApplication exists
    
    plotWidget = pg.PlotWidget()
    image_item = pg.ImageItem()
    plotWidget.addItem(image_item)

    # Create a sample image to display
    cfg = ConfigurationClient(redis_host(), token=auth_token())
    image = np.random.rand(cfg.nrows, cfg.ncols)

    image_item.setImage(image.T)
    draw_overlay(plotWidget)
    plotWidget.show()

    pg.exec()  # Start the Qt event loop
