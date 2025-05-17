from flask import Flask, render_template, request, redirect, url_for, send_file
import pandas as pd
import os
import uuid
import qrcode
import json
from datetime import datetime
from io import BytesIO
from pytz import timezone
import math

app = Flask(__name__)

# Use local IP address for QR code link generation
LOCAL_IP = "172.20.67.110"
PORT = 5000
BASE_URL = f"http://{LOCAL_IP}:{PORT}"

# Persistent storage file for session metadata
SESSION_FILE = "session_data.json"

# Ensure static/qr folder exists
qr_folder = os.path.join('static', 'qr')
os.makedirs(qr_folder, exist_ok=True)

# Load or initialize session storage
def load_sessions():
    print(f"Loading session data from: {SESSION_FILE}")
    if os.path.exists(SESSION_FILE):
        with open(SESSION_FILE, 'r') as f:
            try:
                sessions = json.load(f)
                print(f"Loaded sessions: {sessions}")
                return sessions
            except json.JSONDecodeError:
                print("JSON decode error in session file.")
                return {}
    print("Session file not found.")
    return {}

def save_sessions(data):
    print(f"Saving session data to: {SESSION_FILE}")
    with open(SESSION_FILE, 'w') as f:
        json.dump(data, f)
        print(f"Saved sessions: {data}")

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
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

@app.route('/generate_qr', methods=['POST'])
def generate_qr():
    file = request.files['csv_file']
    lat = float(request.form['latitude'])
    lon = float(request.form['longitude'])
    radius = float(request.form['radius'])

    df = pd.read_csv(file)
    df['Attendance'] = 'Absent'
    df['Latitude'] = ''
    df['Longitude'] = ''

    session_id = str(uuid.uuid4())
    filepath = f"session_{session_id}.csv"
    df.to_csv(filepath, index=False)

    sessions = load_sessions()
    sessions[session_id] = {
        'filepath': filepath,
        'latitude': lat,
        'longitude': lon,
        'radius': radius
    }
    save_sessions(sessions)

    session_url = f"{BASE_URL}/scan/{session_id}"
    qr = qrcode.make(session_url)
    qr_path = f"{qr_folder}/qr_{session_id}.png"
    qr.save(qr_path)

    return render_template('qr_display.html', qr_path=f"qr/qr_{session_id}.png", session_url=session_url, session_id=session_id)

@app.route('/scan/<session_id>')
def scan(session_id):
    print(f"Scan route accessed with session_id: {session_id}")
    sessions = load_sessions()
    print(f"Available session keys: {list(sessions.keys())}")
    if session_id not in sessions:
        return "Invalid session ID"

    df = pd.read_csv(sessions[session_id]['filepath'])
    students = df.to_dict(orient='records')
    return render_template('student_list.html', students=students, session_id=session_id, roll_col='Student ID', name_col='Name')

@app.route('/submit_attendance', methods=['POST'])
def submit_attendance():
    session_id = request.form['session_id']
    student_id = request.form['roll_number']
    student_name = request.form['name']
    lat = request.form['latitude']
    lon = request.form['longitude']

    if not lat or not lon:
        return "Location access is required to mark attendance"

    try:
        lat = float(lat)
        lon = float(lon)
    except ValueError:
        return "Invalid latitude or longitude"

    sessions = load_sessions()
    session = sessions.get(session_id)
    if not session:
        return "Invalid session ID"

    dist = haversine(lat, lon, session['latitude'], session['longitude'])
    if dist > session['radius']:
        return "You are outside the allowed area. Attendance not marked."

    df = pd.read_csv(session['filepath'])
    timestamp = datetime.now(timezone('Asia/Kolkata')).strftime("%Y-%m-%d %H:%M:%S")
    df.loc[df['Student ID'] == student_id, 'Attendance'] = f"Present ({timestamp})"
    df.loc[df['Student ID'] == student_id, 'Latitude'] = lat
    df.loc[df['Student ID'] == student_id, 'Longitude'] = lon

    attendance_file = f"attendance_{session_id}.csv"
    df.to_csv(attendance_file, index=False)

    return "Attendance marked successfully. Thank you!"

@app.route('/download/<session_id>')
def download_attendance(session_id):
    attendance_file = f"attendance_{session_id}.csv"
    if not os.path.exists(attendance_file):
        return "Attendance file not found"

    return send_file(attendance_file, as_attachment=True, download_name=f'attendance_{session_id}.csv')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
