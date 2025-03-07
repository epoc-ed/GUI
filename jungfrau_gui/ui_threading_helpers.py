import logging
from PySide6.QtCore import QCoreApplication
from jungfrau_gui.ui_components.tem_controls.task.record_task import RecordTask
from jungfrau_gui.ui_components.tem_controls.task.get_teminfo_task import GetInfoTask
# from jungfrau_gui.ui_components.tem_controls.task.beam_focus_task import AutoFocusTask
from jungfrau_gui.ui_components.tem_controls.task.beam_focus_task_test import AutoFocusTask

def move_worker_to_thread(thread, worker):
    worker.moveToThread(thread)
    logging.info(f"\033[1m{worker.task_name}\033[0m\033[34m is Ready!")
    thread.started.connect(worker.run) 

def handle_tem_task_cleanup(control_worker):
    control_worker.handle_task_cleanup()

def disconnect_worker_signals(worker):
    if worker is None:  # Just check if the worker is None
        logging.warning(f"Worker {getattr(worker, 'task_name', 'unknown')} is already deleted.")
        return 
       
    try:
        # Attempt to disconnect the 'finished' signal from the worker
        worker.finished.disconnect()
        logging.info(f"Disconnected finished signal for task: \033[1m{worker.task_name}")
    except TypeError:
        # This exception is usually raised if the signal was already disconnected or not connected
        logging.error(f"Finished signal was already disconnected for task: {worker.task_name}")
    except Exception as e:
        # Catch any other unexpected exceptions
        logging.error(f"Could not disconnect finished signal: {e}")

def terminate_thread(task_thread):
    if task_thread is not None:
        if task_thread.isRunning():
            logging.info("Terminating thread...")
            task_thread.quit()
            task_thread.wait()

def remove_worker_thread_pair(threadWorkerPairs, task_thread):
    index_to_delete = None
    for i, (t, worker) in enumerate(threadWorkerPairs):
        if t == task_thread:
            if worker is not None:
                logging.info(f"Deleting task: \033[1m{worker.task_name}")
                worker.deleteLater()  # Schedule the worker for deletion
                logging.info(f"\033[1m{worker.task_name}\033[0m\033[34m successfully ended!")
            index_to_delete = i
            break  # Only one instance of a thread/worker pair

    if index_to_delete is not None:
        del threadWorkerPairs[index_to_delete]

def reset_worker_and_thread(worker, task_thread):
    if task_thread:
        task_thread.deleteLater()  # Schedule the thread for deletion

    logging.info(f"Task {worker.task_name} and its thread were reset to None.")
    return None, None
