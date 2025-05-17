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

BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000")  # Change if deploying

SESSION_FILE = "session_data.json"
qr_folder = os.path.join('static', 'qr')
os.makedirs(qr_folder, exist_ok=True)

def load_sessions():
    if os.path.exists(SESSION_FILE):
        with open(SESSION_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_sessions(data):
    with open(SESSION_FILE, 'w') as f:
        json.dump(data, f)

sessions = load_sessions()

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
    try:
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

        sessions[session_id] = {
            'filepath': filepath,
            'latitude': lat,
            'longitude': lon,
            'radius': radius
        }
        save_sessions(sessions)

        session_url = f"{BASE_URL}/scan/{session_id}"
        qr = qrcode.make(session_url)
        qr_path = f"qr_{session_id}.png"
        qr.save(os.path.join(qr_folder, qr_path))

        return render_template('qr_display.html', qr_path=f"qr/{qr_path}", session_url=session_url, session_id=session_id)

    except Exception as e:
        return f"An error occurred: {str(e)}"

@app.route('/scan/<session_id>')
def scan(session_id):
    sessions.update(load_sessions())
    if session_id not in sessions:
        return "Invalid session ID"

    df = pd.read_csv(sessions[session_id]['filepath'])
    students = df.to_dict(orient='records')
    # Assuming CSV has columns named 'Student ID' and 'Name'
    return render_template('student_list.html', students=students, session_id=session_id, roll_col='Student ID', name_col='Name')

@app.route('/mark', methods=['POST'])
def submit_attendance():
    try:
        session_id = request.form['session_id']
        student_id = request.form['roll_number']
        lat = request.form['latitude']
        lon = request.form['longitude']

        if not lat or not lon:
            return "Location access is required to mark attendance"

        lat = float(lat)
        lon = float(lon)

        sessions.update(load_sessions())
        session = sessions.get(session_id)
        if not session:
            return "Invalid session."

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
    except Exception as e:
        return f"An error occurred while marking attendance: {str(e)}"

@app.route('/download/<session_id>')
def download_attendance(session_id):
    attendance_file = f"attendance_{session_id}.csv"
    if not os.path.exists(attendance_file):
        return "Attendance file not found"
    return send_file(attendance_file, as_attachment=True, download_name=f'attendance_{session_id}.csv')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
