#This file should be useable as a standalone module and not depend on the rest of the reuss package

import zmq
import logging
from rich import print

class ReceiverClient:
    """
    Client for the ReceiverServer
    Commands are sent in the form cmd_name:arg1,arg2,...
    
    """
    _default_timeout = 1000 #1s
    def __init__(self, host, port=5555, verbose = False):
        self.verbose = verbose
        self.host = host
        self.port = port
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REQ)

        self._set_default_timeout()

        """ **** Modified error handling **** """
        try:
            self.ping()
        except zmq.error.Again:
            raise TimeoutError(f"Could not connect to {host}:{port} - Operation timed out")
        
    def _set_default_timeout(self):
        self.socket.setsockopt(zmq.SNDTIMEO, ReceiverClient._default_timeout)
        self.socket.setsockopt(zmq.RCVTIMEO, ReceiverClient._default_timeout)

    def _set_unlimited_timeout(self):
        self.socket.setsockopt(zmq.SNDTIMEO, -1)
        self.socket.setsockopt(zmq.RCVTIMEO, -1)
    
    """ **** Modified method **** """
    def _send_message(self, message):
        # Ensure the socket is connected before sending messages
        self.socket.connect(f"tcp://{self.host}:{self.port}")
        if self.verbose:
            print(f'[spring_green4]Sending: {message}[/spring_green4]')
        try:
            # Send the message
            self.socket.send_string(message)
            # Attempt to receive the reply
            reply = self.socket.recv_string()
        except zmq.error.Again:
            # Handle the case where the reception times out
            raise TimeoutError("Response from server timed out")
        except zmq.ZMQError as e:
            # Handle other potential ZeroMQ errors
            raise ConnectionError(f"Communication error occurred: {e}")
        # Decode and process the reply
        status, message = self._decode_reply(reply)
        if self.verbose:
            print(f'[dark_orange3]Received: {status}:{message}[/dark_orange3]')
        
        return status, message
    
    def _decode_reply(self, reply):
        if ':' in reply:
            status, message = reply.split(':')
        else:
            status = reply
            message = None
        return status, message
    
    def collect_pedestal(self):

        self._set_unlimited_timeout()
        res =  self._send_message("collect_pedestal")
        self._set_default_timeout()
        return res
    
    def tune_pedestal(self):   
        self._set_unlimited_timeout()
        res = self._send_message("tune_pedestal")
        self._set_default_timeout()
        return res
    
    def ping(self):
        status, message  = self._send_message("ping")
        if status == "OK" and message == "pong":
            return True
        else:   
            raise ValueError(f"Unexpected reply: {status}:{message}")
        
    def start(self):
        status, message  = self._send_message("start")
        if status == "OK" and message == "started":
            return True
        else:   
            raise ValueError(f"Could not start data receiving: {status}:{message}")

    """ **** Modified method **** """
    def stop(self):
        try:
            status, message = self._send_message("stop")
            if status == "OK" and message == "stopped":
                return True
            else:
                raise ValueError(f"Could not stop data receiving: {status}:{message}")
        except zmq.error.Again as e:
            logging.error(f"Communication error - resource temporarily unavailable: {e}")
            raise TimeoutError("The stop command could not complete because the resource was temporarily unavailable.")
        except Exception as e:
            logging.error(f"An exception occurred while stopping: {e}")
            raise
        
    @property
    def frames_to_sum(self):
        status, message  = self._send_message("get_frames_to_sum")
        if status == "OK":
            return int(message)
        else:   
            raise ValueError(f"Could not get frames to sum: {status}:{message}")
        

    @frames_to_sum.setter
    def frames_to_sum(self, n):
        status, message  = self._send_message(f"set_frames_to_sum:{n}")
        if status == "OK" and message == str(n):
            return True
        else:   
            raise ValueError(f"Could not set frames to sum: {status}:{message}")
        
    @property
    def threshold(self):
        status, message  = self._send_message("get_threshold")
        if status == "OK":
            return float(message)
        else:   
            raise ValueError(f"Could not get threshold: {status}:{message}")
    
    @threshold.setter
    def threshold(self, th):
        status, message  = self._send_message(f"set_threshold:{th}")
        if status == "OK" and message == str(th):
            return True
        else:   
            raise ValueError(f"Could not set threshold: {status}:{message}")
        
    @property
    def commands(self):
        status, message  = self._send_message("get_commands")
        if status == "OK":
            return [cmd.strip("'") for cmd in message.strip('[]').split(', ')]
        else:   
            raise ValueError(f"Could not get commands: {status}:{message}")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("host", help="Host to connect to")
    parser.add_argument("-p", "--port", help="Port to connect to", type=int, default=5555)
    parser.add_argument("-v", "--verbose", help="Verbose output", action="store_true")
    args = parser.parse_args()
    c = ReceiverClient(args.host, port = args.port, verbose=args.verbose)