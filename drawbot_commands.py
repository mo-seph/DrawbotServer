import subprocess
from drawbot_server import executor

def send_drawbot_command(command:str):
    command = f"./drawbot {command}"
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def pen_up():
    send_drawbot_command("--command d0")

def pen_down():
    send_drawbot_command("--command d1")

def calibrate():
    send_drawbot_command("--command c")

def draw_file(filepath:str):
    send_drawbot_command(f"--command d2 {filepath}")