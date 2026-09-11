from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os, json, time
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "ZONDI_SUPER_SECRET_2026"
from datetime import timedelta
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config['SESSION_PERMANENT'] = True

# === DEV PORTAL PASSWORD YOU REQUESTED ===
DEV_PORTAL_PASSWORD = "zondi@123"

locations = {}
radio_messages = []
user_channels = {}
EVIDENCE = "static/evidence"
os.makedirs(EVIDENCE, exist_ok=True)
UPLOAD_FOLDER = EVIDENCE
USERS_FILE = "users.json"

def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, 'r') as f:
            data = json.load(f)
            # if file is empty, don't overwrite with defaults
            if not data:
                return {}
            return data
    except:
        return {}

def save_users(users):
    with open(USERS_FILE, 'w') as f: json.dump(users, f, indent=2)

@app.route('/')
def home():
    if 'user' in session:
        return redirect('/dashboard')
    return render_template('login.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')
    user = request.form.get('username').strip()
    pw = request.form.get('password')
    users = load_users()
    if user in users and check_password_hash(users[user]['password'], pw):
        session['user'] = user
        session['role'] = users[user]['role']
        return redirect('/dashboard')
    return render_template('login.html', error="❌ Invalid username or password")

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'GET':
        return render_template('register.html')
    username = request.form.get('username').strip()
    email = request.form.get('email').strip()
    password = request.form.get('password')
    role = request.form.get('role')
    users = load_users()
    if username in users:
        return render_template('register.html', error="User already exists")
    if len(password) < 6:
        return render_template('register.html', error="Password must be 6+ characters")
    users[username] = {
        "password": generate_password_hash(password),
        "role": role,
        "email": email,
        "created": datetime.now().isoformat()
    }
    save_users(users)
    return render_template('login.html', success=f"✅ Account {username} created!")

@app.route('/forgot', methods=['GET','POST'])
def forgot():
    if request.method == 'GET':
        return render_template('forgot.html')
    username = request.form.get('username').strip()
    new_pw = request.form.get('new_password')
    confirm = request.form.get('confirm_password')
    users = load_users()
    if username not in users:
        return render_template('forgot.html', error="Username not found")
    if new_pw!= confirm:
        return render_template('forgot.html', error="Passwords don't match")
    users[username]['password'] = generate_password_hash(new_pw)
    save_users(users)
    return render_template('login.html', success="✅ Password reset!")

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect('/login')
    role = session.get('role')
    user = session.get('user')
    if role == 'client':
        return render_template('client.html', user=user)
    elif role == 'patrol':
        return render_template('hq.html', locations=locations, user=user)
    else:
        # dev role user dashboard
        files = os.listdir('evidence')
        all_users = load_users()
        return render_template('dev.html', locations=locations, files=files, user=user, all_users=all_users)

# ====== FIXED VISIBLE DEV PORTAL WITH SINGLE PASSWORD ======
@app.route('/dev', methods=['GET','POST'])
def dev_portal():
    # If already unlocked via dev password
    if session.get('dev_auth') == True:
        files = os.listdir(EVIDENCE)
        all_users = load_users()
        return render_template('dev.html', locations=locations, files=files, user="DEV-PORTAL", all_users=all_users, radio_messages=radio_messages)

    if request.method == 'POST':
        pw = request.form.get('devpass')
        if pw == DEV_PORTAL_PASSWORD:
            session['dev_auth'] = True
            files = os.listdir(EVIDENCE)
            all_users = load_users()
            return render_template('dev.html', locations=locations, files=files, user="DEV-PORTAL", all_users=all_users, radio_messages=radio_messages)
        else:
            return render_template('dev_login.html', error="❌ Wrong Dev Password")

    return render_template('dev_login.html')

@app.route('/dev/logout')
def dev_logout():
    session.pop('dev_auth', None)
    return redirect('/dev')

# KEEP YOUR WORKING ROUTES
@app.route('/update_location', methods=['POST'])
def update_location():
    data = request.json
    locations[data.get('user')] = {"lat": data.get('lat'), "lng": data.get('lng'), "time": datetime.now().strftime("%H:%M:%S")}
    return jsonify({"ok": True})

@app.route('/trigger', methods=['POST'])
def trigger():
    user = session.get('user','unknown')
    now = datetime.now().strftime("%H:%M:%S")
    radio_messages.append({"user": user, "text": f"🚨 PANIC ALERT FROM {user.upper()}!", "type": "panic", "time": now, "file": None})
    return jsonify({"status":"PANIC RECEIVED"})

@app.route('/upload_evidence', methods=['POST'])
def upload_evidence():
    video = request.files.get('video')
    user = session.get('user','unknown')
    if video:
        fname = f"PANIC_{user}_{int(time.time())}.webm"
        path = os.path.join(EVIDENCE, fname)
        video.save(path)
        print(f"✅ Evidence saved to dev: {path}")
        return jsonify(ok=True, file=fname)
    return jsonify(error="no video"),400

@app.route('/send_radio', methods=['POST'])
def send_radio():
    user = session.get('user','unknown')
    text = request.form.get('text','')
    now = datetime.now().strftime("%H:%M:%S")
    filename = None
    if 'audio' in request.files:
        af = request.files['audio']
        filename = f"RADIO_{user}_{now.replace(':','')}.webm"
        af.save(os.path.join("evidence", filename))
    cur_ch = user_channels.get(user, 1)
    radio_messages.append({"user": user, "text": text, "type": "audio" if filename else "text", "file": filename, "channel": cur_ch, "time": now})
    return jsonify({"ok": True})

@app.route('/set_channel/<int:ch>')
def set_channel(ch):
    user_channels[session.get('user','guest')] = ch
    return 'ok'

@app.route('/get_radio')
def get_radio():
    u = session.get('user','guest')
    ch = user_channels.get(u, 1)
    filtered = [r for r in radio_messages if r.get('channel',1)==ch]
    return jsonify(filtered[-20:])

@app.route('/get_locations')
def get_locations(): return jsonify(locations)

@app.route('/evidence/<path:filename>')
def evidence_file(filename):
    return send_from_directory("evidence", filename)

@app.route('/logout')
def logout(): session.clear(); return redirect('/login')

@app.route('/api/radio/upload', methods=['POST'])
def radio_upload():
    file = request.files['audio']
    channel = request.form.get('channel', 'ch1')
    user = request.form.get('user', 'HQ')
    filename = f"{int(time.time()*1000)}_{secure_filename(file.filename)}"
    path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(path)
    msg = {'audioUrl': f'/{UPLOAD_FOLDER}/{filename}', 'channel': channel, 'user': user, 'time': int(time.time())}
    radio_messages.append(msg)
    return jsonify(msg)

@app.route('/api/radio/feed')
def radio_feed():
    channel = request.args.get('channel','ch1')
    if channel == 'ch_all':
        return jsonify(radio_messages[-30:])
    filtered = [m for m in radio_messages if m.get('channel',None) in [channel, 'ch_all'] or 'channel' not in m]
    return jsonify(filtered[-30:])

@app.route('/static/radio/<filename>')
def serve_radio(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

if __name__ == '__main__':
    load_users()
    print("ZPS V4 - ENCRYPTED AUTH + DEV PORTAL zondi@123 READY")
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)), debug=True)
