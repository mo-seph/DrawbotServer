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


app = Flask(__name__)
executor = Executor(app)

app.secret_key = 'your-secret-key-here'  # Add this line after creating the Flask app


UPLOAD_FOLDER = 'data/uploaded'
ALLOWED_EXTENSIONS = {'svg'}
app.config['UPLOAD_PATH'] = UPLOAD_FOLDER

setup = BotSetup().add_magnets(inset=180,height=100)

@app.route("/", methods=['GET', 'POST'])
def index():
    print("Showing index page...")
    if request.method == 'POST' and good_file():
        print("Got a file uploaded!")
        return handle_upload(request.files['file'],request.form)
    return render_template('index.html',setup=setup,tasks=executor.futures)

@app.route("/design/<int:id>", methods=['GET','POST'])
def design(id):
    global setup
    if request.method == 'POST':
        if request.form.get('action') == 'reprocess':
            # Reprocess existing file
            setup = form_to_setup(request.form)
            process_file(str(id), setup)
            return redirect(f'/design/{id}')
        elif good_file():
            # Handle new file upload
            print("Got a file uploaded!")
            return handle_upload(request.files['file'], request.form, f"{id}")
    return render_template('design.html', id=id, setup=setup)

@app.route('/data/<path:filepath>')
def data(filepath):
    return send_from_directory('data', filepath)

def rand_id():
    return ''.join(random.choice(string.digits) for x in range(6))

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def handle_upload(file,form,id=None):
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
    print(f"Processing {id}")   
    process_file(id,setup)
    print(f"Redirecting to {id}")
    return redirect(f'/design/{id}')

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
