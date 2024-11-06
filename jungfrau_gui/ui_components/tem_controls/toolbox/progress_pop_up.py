from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar

class ProgressPopup(QDialog):
    def __init__(self, title="Progress", message="Please wait...", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)  # Make it modal to block interaction with the main window

        # Set up layout and widgets
        layout = QVBoxLayout()
        self.label = QLabel(message)
        layout.addWidget(self.label)
        
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)

        self.setLayout(layout)
        self.progress_value = 0

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def close_on_complete(self):
        self.accept()  # Close the dialog when progress reaches 100%