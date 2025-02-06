from PySide6.QtWidgets import QPushButton

class ToggleButton(QPushButton):
    def __init__(self, label, window):
        super().__init__(label, window)
        self.started = False