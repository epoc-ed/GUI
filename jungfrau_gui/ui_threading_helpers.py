import logging

def move_worker_to_thread(thread, worker):
    worker.moveToThread(thread)
    logging.info(f"{worker.task_name} is Ready!")
    thread.started.connect(worker.run) 

def disconnect_worker_signals(worker):
    if worker:
        try:
            # Attempt to disconnect the 'finished' signal from the worker
            worker.finished.disconnect()
            logging.info(f"Disconnected finished signal for task: {worker.task_name}")
        except TypeError:
            # This exception is usually raised if the signal was already disconnected or not connected
            logging.warning(f"Finished signal was already disconnected for task: {worker.task_name}")
        except Exception as e:
            # Catch any other unexpected exceptions
            logging.warning(f"Could not disconnect finished signal: {e}")

def terminate_thread(task_thread):
    if task_thread:
        logging.info("Terminating thread...")
        task_thread.quit()
        task_thread.wait()

def remove_worker_thread_pair(threadWorkerPairs, task_thread):
    index_to_delete = None
    for i, (t, worker) in enumerate(threadWorkerPairs):
        if t == task_thread:
            if worker is not None:
                logging.info(f"Deleting task: {worker.task_name}")
                worker.deleteLater()  # Schedule the worker for deletion
                logging.info(f"{worker.task_name} successfully stopped!")
            index_to_delete = i
            break  # Only one instance of a thread/worker pair

    if index_to_delete is not None:
        del threadWorkerPairs[index_to_delete]

def reset_worker_and_thread(worker, task_thread):
    if task_thread:
        task_thread.deleteLater()  # Schedule the thread for deletion

    worker = None
    task_thread = None
    logging.info("Task and thread reset to None.")
