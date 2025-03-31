import logging
from PySide6.QtCore import QObject, Signal, Slot

class TemUpdateWorker(QObject):
    finished = Signal()
    status_updated = Signal(dict)
    
    def __init__(self, control_worker):
        super().__init__()
        self.control_worker = control_worker
        self.running = True
        self.task_name = "UI Updater"
    
    @Slot()
    def process_tem_info(self):
        """Process TEM info in a separate thread."""
        try:
            # Get the state without blocking UI
            results = self.control_worker.get_state_batched()
            
            # Emit results and finished signal
            self.status_updated.emit(results)
            self.finished.emit()
        except Exception as e:
            logging.error(f"Error in TemUpdateWorker: {e}")
            self.finished.emit()
    
    def stop(self):
        """Stop the worker."""
        self.running = False

    def __str__(self) -> str:
        return "UI Updater"