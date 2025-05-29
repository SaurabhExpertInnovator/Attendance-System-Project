from flask import Flask, render_template, request, redirect, url_for, flash, send_file
import csv
import os
import datetime
from geopy.distance import geodesic
import pandas as pd
import qrcode
from io import BytesIO

app = Flask(__name__)
app.secret_key = "secret"

STUDENT_CSV = 'students.csv'
ALLOWED_RADIUS_METERS = 100

# Define teacher's location (this will be auto-detected in full version)
TEACHER_LOCATION = (28.7041, 77.1025)

# -------------------------
# Routes
# -------------------------

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/qr')
def qr_display():
    # Generate QR code pointing to /mark page
    qr_url = request.host_url + 'mark'
    img = qrcode.make(qr_url)
    buffer = BytesIO()
    img.save(buffer, 'PNG')
    buffer.seek(0)
    return send_file(buffer, mimetype='image/png')

@app.route('/upload', methods=['GET', 'POST'])
def upload_csv():
    if request.method == 'POST':
        file = request.files['file']
        if file.filename.endswith('.csv'):
            file.save(STUDENT_CSV)
            flash("CSV uploaded successfully!", "success")
            return redirect(url_for('home'))
        else:
            flash("Invalid file format. Please upload a CSV file.", "danger")
    return render_template('upload.html')

@app.route('/mark', methods=['GET', 'POST'])
def mark_attendance():
    students = []
    if os.path.exists(STUDENT_CSV):
        df = pd.read_csv(STUDENT_CSV)
        students = df[['Name', 'Roll']].values.tolist()

    if request.method == 'POST':
        name = request.form['name']
        roll = request.form['roll']
        lat = float(request.form['latitude'])
        lon = float(request.form['longitude'])
        user_loc = (lat, lon)

        df = pd.read_csv(STUDENT_CSV)
        today = datetime.date.today().isoformat()
        if today not in df.columns:
            df[today] = 0

        matched = df[(df['Name'] == name) & (df['Roll'].astype(str) == roll)]

        if not matched.empty:
            distance = geodesic(user_loc, TEACHER_LOCATION).meters
            if distance <= ALLOWED_RADIUS_METERS:
                index = matched.index[0]
                df.at[index, today] = 1
                flash("Attendance marked successfully!", "success")
            else:
                flash("You are outside the allowed location range.", "danger")
        else:
            flash("Student not found in the record!", "danger")

        # Update attendance percentage
        attendance_cols = df.columns[2:]  # Skip Name and Roll
        df['Attendance %'] = df[attendance_cols].sum(axis=1) / len(attendance_cols) * 100
        df.to_csv(STUDENT_CSV, index=False)

        return redirect(url_for('thank_you'))

    return render_template('student_list.html', students=students)

@app.route('/thankyou')
def thank_you():
    df = pd.read_csv(STUDENT_CSV)
    today = datetime.date.today().isoformat()
    total_present = df[today].sum() if today in df.columns else 0
    total_students = len(df)
    return render_template("thank_you.html", present=total_present, total=total_students)

@app.route('/students')
def student_list():
    if os.path.exists(STUDENT_CSV):
        df = pd.read_csv(STUDENT_CSV)
        records = df.to_dict(orient='records')
        return render_template("students.html", records=records, headers=df.columns)
    return "No student data available."

# -------------------------
# Main
# -------------------------

if __name__ == '__main__':
    app.run(debug=True)
