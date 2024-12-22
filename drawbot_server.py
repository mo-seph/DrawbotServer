# Run with:
# export FLASK_APP=drawbot_server
# export FLASK_ENV=development
# flask run


from flask import Flask, render_template, send_from_directory, flash, request, redirect, url_for
import os
import random
import string
from drawbot_converter.transformer_svgpathtools import TransformerSVGPathTools

from drawbot_converter.bot_setup import BotSetup
import drawbot_converter.process as pr

from flask_executor import Executor
from datetime import datetime

from drawbot_control import DrawbotControl
import uuid  # Add this import at the top
import threading


app = Flask(__name__)
app.config['EXECUTOR_TYPE'] = 'thread'
app.config['EXECUTOR_MAX_WORKERS'] = 1

executor = Executor(app)
futures = []

app.secret_key = 'your-secret-key-here'  # Add this line after creating the Flask app


UPLOAD_FOLDER = 'data/uploaded'
ALLOWED_EXTENSIONS = {'svg'}
app.config['UPLOAD_PATH'] = UPLOAD_FOLDER

setup = BotSetup().standard_magnets().a3_paper().rodalm_21_30()
fake = 'FAKE_DRAWBOT' in os.environ
controller = DrawbotControl(fake=fake)
print(f"Using fake drawbot: {fake}")

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
    
    return render_template('design.html' if id else 'index.html', 
                         id=id, 
                         setup=setup,
                         tasks=futures)

def handle_drawbot_command(command,id=None):
    print(f"handle_drawbot_command: {command}")
    
    command_tasks = {
        'pen_up': [controller.pen_up],
        'pen_down': [controller.pen_down],
        'calibrate': [controller.calibrate],
        'home': [controller.home],
        'draw_file': [controller.draw_file,f"data/uploaded/{id}/output.gcode"]
    }
    
    if command in command_tasks:
        print(f"Submitting command: {command}")
        cancel_event = threading.Event()
        if len(command_tasks[command]) == 2:
            future = executor.submit(command_tasks[command][0], command_tasks[command][1],cancel_event)
        else:
            future = executor.submit(command_tasks[command][0],cancel_event)
        # Add metadata including unique ID to the future
        future.command = command
        future.start_time = datetime.now()
        future.task_id = str(uuid.uuid4())
        future.cancel_event = cancel_event  # Store the event on the future
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
    dir_path = os.path.join(app.config['UPLOAD_PATH'], id)
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
    app.run(debug=True)
