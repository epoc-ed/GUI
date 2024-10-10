import zmq
import time
from datetime import datetime
from rich.console import Console

from reuss import SummingReceiver
import reuss 
import threading
import numpy as np

class ReceiverServer:
    _commands = ['collect_pedestal',
                 'get_commands',
                 'tune_pedestal',
                 'ping', 
                 'start', 
                 'stop', 
                 'set_frames_to_sum', 
                 'get_frames_to_sum',
                 'get_threshold',
                 'set_threshold']

    def __init__(self, port=5555, threads = 8):
        self.console = Console()
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REP)
        self.thread_count = threads
        endpoint = f"tcp://*:{port}"
        print(f"[blue]Receiver binding to {endpoint}, thread_count: {self.thread_count}[/blue] ")
        self.socket.bind(endpoint)

        #TODO! Assumes detector software is running on the same machine 
        #refactor to read udp sources from redis
        self.receiver = SummingReceiver(self.thread_count)

    def _now(self):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def _decode(self, message):
        """
        Decode the message into a command and arguments
        """
        if ':' in message:
            cmd, args = message.split(':')
            if ',' in args:
                args = args.split(',')
            else:
                args = [args]
        else:
            cmd = message
            args = []
        
        return cmd, args
    
    def _has_function(self, cmd):
        return cmd in self._commands
    
    def collect_pedestal(self):
        self.receiver.record_pedestal(1) 
        return "OK:Pedestal collected"
    
    def tune_pedestal(self):
        self.receiver.record_pedestal(2) 
        return "OK:Pedestal tuned"
    
    def ping(self):
        return "OK:pong"
    
    def start(self):
        self.receiver.start()
        return "OK:started"
    
    def stop(self):
        self.receiver.stop()
        return "OK:stopped"
    
    def  set_frames_to_sum(self, n):
        n = int(n)
        self.receiver.set_frames_to_sum(n)
        return f"OK:{n}"
    
    def get_frames_to_sum(self):
        return f"OK:{self.receiver.get_frames_to_sum()}"
    
    def get_commands(self):
        return f"OK:{self._commands}"
    
    def set_threshold(self, th):
        th = float(th)
        self.receiver.set_threshold(th)
        return f"OK:{th}"
    
    def get_threshold(self):
        return f"OK:{self.receiver.get_threshold()}"

    def run(self):
        while True:
            #  Wait for next request from client
            message = self.socket.recv_string()
            self.console.print(f"[gold3]{self._now()}[/gold3] [black]- Received request: [bold]{message}[/bold][/black]", highlight=False)

            # Decode the message into a command and arguments
            cmd, args = self._decode(message)
            self.console.print(f'[gold3]{self._now()}[/gold3] - [black]Decoded to: {cmd}, {args}[/black]', highlight=False)

            #If the command was not found return an error
            if not self._has_function(cmd):
                self.socket.send_string("ERROR:Unknown command")
                continue
 
            #Call the right function with the arguments
            res = getattr(self, cmd)(*args)
            
            #Reply to the client
            self.console.print(f"[gold3]{self._now()}[/gold3] - [black]Sending reply: [bold]{res}[/bold][/black]", highlight=False)
            self.socket.send_string(res)

if __name__ == '__main__':
    import os
    os.environ['PYTHONINSPECT'] = 'TRUE'

    # Copied from srecv
    cal = reuss.load_calibration()
    #cal = np.ones((3, 512, 1024), dtype=np.float32)
    try:
        pd = np.fromfile("/dev/shm/reuss/pedestal.bin", dtype=np.float32).reshape(3, 512, 1024)
    except:
        print("No pedestal found, using zeros")
        pd = np.zeros((3, 512, 1024), dtype=np.float32)

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--threads", "-t", default=8, type = int)
    args = parser.parse_args()
    r = ReceiverServer(threads=args.threads)

    r.set_frames_to_sum(100)
    # at 1kHz, sum 50 frames
    # r.set_frames_to_sum(50)
    # threshold slightly above 0 should reduce noise
    r.set_threshold(5)

    r.receiver.set_pedestal(pd)
    r.receiver.set_calibration(cal)

    server_thread = threading.Thread(target=r.run, daemon=True)
    server_thread.start()

