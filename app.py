from flask import Flask, render_template, request, send_file
import pandas as pd
import qrcode, uuid, os, math
from datetime import datetime
from io import BytesIO
from pytz import timezone

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'

# ---------------------------------------------------------------------------
#  folder setup
# ---------------------------------------------------------------------------
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
qr_folder = os.path.join('static', 'qr')
os.makedirs(qr_folder, exist_ok=True)

# ---------------------------------------------------------------------------
#  in-memory stores
# ---------------------------------------------------------------------------
sessions   = {}   # session_id → dict with CSV filename, geo-fence & cached lookup
attendance = {}   # session_id → list of {name, roll, timestamp}

# Render base URL (change if you deploy somewhere else)
BASE_URL = 'https://attendance-system-project.onrender.com/'

# ---------------------------------------------------------------------------
def haversine(lat1, lon1, lat2, lon2):
    """Distance in metres between two lat/lon pairs."""
    R = 6371000
    φ1, φ2   = map(math.radians, (lat1, lat2))
    dφ       = math.radians(lat2 - lat1)
    dλ       = math.radians(lon2 - lon1)
    a = math.sin(dφ/2)**2 + math.cos(φ1)*math.cos(φ2)*math.sin(dλ/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def normalize_roll(roll):
    """Normalize roll number string for consistent lookup."""
    return str(roll).strip().lower().lstrip('0')


# ---------------------------------------------------------------------------
@app.route('/')
def index():
    return render_template('index.html')


# ---------------------------------------------------------------------------
#  Teacher uploads CSV & geo-fence
# ---------------------------------------------------------------------------
@app.route('/upload', methods=['POST'])
def upload():
    file      = request.files.get('file')
    latitude  = request.form.get('latitude')
    longitude = request.form.get('longitude')
    radius    = request.form.get('radius')

    if not (latitude and longitude and radius):
        return 'Location and radius are required.'

    try:
        latitude, longitude, radius = map(float, (latitude, longitude, radius))
    except ValueError:
        return 'Invalid location / radius.'

    if not file:
        return 'No file uploaded.'

    # save CSV and build fast lookup
    try:
        df = pd.read_csv(file)
    except Exception:
        return 'Unable to read CSV. Please upload a valid CSV file.'

    session_id = str(uuid.uuid4())
    csv_path   = os.path.join(app.config['UPLOAD_FOLDER'], f'{session_id}.csv')
    df.to_csv(csv_path, index=False)

    roll_col = df.columns[0]
    name_col = df.columns[1] if df.shape[1] > 1 else None

    # Build dict: normalized roll_number → row-dict
    students_map = {
        normalize_roll(row[roll_col]): row.to_dict()
        for _, row in df.iterrows()
    }

    sessions[session_id] = dict(
        filename=csv_path,
        latitude=latitude,
        longitude=longitude,
        radius=radius,
        roll_col=roll_col,
        name_col=name_col,
        students_map=students_map,   # cached for O(1) look-up
    )

    # generate QR
    qr_url  = f'{BASE_URL}scan/{session_id}'
    qr_path = os.path.join(qr_folder, f'{session_id}.png')
    qrcode.make(qr_url).save(qr_path)

    return render_template(
        'qr_display.html',
        qr_path=f'qr/{session_id}.png',
        session_id=session_id
    )


# ---------------------------------------------------------------------------
#  Student enters roll number
# ---------------------------------------------------------------------------
@app.route('/scan/<session_id>', methods=['GET', 'POST'])
def scan(session_id):
    session = sessions.get(session_id)
    if not session:
        return 'Invalid session ID'

    roll_col  = session['roll_col']
    name_col  = session['name_col']
    students  = session['students_map']        # dict: normalized roll → row-dict

    # ----------------------------- POST
    if request.method == 'POST':
        entered_roll = normalize_roll(request.form.get('roll_number', ''))

        if not entered_roll:
            return render_template(
                'roll_entry.html',
                session_id=session_id,
                roll_col=roll_col,
                error='Please enter a roll number.'
            )

        matched = students.get(entered_roll)

        if not matched:
            return render_template(
                'roll_entry.html',
                session_id=session_id,
                roll_col=roll_col,
                error='Roll number not found. Try again.'
            )

        # Found → go to confirmation page
        return render_template(
            'confirm_details.html',
            student=matched,
            session_id=session_id,
            roll_col=roll_col,
            name_col=name_col
        )

    # ----------------------------- GET
    return render_template(
        'roll_entry.html',
        session_id=session_id,
        roll_col=roll_col,
        error=None
    )


# ---------------------------------------------------------------------------
#  Student confirms & attendance is stored
# ---------------------------------------------------------------------------
@app.route('/mark', methods=['POST'])
def mark_attendance():
    session_id = request.form.get('session_id')
    roll       = request.form.get('roll_number', '').strip()
    name       = request.form.get('name', '').strip()
    lat        = request.form.get('latitude')
    lon        = request.form.get('longitude')

    # 1. Location required
    if not (lat and lon):
        return render_template(
            'confirm_attendance.html',
            message='❌ Location permission is required to mark attendance.'
        )

    try:
        lat, lon = map(float, (lat, lon))
    except ValueError:
        return render_template(
            'confirm_attendance.html',
            message='❌ Invalid latitude/longitude.'
        )

    session = sessions.get(session_id)
    if not session:
        return render_template(
            'confirm_attendance.html',
            message='❌ Invalid session. Please rescan the QR code.'
        )

    # 2. Geo-fence check
    dist = haversine(lat, lon, session['latitude'], session['longitude'])
    if dist > session['radius']:
        return render_template(
            'confirm_attendance.html',
            message=f'❌ Outside allowed area ({dist:.1f} m).'
        )

    # 3. Double-mark prevention
    attendance.setdefault(session_id, [])
    if any(normalize_roll(rec['roll']) == normalize_roll(roll) for rec in attendance[session_id]):
        return render_template(
            'confirm_attendance.html',
            message='⚠️ Attendance already marked for this roll number.'
        )

    # 4. Record attendance
    timestamp = datetime.now(timezone('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S')
    attendance[session_id].append(dict(name=name, roll=roll, timestamp=timestamp))

    return render_template(
        'confirm_attendance.html',
        message='✅ Attendance marked successfully!'
    )


# ---------------------------------------------------------------------------
#  Teacher downloads final CSV with extra date column
# ---------------------------------------------------------------------------
@app.route('/download/<session_id>')
def download(session_id):
    session = sessions.get(session_id)
    if not session:
        return 'Invalid session.'

    if session_id not in attendance or not attendance[session_id]:
        return 'No attendance recorded yet.'

    df = pd.read_csv(session['filename'])
    col_name = datetime.now(timezone('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S')

    present = {normalize_roll(rec['roll']): 1 for rec in attendance[session_id]}
    df[col_name] = df[df.columns[0]].apply(
        lambda r: present.get(normalize_roll(r), 0)
    )

    buf = BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    return send_file(
        buf,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'attendance_{session_id}.csv'
    )


# ---------------------------------------------------------------------------
if __name__ == '__main__':
    # On Render, the platform supplies PORT; default to 5000 for local runs.
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
