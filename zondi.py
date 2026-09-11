from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_from_directory
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os, json, time
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "ZONDI_SUPER_SECRET_2026"
from datetime import timedelta
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config['SESSION_PERMANENT'] = True

socketio = SocketIO(app, cors_allowed_origins="*")

# === DEV PORTAL PASSWORD YOU REQUESTED ===
DEV_PORTAL_PASSWORD = "zondi@123"

# Global state
locations = {}
radio_messages = []
user_channels = {}
active_users = {}  # Track active users and their roles
ptt_active = {}    # Track who's currently transmitting
panic_alerts = []  # Store panic alerts

EVIDENCE = "evidence"
os.makedirs(EVIDENCE, exist_ok=True)
UPLOAD_FOLDER = EVIDENCE
USERS_FILE = "users.json"

def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, 'r') as f:
            data = json.load(f)
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
        files = os.listdir(EVIDENCE) if os.path.exists(EVIDENCE) else []
        all_users = load_users()
        return render_template('dev.html', locations=locations, files=files, user=user, all_users=all_users, radio_messages=radio_messages, panic_alerts=panic_alerts)

# ====== VISIBLE DEV PORTAL WITH SINGLE PASSWORD ======
@app.route('/dev', methods=['GET','POST'])
def dev_portal():
    if session.get('dev_auth') == True:
        files = os.listdir(EVIDENCE) if os.path.exists(EVIDENCE) else []
        all_users = load_users()
        return render_template('dev.html', locations=locations, files=files, user="DEV-PORTAL", all_users=all_users, radio_messages=radio_messages, panic_alerts=panic_alerts)

    if request.method == 'POST':
        pw = request.form.get('devpass')
        if pw == DEV_PORTAL_PASSWORD:
            session['dev_auth'] = True
            files = os.listdir(EVIDENCE) if os.path.exists(EVIDENCE) else []
            all_users = load_users()
            return render_template('dev.html', locations=locations, files=files, user="DEV-PORTAL", all_users=all_users, radio_messages=radio_messages, panic_alerts=panic_alerts)
        else:
            return render_template('dev_login.html', error="❌ Wrong Dev Password")

    return render_template('dev_login.html')

@app.route('/dev/logout')
def dev_logout():
    session.pop('dev_auth', None)
    return redirect('/dev')

# ====== REST API ENDPOINTS ======
@app.route('/update_location', methods=['POST'])
def update_location():
    data = request.json
    user = data.get('user', session.get('user', 'unknown'))
    locations[user] = {
        "lat": data.get('lat'),
        "lng": data.get('lng'),
        "time": datetime.now().strftime("%H:%M:%S"),
        "role": "client"
    }
    socketio.emit('location_update', {'user': user, 'location': locations[user]}, broadcast=True)
    return jsonify({"ok": True})

@app.route('/trigger_panic', methods=['POST'])
def trigger_panic():
    user = session.get('user', 'unknown')
    now = datetime.now().strftime("%H:%M:%S")
    
    panic_data = {
        "user": user,
        "time": now,
        "location": locations.get(user, {"lat": 0, "lng": 0}),
        "message": f"🚨 PANIC ALERT FROM {user.upper()}!"
    }
    
    panic_alerts.append(panic_data)
    radio_messages.append({
        "user": user,
        "text": f"🚨 PANIC ALERT FROM {user.upper()}!",
        "type": "panic",
        "time": now,
        "file": None,
        "channel": "PANIC"
    })
    
    socketio.emit('panic_alert', panic_data, broadcast=True)
    return jsonify({"status": "PANIC RECEIVED"})

@app.route('/upload_evidence', methods=['POST'])
def upload_evidence():
    video = request.files.get('video')
    user = session.get('user', 'unknown')
    if video:
        fname = f"CLIENT_{user}_{int(time.time())}.webm"
        path = os.path.join(EVIDENCE, fname)
        video.save(path)
        print(f"✅ Evidence saved: {path}")
        socketio.emit('evidence_uploaded', {'user': user, 'file': fname}, broadcast=True)
        return jsonify(ok=True, file=fname)
    return jsonify(error="no video"), 400

@app.route('/set_channel/<int:ch>')
def set_channel(ch):
    user = session.get('user', 'guest')
    user_channels[user] = ch
    socketio.emit('channel_changed', {'user': user, 'channel': ch}, broadcast=True)
    return 'ok'
    
@app.route('/upload_radio', methods=['POST'])
def upload_radio():
    if 'radio' not in request.files:
        return jsonify(ok=False)
    f = request.files['radio']
    ch = int(request.form.get('channel', 1))
    user = session.get('user', 'unknown')
    fname = f"RADIO_CH{ch}_{user}_{int(time.time())}.webm"
    path = os.path.join(EVIDENCE, fname)
    f.save(path)
    now = datetime.now().strftime("%H:%M:%S")
    msg = {"user": user, "text": "🎙️ Voice message", "type": "audio", "channel": ch, "time": now, "file": fname}
    radio_messages.append(msg)
    socketio.emit('new_radio', {"channel": ch, "msg": msg}, broadcast=True)
    return jsonify(ok=True, file=fname)
    
@app.route('/get_radio')
def get_radio():
    u = session.get('user', 'guest')
    ch = user_channels.get(u, 1)
    filtered = [r for r in radio_messages if r.get('channel', 1) == ch]
    return jsonify(filtered[-20:])

@app.route('/get_locations')
def get_locations():
    return jsonify(locations)

@app.route('/get_panic_alerts')
def get_panic_alerts():
    return jsonify(panic_alerts[-10:])

@app.route('/evidence/<path:filename>')
def evidence_file(filename):
    return send_from_directory(EVIDENCE, filename)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

# ====== SOCKETIO EVENTS FOR REAL-TIME PTT RADIO ======

@socketio.on('connect')
def handle_connect():
    user = session.get('user', 'unknown')
    role = session.get('role', 'unknown')
    active_users[user] = {'role': role, 'sid': request.sid}
    print(f"✅ {user} ({role}) connected")
    socketio.emit('user_connected', {'user': user, 'role': role}, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    user = session.get('user', 'unknown')
    if user in active_users:
        del active_users[user]
    print(f"❌ {user} disconnected")
    socketio.emit('user_disconnected', {'user': user}, broadcast=True)

@socketio.on('ptt_start')
def handle_ptt_start(data):
    user = session.get('user', 'unknown')
    channel = data.get('channel', 1)
    ptt_active[user] = {'channel': channel, 'started': datetime.now().isoformat()}
    socketio.emit('ptt_active', {'user': user, 'channel': channel}, broadcast=True)
    print(f"🎙️ {user} started PTT on channel {channel}")

@socketio.on('ptt_audio_chunk')
def handle_ptt_audio(data):
    user = session.get('user', 'unknown')
    channel = user_channels.get(user, 1)
    audio_data = data.get('audio')
    socketio.emit('ptt_audio', {
        'user': user,
        'channel': channel,
        'audio': audio_data
    }, broadcast=True)

@socketio.on('ptt_end')
def handle_ptt_end(data):
    user = session.get('user', 'unknown')
    channel = user_channels.get(user, 1)
    
    if user in ptt_active:
        del ptt_active[user]
    
    now = datetime.now().strftime("%H:%M:%S")
    radio_messages.append({
        "user": user,
        "text": data.get('text', ''),
        "type": "audio",
        "channel": channel,
        "time": now,
        "file": None
    })
    
    socketio.emit('ptt_inactive', {'user': user, 'channel': channel}, broadcast=True)
    print(f"🎙️ {user} ended PTT on channel {channel}")

if __name__ == '__main__':
    load_users()
    print("🚨 ZONDI SECURITY SYSTEM V5 READY")
    print("   - CLIENT PORTAL: /dashboard (role=client)")
    print("   - HQ PORTAL: /dashboard (role=patrol)")
    print("   - DEV PORTAL: /dev (password: zondi@123)")
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get("PORT", 5000)), debug=True)
