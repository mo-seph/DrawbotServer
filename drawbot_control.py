import subprocess
import serial
#from drawbot_server import executor
import re
import fcntl
import sys
import time



class DrawbotControl:
    def __init__(self, serialport='/dev/ttyACM0', timeout=1, baud='57600', verbose=True, fake=False):
        self.serialport = serialport
        self.timeout = timeout
        self.baud = baud    
        self.verbose = verbose
        self.fake = fake
        self.proportion = 1.0

    def start_serial(self):
        if self.fake:
            print("Startingfake serial")
            return
        try:
            self.serial_port=serial.Serial()
            self.serial_port.port=self.serialport
            self.serial_port.timeout=self.timeout
            self.serial_port.writeTimeout = self.timeout
            self.serial_port.baudrate=self.baud
            self.serial_port.open()
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
        self.start_serial()
        comment_match = re.compile("^#")
        response = ""
        num_commands = len(commands)
        for i, line in enumerate(commands):
            if cancel_event and cancel_event.is_set():
                self.serial_port.write("d0")
                print("Cancel event set, stopping execution and raising pen")
                break
            self.proportion = i / num_commands
            if comment_match.match(line):
                print(f"skipping line: {line}")  # Use f-string
            elif line is not None:
                # Encode string to bytes before sending
                if self.fake:
                    print(f"Fake send -> {line}")
                    time.sleep(1)
                else:
                    if self.verbose:
                        print(f"-> {line}", end='')  # Use f-string and end=''
                    self.serial_port.write(str(line))
                response += self.read_serial_response()
        self.finish_serial()
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
        return self.send_drawbot_commands(["c"],cancel_event)

    def draw_file(self, filepath:str,cancel_event=None):
        print(f"draw_file: {filepath}")
        gcode = ["d0"] + self.readFile(filepath) + ["d0"] + ["g380,250"]
        output = self.send_drawbot_commands(gcode,cancel_event)
        print("Finished draw_file")
        return output

    def home(self,cancel_event=None):
        return self.send_drawbot_commands(["g380,250"],cancel_event)

    def readFile(self, filepath:str):
        gcode = open(filepath)
        gcodes = gcode.readlines()
        return gcodes


