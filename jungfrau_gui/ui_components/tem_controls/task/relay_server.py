import json
import queue
import socket
# import threading
import timeit
import time
from threading import Thread
from PyJEM.offline import TEM3
# import io
# import sys

BUFFER_SIZE = 1024
INFO_UPDATE_TIME_SECS = 0.5

ht = TEM3.HT3()
apt = TEM3.Apt3()
stage = TEM3.Stage3()
eos = TEM3.EOS3()
defl = TEM3.Def3()
lens = TEM3.Lens3()
# detector = TEM3.Detector3() # can be used with JF?
info = {}
conn_open = False

def main():
    # Create a TCP server
    sock = socket.socket()
    host = "0.0.0.0"
    port = 12345
    print("Listening to ", host + ":" + str(port))
    sock.settimeout(30) # timeout command #
    sock.bind((host, port))
    sock.listen(5)

# main loop
    while True:
        global conn_open
        global info
        connection, address = sock.accept()
        print("Got connection from", address)
        conn_open = True

        # Create an event queue that holds incoming messages and other tasks
        q = queue.Queue()
        
        receiving_thread = Thread(target=start_receiving, args=(connection, q))
        receiving_thread.start()

        info_thread = Thread(target=start_info_gathering, args=(q, None))
        info_thread.start()
 
        while True:
            task = q.get()
            if task == "#quit":
                print("disconnected.")
                break
            elif "#info" in task or task == "#more":
                # info = get_state()
                if task == "#more":
                    info = get_state_detailed()
                try:
                    # print("------------------------")
                    # print(info)
                    connection.send(json.dumps(info).encode())
                except ConnectionResetError:
                    print("The connection was forcibly closed when sending.")
                    break
            else:
                try:
                    # buffer = io.StringIO()
                    # sys.stdout = buffer
                    # exec(task)
                    # sys.stdout = sys.__stdout__
                    # result = buffer.getvalue()
                    result = str(exec(task)) # result = str(eval(task))
                    print(task, "-->", result)
                    ##
                    # if len(result) != 0 and result != "None":
                    #     connection.send(result.encode())
                    ##
                    # else:
                    #     print(task, "-->", None)
                except Exception as exc:
                    print("Exception when receiving {:}: {:}".format(task, exc))

        # wait for the receiving thread to finish and close the connection
        receiving_thread.join()
        conn_open = False
        connection.close()
        break

def start_receiving(connection, q):
    while True:
        try:
            data = connection.recv(BUFFER_SIZE)
            if data:
                q.put(data.decode())
            else:
                q.put("#quit")
                break
        except ConnectionResetError:
            print("The connection was forcibly closed when receiving.")
            q.put("#quit")
            break

def start_info_gathering(q, x):
    global conn_open
    global info
    while conn_open:
        for query in INFO_QUERIES:
            result = {}
            result["tst_before"] = time.time()
            result["val"] = eval(query + "()")
            result["tst_after"] = time.time()
            info[query] = result
        if not conn_open:
            break
        time.sleep(INFO_UPDATE_TIME_SECS) # too short value (0.2) brought errors in test env.???
        q.put("#info")


def get_state():
    results = {}
    timeit.timeit()

    for query in INFO_QUERIES:
        tic = time.perf_counter()
        results[query] = eval(query + "()")
        toc = time.perf_counter()
        # print("Getting info for", query, "Took", toc - tic, "seconds")

    return results

def get_state_detailed():
    results = {}
    for query in MORE_QUERIES:
        if 'defl' in query: time.sleep(0.1)
        command = query
        if not 'apt.GetSize' in query:
            command = query + "()"
        result = {}
        result["tst_before"] = time.time()
        # result["val"] = eval(query + "()")
        result["val"] = eval(command)
        result["tst_after"] = time.time()
        results[query] = result
    return results


INFO_QUERIES = ["stage.GetPos", "stage.Getf1OverRateTxNum", "stage.GetStatus", "eos.GetMagValue", "eos.GetFunctionMode"]
# INFO_QUERIES = ["stage.GetPos", "stage.GetStatus", "eos.GetMagValue", "eos.GetFunctionMode"] # for test env.
MORE_QUERIES = ["stage.GetPos", "stage.GetStatus", "eos.GetMagValue", "eos.GetFunctionMode",
                "apt.GetSize(1)", "apt.GetSize(4)", # 1=CL, 4=SA
                "eos.GetSpotSize", "eos.GetAlpha", 
                "lens.GetCL3", "lens.GetIL1", "lens.GetOLf", # OLf = defocus(fine)
                "defl.GetILs", "defl.GetPLA", "defl.GetBeamBlank"] # for in detail
INIT_QUERIES = ["ht.GetHtValue", "stage.Getf1OverRateTxNum"]

if __name__ == "__main__":
    main()
