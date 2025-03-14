import subprocess
import serial
from PIL import Image, ImageDraw
import os
#from drawbot_server import executor
from drawbot_server import BotSetup
import re
import fcntl
import sys
import time
from datetime import datetime
from typing import Optional, Protocol, List, abstractmethod
from abc import ABC


class StateListener:
    def set_state(self,state:str):
        pass
    def set_progress(self,progress:float,done:int,total:int):
        pass
    def set_estimated_time_left(self,time_left:float):
        pass
    def set_target_image(self,image_path:str):
        pass

class DrawbotOutput(ABC):
    """Base class for drawbot output implementations"""
    
    def start_block(self):
        """Initialize the output connection"""
        pass
    
    def finish_block(self):
        """Clean up the output connection"""
        pass
    
    def write_command(self, command: str) -> str:
        """Write a command and return the response"""
        pass

    def start_file(self, filepath: str, setup: BotSetup):
        """Called when starting to process a new file
        
        Args:
            filepath: The path of the file to be processed
            setup: The BotSetup configuration for this file
        """
        pass

    def end_file(self, filepath: str, success: bool):
        """Called when finished processing a file
        
        Args:
            filepath: The path of the file that was processed
            success: Whether the file processing completed successfully
        """
        pass


class SerialDrawbotOutput(DrawbotOutput):
    def __init__(self, serialport='/dev/ttyACM0', timeout=120, baud='57600', verbose=True):
        self.serialport = serialport
        self.timeout = timeout
        self.baud = baud
        self.verbose = verbose
        self.serial_port = None
        self.lock_fd = None

    """
    this requires the robot to respond in the expected way, where all responsed end with "ok"
    """
    def get_lock(self):
        file = "/tmp/feed.lock"
        self.lock_fd = open(file,'w')
        try:
            fcntl.lockf(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except IOError:
            print(f"another process is running with lock. quitting! {file}", file=sys.stderr)
            raise

    def release_lock(self):
        """Release the lock file if it exists"""
        try:
            if self.lock_fd:
                fcntl.lockf(self.lock_fd, fcntl.LOCK_UN)
                self.lock_fd.close()
                self.lock_fd = None
        except Exception as e:
            print(f"Error releasing lock: {e}", file=sys.stderr)

    def start_block(self):
        try:
            print(f"Starting real serial on {self.serialport}")
            self.get_lock()
            self.serial_port = serial.Serial()
            self.serial_port.port = self.serialport
            self.serial_port.timeout = self.timeout
            self.serial_port.writeTimeout = self.timeout
            self.serial_port.baudrate = self.baud
            self.serial_port.open()
            print("serial opened")
        except IOError as e:
            self.release_lock()  # Make sure to release lock if serial fails
            print("robot not connected?", e)
            raise e

    def finish_block(self):
        try:
            if self.verbose:
                print("closing serial")
            if self.serial_port:
                self.serial_port.close()
                self.serial_port = None
            self.release_lock()  # Release lock when finishing
        except IOError as e:
            print("robot not connected?", e)
            raise e

    def write_command(self, command: str) -> str:
        if self.verbose:
            print(f"-> {command}")
        self.serial_port.write(str(command).encode('utf-8'))
        return self.read_serial_response()

    def read_serial_response(self):
        response = ""
        all_lines = ""
        while "ok" not in response:
            response = self.serial_port.readline().decode('utf-8')
            if response == "":
                print("timeout on serial read", file=sys.stderr)
                self.serial_port.close()
                raise IOError("Serial timeout")
            if self.verbose:
                print(f"<- {response}", end='')
            all_lines += response
        return all_lines

    def start_file(self, filepath: str, setup: BotSetup):
        if self.verbose:
            print(f"Serial output starting file: {filepath}")
            print(f"Using setup: {setup}")

    def end_file(self, filepath: str, success: bool):
        if self.verbose:
            status = "successfully" if success else "with errors"
            print(f"Serial output finished file {filepath} {status}")


class FakeDrawbotOutput(DrawbotOutput):
    def __init__(self, fake_delay=0.1, verbose=True):
        self.fake_delay = fake_delay
        self.verbose = verbose

    def start_file(self, filepath: str, setup: BotSetup):
        if self.verbose:
            print(f"Fake output starting file: {filepath}")
            print(f"Using setup: {setup}")

    def end_file(self, filepath: str, success: bool):
        if self.verbose:
            status = "successfully" if success else "with errors"
            print(f"Fake output finished file {filepath} {status}")

    def start_block(self):
        if self.verbose:
            print("Starting fake output")

    def finish_block(self):
        if self.verbose:
            print("Finishing fake output")

    def write_command(self, command: str) -> str:
        if self.verbose:
            print(f"Fake send -> {command}")
        time.sleep(self.fake_delay)
        return "fake ok"


class PNGOutput(DrawbotOutput):
    def __init__(self, output_path, line_color=(0, 0, 0), bg_color=(220,220,190), line_width=2, verbose=True, scale=10, save_interval=10):
        """
        Initialize PNGOutput with a fixed output path.
        
        Args:
            output_path: The full path where the PNG will be saved
            line_color: RGB tuple for line color (default: black)
            bg_color: RGB tuple for background color (default: off-white)
            line_width: Width of drawn lines in pixels (default: 2)
            verbose: Whether to print debug information (default: True)
            scale: Factor to scale up the image dimensions (default: 10)
            save_interval: Number of lines to draw before saving (default: 10)
        """
        self.output_path = output_path
        self.line_color = line_color
        self.bg_color = bg_color
        self.line_width = line_width
        self.verbose = verbose
        self.scale = scale
        self.save_interval = save_interval
        self.image = None
        self.draw = None
        self.current_pos = (0, 0)
        self.pen_down = False
        self.setup = None
        self.lines_since_save = 0
        
        # Create temp filename based on output path
        self.temp_path = output_path.replace(".png","_tmp.png")
        
        # Ensure the output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

    def start_file(self, filepath: str, setup: BotSetup):
        self.setup = setup
        
        # Create a new image with the drawable area dimensions
        # Width is bot width minus margins, scaled up
        width = (setup.bot_width - (2 * setup.x_margins)) * self.scale
        # Height is bot height minus minimum_y_offset, scaled up
        height = (setup.bot_height - setup.minimum_y_offset) * self.scale
        
        if self.verbose:
            print(f"Creating PNG output of size {width}x{height}")
            print(f"Bot dimensions: {setup.bot_width}x{setup.bot_height}")
            print(f"X margins: {setup.x_margins}")
            print(f"Minimum Y offset: {setup.minimum_y_offset}")
            print(f"Scale factor: {self.scale}")
            print(f"Output path: {self.output_path}")
            
        self.image = Image.new('RGB', (width, height), self.bg_color)
        self.draw = ImageDraw.Draw(self.image)
        
        # Initialize position to top-left of drawable area
        self.current_pos = (0, 0)
        self.pen_down = False
        
        # Save initial blank image
        self.save_image()

    def end_file(self, filepath: str, success: bool):
        if self.verbose:
            status = "successfully" if success else "with errors"
            print(f"PNG output finished {status}")
        
        # Final save just to be sure
        if self.image:
            self.save_image()
            self.image = None
            self.draw = None

    def save_image(self):
        """Save the current state of the image using atomic operations"""
        if self.image:
            try:
                # Save to temporary file first
                self.image.save(self.temp_path)
                # Then move the temporary file into place (atomic operation)
                os.replace(self.temp_path, self.output_path)
            except Exception as e:
                print(f"Error saving PNG: {e}")
                # Clean up temp file if it exists
                try:
                    if os.path.exists(self.temp_path):
                        os.remove(self.temp_path)
                except:
                    pass

    def write_command(self, command: str) -> str:
        if not self.image or not self.draw:
            return "png ok"
            
        try:
            if command.startswith('d'):
                # Pen up/down command
                self.pen_down = command == 'd1'
            elif command.startswith('g'):
                # Move command
                coords = command[1:].split(',')
                if len(coords) == 2:
                    # Convert from bot coordinates to image coordinates
                    x = float(coords[0])
                    y = float(coords[1])
                    
                    # Transform coordinates:
                    # Subtract x_margin to move origin to drawable area
                    # Subtract minimum_y_offset for y coordinate
                    # Scale up by scale factor
                    x = (x - self.setup.x_margins) * self.scale
                    y = (y - self.setup.minimum_y_offset) * self.scale
                    
                    new_pos = (x, y)
                    
                    if self.pen_down:
                        self.draw.line([self.current_pos, new_pos], 
                                     fill=self.line_color, 
                                     width=self.line_width)
                        self.lines_since_save += 1
                        
                        # Save periodically based on save_interval
                        if self.lines_since_save >= self.save_interval:
                            self.save_image()
                            self.lines_since_save = 0
                    
                    self.current_pos = new_pos
            
            return "png ok"
            
        except Exception as e:
            if self.verbose:
                print(f"Error processing command {command}: {e}")
            return "png error"


class DrawbotControl:
    def __init__(self, outputs: List[DrawbotOutput], verbose=True):
        self.outputs = outputs
        self.verbose = verbose
        self.proportion = 1.0
        self.state_listeners = []

    def add_state_listener(self,listener:StateListener):
        self.state_listeners.append(listener)
    
    def send_state(self,state:str):
        try:
            for listener in self.state_listeners:
                listener.set_state(state)
        except Exception as e:
            print(f"Error sending state: {e}")

    def send_progress(self,progress:float,done:int,total:int):
        try:
            for listener in self.state_listeners:
                listener.set_progress(progress,done,total)
        except Exception as e:
            print(f"Error sending progress: {e}")

    def send_estimated_time_left(self,time_left:float):
        try:
            for listener in self.state_listeners:
                listener.set_estimated_time_left(time_left)
        except Exception as e:
            print(f"Error sending estimated time left: {e}")

    def start_serial(self):
        for output in self.outputs:
            output.start_block()

    def finish_serial(self):
        for output in self.outputs:
            output.finish_block()

    def send_block(self, commands:list[str], cancel_event=None):
        if self.verbose:
            print(f"Sending {len(commands)} commands")
        
        for output in self.outputs:
            output.start_block()
            
        comment_match = re.compile("^#")
        response = ""
        num_commands = len(commands)
        last_proportion = 0
        last_update = time.time()
        start_time = time.time()
        self.send_progress(last_proportion,0,num_commands)
        self.send_estimated_time_left(num_commands)
        
        for i, line in enumerate(commands):
            try:
                if self.verbose and i % 100 == 0:
                    command_rate = i / (time.time() - start_time)
                    print(f"Sending command {i} of {num_commands}: {line} ({self.proportion}) (at {command_rate} commands/second)")
                if cancel_event and cancel_event.is_set():
                    self.do_stop()
                    print("Cancel event set, stopping execution and raising pen")
                    break
                    
                self.proportion = i / num_commands
                if abs(self.proportion - last_proportion) > 0.01 or time.time() - last_update > 30:
                    self.send_progress(round(self.proportion*100, 0),i,num_commands)
                    last_proportion = self.proportion
                    last_update = time.time()
                    time_remaining = (time.time() - start_time) * (1 - self.proportion) / self.proportion
                    self.send_estimated_time_left(time_remaining)

                if comment_match.match(line):
                    print(f"skipping line: {line}")
                elif line is not None:
                    for output in self.outputs:
                        response += output.write_command(line)
                        
            except Exception as e:
                print(f"Error sending command {i}: {e}")
                
        self.do_stop()
        for output in self.outputs:
            output.finish_block()
            
        if self.verbose:
            print(f"Finished sending {len(commands)} commands")
        return response

    def send_file(self, filepath: str, setup:BotSetup, cancel_event=None, raise_pen_after=True, home_after=True):
        """
        Send commands from a file to the drawbot.
        
        Args:
            filepath: Path to the file containing commands
            setup: BotSetup configuration
            cancel_event: Optional event to cancel execution
            raise_pen_after: Whether to raise the pen after execution (default: True)
            home_after: Whether to home the drawbot after execution (default: True)
        """
        print(f"send_file: {filepath}")
        success = False
        
        try:
            # Set state using the parent directory name
            fp = filepath.split("/")[-2]
            self.send_state(f"drawing {fp}")
            
            # Notify outputs that we're starting a file
            for output in self.outputs:
                output.start_file(filepath, setup)

            with open(filepath) as f:
                commands = f.readlines()
            
            # Strip whitespace and filter out empty lines
            commands = [cmd.strip() for cmd in commands if cmd.strip()]
            
            # Add safety commands
            final_commands = ["d0"]  # Start with pen up
            final_commands.extend(commands)
            if raise_pen_after:
                final_commands.append("d0")
            if home_after:
                final_commands.append("g380,250")
                
            output = self.send_block(final_commands, cancel_event)
            print("Finished send_file")
            self.send_state("idle")
            success = True
            return output
            
        except Exception as e:
            print(f"Error reading or executing file {filepath}: {e}")
            self.send_state("idle")  # Ensure we reset state even on error
            raise
            
        finally:
            # Notify outputs that we're done with the file
            for output in self.outputs:
                output.end_file(filepath, success)

    def do_stop(self):
        try:
            for output in self.outputs:
                output.write_command("d0")
        except Exception as e:
            print(f"Error stopping drawbot: {e}")
        try:    
            self.send_progress(0,0,0)
            self.send_estimated_time_left(-1)
            self.send_state("idle")
        except Exception as e:
            print(f"Error sending progress: {e}")

    def pen_up(self,cancel_event=None):
        return self.send_block(["d0"],cancel_event)

    def pen_down(self,cancel_event=None):
        return self.send_block(["d1"],cancel_event)

    def calibrate(self,cancel_event=None):
        self.send_state("calibrating")
        output = self.send_block(["c"],cancel_event)
        self.send_state("idle")
        return output

    def home(self,cancel_event=None):
        self.send_state("homing")
        output = self.send_block(["g380,250"],cancel_event)
        self.send_state("idle")
        return output

    def readFile(self, filepath:str):
        gcode = open(filepath)
        gcodes = gcode.readlines()
        return gcodes


