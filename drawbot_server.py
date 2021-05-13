# Run with:
# export FLASK_APP=drawbot_server
# export FLASK_ENV=development
# flask run


from flask import Flask, render_template, send_from_directory, flash, request, redirect, url_for
import os
import random
import string

from drawbot_converter.svg_transform import BotSetup
import drawbot_converter.process as pr


app = Flask(__name__)


UPLOAD_FOLDER = 'data/uploaded'
ALLOWED_EXTENSIONS = {'svg'}
app.config['UPLOAD_PATH'] = UPLOAD_FOLDER

@app.route("/", methods=['GET', 'POST'])
def index():
    if request.method == 'POST' and good_file():
        return handle_upload(request.files['file'])
    return render_template('index.html')

@app.route("/design/<int:id>")
def design(id):
    return render_template('design.html',id=id)

@app.route('/data/<path:filepath>')
def data(filepath):
    return send_from_directory('data', filepath)

def rand_id():
    return ''.join(random.choice(string.digits) for x in range(6))

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        # check if the post request has the file part
        if 'file' not in request.files:
            flash('No file part')
            return redirect(request.url)
        file = request.files['file']
        # if user does not select file, browser also
        # submit an empty part without filename
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            id = rand_id()
            filename = f"{id}.svg"
            path = os.path.join(app.config['UPLOAD_PATH'], filename)
            file.save(path)
            process_file(id)
            return redirect(f'/design/{id}')
    return '''
    <!doctype html>
    <title>Upload new File</title>
    <h1>Upload new File</h1>
    <form method=post enctype=multipart/form-data>
      <input type=file name=file>
      <input type=submit value=Upload>
    </form>
    '''
def handle_upload(file):
    id = rand_id()
    filename = f"{id}.svg"
    path = os.path.join(app.config['UPLOAD_PATH'], filename)
    file.save(path)
    process_file(id)
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

def process_file(id,setup:BotSetup=None):
    if not setup:
        setup = BotSetup(
            bot_width=760,
            bot_height=580,
            paper_width=584,
            paper_height=420,
            drawing_width=200,
            drawing_height=200
        ).center_paper().center_drawing()
    pr.process(setup=setup,
        file=f"data/uploaded/{id}.svg",
        intermediate=f"data/processed/{id}.svg",
        check_svg=f"data/check_svg/{id}.gcode",
        gcode=f"data/gcode/{id}.gcode",
        check_gcode=f"data/check/{id}.svg"
        )


if __name__ == "__main__":
    app.run(debug=True)
