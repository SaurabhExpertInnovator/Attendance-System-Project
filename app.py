from flask import Flask, render_template, request, redirect, url_for, jsonify
import pandas as pd
import os
import uuid
import qrcode
from datetime import datetime

app = Flask(__name__)

# Base URL for generating public QR code links
BASE_URL = os.environ.get("BASE_URL", "https://attendance-system-project.onrender.com")

# Store sessions in memory
sessions = {}

def save_attendance(session_id, student_id, lat, lon):
    attendance_file = f"attendance_{session_id}.csv"
    df = pd.read_csv(sessions[session_id]['filepath'])
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df.loc[df['Student ID'] == student_id, 'Attendance'] = f"Present ({timestamp})"
    df.loc[df['Student ID'] == student_id, 'Latitude'] = lat
    df.loc[df['Student ID'] == student_id, 'Longitude'] = lon
    df.to_csv(attendance_file, index=False)
    return attendance_file

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate_qr', methods=['POST'])
def generate_qr():
    file = request.files['csv_file']
    lat = request.form['latitude']
    lon = request.form['longitude']

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
        'longitude': lon
    }

    session_url = f"{BASE_URL}/scan/{session_id}"
    qr = qrcode.make(session_url)
    qr_path = f"static/qr_{session_id}.png"
    qr.save(qr_path)

    return render_template('qr_display.html', qr_path=qr_path, session_url=session_url)

@app.route('/scan/<session_id>')
def scan(session_id):
    if session_id not in sessions:
        return "Invalid session ID"

    df = pd.read_csv(sessions[session_id]['filepath'])
    students = df.to_dict(orient='records')
    return render_template('scan.html', students=students, session_id=session_id)

@app.route('/submit_attendance', methods=['POST'])
def submit_attendance():
    session_id = request.form['session_id']
    student_id = request.form['student_id']
    lat = request.form['latitude']
    lon = request.form['longitude']

    if not lat or not lon:
        return "Location access is required to mark attendance"

    save_attendance(session_id, student_id, lat, lon)
    return "Attendance marked successfully. Thank you!"

@app.route('/download/<session_id>')
def download_attendance(session_id):
    attendance_file = f"attendance_{session_id}.csv"
    if not os.path.exists(attendance_file):
        return "Attendance file not found"
    return redirect(f"/{attendance_file}")

if __name__ == '__main__':
    app.run(debug=True)
