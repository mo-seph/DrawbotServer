# Run with:
# export FLASK_APP=drawbot_server
# export FLASK_ENV=development
# flask run


from flask import Flask, render_template, send_from_directory, flash, request, redirect, url_for, current_app
from flask.signals import appcontext_pushed

import os
import random
import string
from drawbot_converter.transformer_svgpathtools import TransformerSVGPathTools

from drawbot_converter.bot_setup import BotSetup
import drawbot_converter.process as pr

from flask_executor import Executor
from datetime import datetime

from drawbot_control import DrawbotControl, FakeDrawbotOutput, SerialDrawbotOutput, PNGOutput
from drawbot_ha import HAConnection
import uuid  # Add this import at the top
import threading
import socket

import functools
print = functools.partial(print, flush=True)


app = Flask(__name__)
app.config['EXECUTOR_TYPE'] = 'thread'
app.config['EXECUTOR_MAX_WORKERS'] = 1

executor = Executor(app)
futures = []

app.secret_key = 'your-secret-key-here'  # Add this line after creating the Flask app


UPLOAD_FOLDER = 'data/uploaded'
CURRENT_IMAGE_PATH = 'data/png_output.png'
NO_DRAWING_IMAGE_PATH = 'static/no_drawing.png'
ALLOWED_EXTENSIONS = {'svg'}
app.config['UPLOAD_PATH'] = UPLOAD_FOLDER

setup = BotSetup().standard_magnets().a3_paper().rodalm_21_30()
fake = 'FAKE_DRAWBOT' in os.environ
outputs = []
if fake:
    outputs.append(FakeDrawbotOutput(fake_delay=0.01,verbose=False))
else:
    outputs.append(SerialDrawbotOutput(verbose=False))

outputs.append(PNGOutput(output_path=CURRENT_IMAGE_PATH))

controller = DrawbotControl(outputs=outputs,verbose=True)

print(f"Using fake drawbot: {fake}")

def get_local_ip():
    """Get the local IP address of the machine"""
    try:
        # Create a socket and connect to an external server
        # This doesn't actually establish a connection but gives us the local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"  # Fallback to localhost if we can't get IP

local_address = get_local_ip()
print(f"Local address: {local_address}")
port = 5001 if fake else 5000

base_url = f"http://{local_address}:{port}"
mqtt_server = "moominpappa.local" if fake else "192.168.2.6"



#if not fake:
ha = HAConnection(controller,config_url=base_url,mqtt_host=mqtt_server,image_path=CURRENT_IMAGE_PATH, no_drawing_image_path=NO_DRAWING_IMAGE_PATH)

# Add this near the top with other global variables
PAPER_SIZES = {
    'A3': {
        'paper': {'width': 420, 'height': 297, 'offset': 80},
    },
    'A3 Low': {
        'paper': {'width': 420, 'height': 297, 'offset': 230},
    },
    'A2': {
        'paper': {'width': 420, 'height': 594, 'offset': 80},
    },
    'Rodalm21x30': {
        'drawing': {'width': 180, 'height': 130, 'offset': 70},
    },
    'Rodalm21x30 Full Frame': {
        'drawing': {'width': 210, 'height': 300, 'offset': 70},
    },
    'Rodalm13x18': {
        'drawing': {'width': 150, 'height': 100, 'offset': 70},
    },
    'Rodalm30x40': {
        'drawing': {'width': 210, 'height': 300, 'offset': 70},
    },
    'Rodalm40x50': {
        'drawing': {'width': 300, 'height': 400, 'offset': 70},
    },
    'Sannahed25': {
        'drawing': {'width': 130, 'height': 130, 'offset': 70},
    },
    'Sannahed25 Full Frame': {
        'paper': {'width': 420, 'height': 297, 'offset': 230},
        'drawing': {'width': 250, 'height': 250, 'offset': 10},
    },
}

# Update base_url when handling requests
@app.before_request
def update_base_url():
    global base_url
    if fake:
        # Get actual port from request
        server_port = request.environ.get('SERVER_PORT', '5000')
        base_url = f"http://{local_address}:{server_port}"

@app.route("/", methods=['GET', 'POST'])
def index():
    print("Showing index page...")
    return process_request(request)

@app.route("/design/<int:id>", methods=['GET','POST'])
def design(id):
    global setup
    return process_request(request,id)

@app.route('/data/<path:filepath>')
def data(filepath):
    return send_from_directory('data', filepath)

def process_request(request,id=None):
    global setup
    global futures
    command_regex = r"command_(.*)"
    task_regex = r"task_(.*)"
    print(f"request: {request}")
    print(f"ID: {id}")
    if request.method == 'POST':
        if request.form.get('action') == 'reprocess' and id:
            # Reprocess existing file
            setup = form_to_setup(request.form)
            process_file(str(id), setup)
            return redirect(f'/design/{id}')
        elif request.form.get('control'):
            future = handle_drawbot_command(request.form.get('control'),id)
            if future:
                futures.append(future)  # Store the future for tracking
        elif request.form.get('cancel_task'):
            cancel_drawbot_task(request.form.get('cancel_task'))
        elif good_file():
            # Handle new file upload
            print("Got a file uploaded!")
            id = upload_svg_file(request.files['file'], request.form, id)
            process_file(str(id), setup)
            return redirect(f'/design/{id}')

    # Clean up completed tasks before rendering
    futures = [f for f in futures if not f.done()]
    
    # Get a list of the most recent 10 directories in the data/upload folder
    upload_dir = os.path.join(app.config['UPLOAD_PATH'])
    recent_dirs = sorted(os.listdir(upload_dir), key=lambda x: os.path.getmtime(os.path.join(upload_dir, x)), reverse=True)[:10]
    # For each directory, make a dict with the id, modified time, link to the design page and to the uploaded SVG file
    recent_dirs_info = []
    for dir in recent_dirs:
        dir_path = os.path.join(upload_dir, dir)
        dir_id = dir
        modified_time = datetime.fromtimestamp(os.path.getmtime(dir_path)).strftime('%Y-%m-%d %H:%M:%S')
        design_link = f"/design/{dir_id}"
        svg_link = f"/data/uploaded/{dir_id}/input.svg"
        recent_dirs_info.append({'id': dir_id, 'modified_time': modified_time, 'design_link': design_link, 'svg_link': svg_link})
    
    print(f"ID for render: {id}")
    return render_template('design.html' if id else 'index.html', 
                         id=id, 
                         setup=setup,
                         tasks=futures,
                         recent_files=recent_dirs_info,
                         sizes=PAPER_SIZES)

def handle_drawbot_command(command,id=None):
    global setup
    print(f"handle_drawbot_command: {command}")
    
    command_tasks = {
        'pen_up': [controller.pen_up],
        'pen_down': [controller.pen_down],
        'calibrate': [controller.calibrate],
        'home': [controller.home],
        'draw_file': [controller.send_file,f"data/uploaded/{id}/output.gcode",setup]
    }
    
    if command in command_tasks:
        print(f"Submitting command: {command}")
        cancel_event = threading.Event()
        print(f"Command tasks for {command}: {command_tasks[command]}")
        if len(command_tasks[command]) > 1:
            print(f"Submitting with args: func={command_tasks[command][0]}, args={command_tasks[command][1:]}, cancel_event={cancel_event}")
            future = executor.submit(command_tasks[command][0], *command_tasks[command][1:], cancel_event)
        else:
            print(f"Submitting without args: func={command_tasks[command][0]}, cancel_event={cancel_event}")
            future = executor.submit(command_tasks[command][0], cancel_event)
        
        # Add metadata including unique ID to the future
        future.command = command
        future.start_time = datetime.now()
        future.task_id = str(uuid.uuid4())
        future.cancel_event = cancel_event  # Store the event on the future
        
        # Add a done callback to handle any errors
        def handle_future_error(future):
            try:
                # This will raise the exception if there was one
                future.result()
            except Exception as e:
                import traceback
                print(f"\nError in future execution for command '{command}':")
                print(f"Error type: {type(e).__name__}")
                print(f"Error message: {str(e)}")
                print("Full stack trace:")
                traceback.print_exc()
                print(f"\nCommand details:")
                print(f"Function: {command_tasks[command][0]}")
                if len(command_tasks[command]) > 1:
                    print(f"Arguments: {command_tasks[command][1:]}")
        
        future.add_done_callback(handle_future_error)
        
        if command == "draw_file":
            # Get the absolute path to the input.svg file
            base_url = url_for(f"index",_external=True)
            image_url = f"{base_url}/data/uploaded/{id}/input.svg"
            print(f"Setting image URL: {image_url}")
            ha.set_target_image(image_url)
        else:
            ha.set_target_image(None)
        
        print(f"Future: {future}")
        return future
    else:
        print(f"Unknown command: {command}")
        return None

def cancel_drawbot_task(task_id):
    print(f"cancel_drawbot_task: {task_id}")
    # Find and cancel the future with matching ID
    for future in futures:
        if hasattr(future, 'task_id') and future.task_id == task_id:
            # Set the cancel event
            future.cancel_event.set()
            #future.cancel()  # Still call cancel() for good measure
            print(f"Cancelled task: {future.command}")
            executor.submit(controller.pen_up)
            break

def rand_id():
    return ''.join(random.choice(string.digits) for x in range(6))

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def upload_svg_file(file,form,id=None):
    global setup
    setup = form_to_setup(form)
    if not id:
        id = rand_id()
    dir_path = os.path.join(app.config['UPLOAD_PATH'], str(id))
    print(f"Ensuring directory {dir_path} exists")
    os.makedirs(dir_path, exist_ok=True)
    path = os.path.join(dir_path, "input.svg")
    print(f"Saving to {path}")
    file.save(path)
    return id

def good_file():
    # check if the post request has the file part
    if 'file' not in request.files:
        flash('No file part')
        return False
    file = request.files['file']
    # if user does not select file, browser also
    # submit an empty part without filename
    if file.filename == '':
        flash('No selected file')
        return False
    if not file:
        flash('No file found')
        return False
    if not allowed_file(file.filename):
        flash('Wrong filetype')
        return False
    return True

def process_file(id,setup:BotSetup):
    processor = TransformerSVGPathTools()
    processor.pipeline(setup=setup,
        input_svg=f"data/uploaded/{id}/input.svg",
        processed_svg=f"data/uploaded/{id}/processed.svg",
        output_gcode=f"data/uploaded/{id}/output.gcode",
        check_gcode=f"data/uploaded/{id}/gcode_check.svg",
        annot_check_gcode=f"data/uploaded/{id}/check.svg"
        )

def form_to_setup(form):
    global setup
    print(f"form_to_setup Start: {setup}")
    print(f"form: {form}")
    if 'bot_width' in form:
        setup.bot_width=int(form['bot_width'])
    if 'bot_height' in form:
        setup.bot_height=int(form['bot_height'])
    if 'paper_width' in form:
        setup.paper_width=int(form['paper_width'])
    if 'paper_height' in form:
        setup.paper_height=int(form['paper_height'])
    if 'drawing_width' in form:
        setup.drawing_width=int(form['drawing_width'])
    if 'drawing_height' in form:
        setup.drawing_height=int(form['drawing_height'])
    if 'fill_target' in form:
        setup.fill_target= True if form['fill_target'] == 'on' else False
    if 'paper_offset' in form:
        setup.paper_offset_h = int(form['paper_offset'])
        setup.top_center_paper(int(form['paper_offset']))
    if 'drawing_offset' in form:
        setup.drawing_offset_h = int(form['drawing_offset'])
        setup.top_center_drawing(int(form['drawing_offset']))
    print(f"form_to_setup End : {setup}")
    return setup


if __name__ == "__main__":
    print("Starting app")
    app.run(debug=True,host='0.0.0.0')
    print("App started")
