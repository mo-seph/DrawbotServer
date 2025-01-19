import subprocess
import serial
#from drawbot_server import executor
import re
import fcntl
import sys
import time
from datetime import datetime
from typing import Optional
class StateListener:
    def set_state(self,state:str):
        pass
    def set_progress(self,progress:float):
        pass
    def set_estimated_end_time(self,end_time:Optional[datetime]):
        pass
    def set_image_url(self,image_url:str):
        pass

class DrawbotControl:
    def __init__(self, serialport='/dev/ttyACM0', timeout=120, baud='57600', verbose=True, fake=False, fake_delay=0.1):
        self.serialport = serialport
        self.timeout = timeout
        self.baud = baud    
        self.verbose = verbose
        self.fake = fake
        self.proportion = 1.0
        self.state_listeners = []
        self.fake_delay = fake_delay

    def add_state_listener(self,listener:StateListener):
        self.state_listeners.append(listener)
    
    def send_state(self,state:str):
        for listener in self.state_listeners:
            listener.set_state(state)

    def send_progress(self,progress:float):
        for listener in self.state_listeners:
            listener.set_progress(progress)

    def send_estimated_end_time(self,end_time:datetime):
        for listener in self.state_listeners:
            listener.set_estimated_end_time(end_time)

    def start_serial(self):
        if self.fake:
            print("Startingfake serial")
            return
        try:
            print(f"Starting real serial on {self.serialport}")
            self.serial_port=serial.Serial()
            self.serial_port.port=self.serialport
            self.serial_port.timeout=self.timeout
            self.serial_port.writeTimeout = self.timeout
            self.serial_port.baudrate=self.baud
            self.serial_port.open()
            print("serial opened")
        except IOError as e:
            print("robot not connected?", e)
            raise e

    def finish_serial(self):
        if self.fake:
            print("Finishing fake serial")
            return
        try:
            if self.verbose:
                print("closing serial")
            self.serial_port.close()
            self.serial_port = None
        except IOError as e:
            print("robot not connected?", e)
            raise e

    def send_drawbot_commands(self, commands:list[str],cancel_event=None):
        if self.verbose:
            print(f"Sending {len(commands)} commands")
        self.start_serial()
        comment_match = re.compile("^#")
        response = ""
        num_commands = len(commands)
        last_proportion = 0
        last_update = time.time()
        start_time = time.time()
        self.send_progress(last_proportion)
        for i, line in enumerate(commands):
            if self.verbose:
                print(f"Sending command {i} of {num_commands}: {line} ({self.proportion})")
            if cancel_event and cancel_event.is_set():
                self.serial_port.write("d0")
                print("Cancel event set, stopping execution and raising pen")
                break
            self.proportion = i / num_commands
            # if there's a significant difference and it's been more than 10 seconds since the last update:
            if abs(self.proportion - last_proportion) > 0.01 and time.time() - last_update > 10:
                # Round to the nearest 0.01
                self.send_progress(round(self.proportion*100, 0))
                last_proportion = self.proportion
                last_update = time.time()
                # Estimate the end time/date    
                time_remaining = (time.time() - start_time) * (1 - self.proportion) / self.proportion
                end_time = time.time() + time_remaining
                print(f"Estimated end date/time: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
                self.send_estimated_end_time(end_time)

                
            if comment_match.match(line):
                print(f"skipping line: {line}")  # Use f-string
            elif line is not None:
                # Encode string to bytes before sending
                if self.fake:
                    print(f"Fake send -> {line}")
                    time.sleep(self.fake_delay)
                else:
                    if self.verbose:
                        print(f"-> {line}")  # Use f-string and end=''
                    self.serial_port.write(str(line).encode('utf-8'))
                response += self.read_serial_response()
        self.finish_serial()
        self.send_estimated_end_time(None)
        self.send_progress(100)
        self.send_state("idle")
        if self.verbose:
            print(f"Finished sending {len(commands)} commands")
        return response        #command = f"./drawbot {command}"
        #process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    """
    this requires the robot to respond in the expected way, where all responsed end with "ok"
    """
    def read_serial_response(self):
        if self.fake:
            return "fake ok"
        response = ""
        all_lines = ""
        # Replace string.find with in operator
        while "ok" not in response:
            response = self.serial_port.readline().decode('utf-8')  # Add decode for bytes to str
            if response == "":
                print("timeout on serial read", file=sys.stderr)
                self.serial_port.close()
                raise IOError("Serial timeout")  # Raise instead of exit
            if self.verbose:
                print(f"<- {response}", end='')  # Use f-string and end=''
            all_lines += response
        return all_lines

    def get_lock():
        file = "/tmp/feed.lock"
        fd = open(file,'w')
        try:
            fcntl.lockf(fd,fcntl.LOCK_EX | fcntl.LOCK_NB)
        except IOError:
            print(f"another process is running with lock. quitting! {file}", file=sys.stderr)
            raise   

    def pen_up(self,cancel_event=None):
        return self.send_drawbot_commands(["d0"],cancel_event)

    def pen_down(self,cancel_event=None):
        return self.send_drawbot_commands(["d1"],cancel_event)

    def calibrate(self,cancel_event=None):
        self.send_state("calibrating")
        output = self.send_drawbot_commands(["c"],cancel_event)
        self.send_state("idle")
        return output

    def draw_file(self, filepath:str,cancel_event=None):
        self.send_state(f"drawing {filepath}")
        print(f"draw_file: {filepath}")
        gcode = ["d0"] + self.readFile(filepath) + ["d0"] + ["g380,250"]
        output = self.send_drawbot_commands(gcode,cancel_event)
        print("Finished draw_file")
        self.send_state("idle")
        return output

    def home(self,cancel_event=None):
        self.send_state("homing")
        output = self.send_drawbot_commands(["g380,250"],cancel_event)
        self.send_state("idle")
        return output

    def readFile(self, filepath:str):
        gcode = open(filepath)
        gcodes = gcode.readlines()
        return gcodes


