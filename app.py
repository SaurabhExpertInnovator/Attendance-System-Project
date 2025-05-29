from flask import Flask, render_template, request, send_file
import pandas as pd
import qrcode
import uuid
import os
from datetime import datetime
from io import BytesIO
from pytz import timezone
import math

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

qr_folder = os.path.join('static', 'qr')
os.makedirs(qr_folder, exist_ok=True)

sessions = {}  # session_id -> session details
attendance = {}  # session_id -> list of marked attendance dicts

# Use Render public URL for deployed app
BASE_URL = 'https://attendance-system-project.onrender.com/'

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000  # meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    file = request.files.get('file')
    latitude = request.form.get('latitude')
    longitude = request.form.get('longitude')
    radius = request.form.get('radius')

    if not latitude or not longitude or not radius:
        return 'Location and radius are required.'

    try:
        latitude = float(latitude)
        longitude = float(longitude)
        radius = float(radius)
    except ValueError:
        return 'Invalid location or radius values.'

    if file:
        df = pd.read_csv(file)
        session_id = str(uuid.uuid4())
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], session_id + '.csv')
        df.to_csv(filepath, index=False)

        sessions[session_id] = {
            'filename': filepath,
            'latitude': latitude,
            'longitude': longitude,
            'radius': radius
        }

        url = BASE_URL + 'scan/' + session_id
        qr = qrcode.make(url)
        qr_path = os.path.join(qr_folder, session_id + '.png')
        qr.save(qr_path)

        return render_template('qr_display.html', qr_path='qr/' + session_id + '.png', session_id=session_id)
    else:
        return 'File not uploaded.'

@app.route('/scan/<session_id>')
def scan(session_id):
    session = sessions.get(session_id)
    if not session:
        return 'Invalid session ID.'

    df = pd.read_csv(session['filename'])
    students = df.to_dict(orient='records')
    roll_col = df.columns[0]
    name_col = df.columns[1]

    return render_template('student_list.html', students=students, session_id=session_id, roll_col=roll_col, name_col=name_col)

@app.route('/mark', methods=['POST'])
def mark_attendance():
    session_id = request.form.get('session_id')
    name = request.form.get('name')
    roll = request.form.get('roll_number')
    lat = request.form.get('latitude')
    lon = request.form.get('longitude')

    if not lat or not lon:
        return 'Location access is required to mark attendance.'

    try:
        lat = float(lat)
        lon = float(lon)
    except ValueError:
        return 'Invalid latitude or longitude.'

    session = sessions.get(session_id)
    if not session:
        return 'Invalid session.'

    dist = haversine(lat, lon, session['latitude'], session['longitude'])
    if dist > session['radius']:
        return f'You are outside the allowed area (Distance: {dist:.2f} m). Attendance not marked.'

    if session_id not in attendance:
        attendance[session_id] = []

    # Prevent multiple attendance for same roll number
    for record in attendance[session_id]:
        if record['roll'] == roll:
            return 'Attendance already marked for this roll number.'

    india_time = datetime.now(timezone('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S')

    attendance[session_id].append({
        'name': name,
        'roll': roll,
        'timestamp': india_time
    })

    return 'Attendance marked successfully!'

@app.route('/download/<session_id>')
def download(session_id):
    session = sessions.get(session_id)
    if not session:
        return 'Invalid session.'

    if session_id not in attendance:
        return 'No attendance data for this session.'

    df = pd.read_csv(session['filename'])
    attendance_records = attendance[session_id]

    # Column name as current IST date-time
    col_name = datetime.now(timezone('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S')

    present_rolls = {record['roll']: 1 for record in attendance_records}

    # Add attendance column: 1 for present, 0 for absent
    df[col_name] = df[df.columns[0]].apply(lambda roll: present_rolls.get(roll, 0))

    output = BytesIO()
    df.to_csv(output, index=False)
    output.seek(0)

    return send_file(output, mimetype='text/csv', as_attachment=True, download_name=f'attendance_{session_id}.csv')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
