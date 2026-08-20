from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os, json

app = Flask(__name__)
app.secret_key = "zondi_super_secret_2026_encrypted"

locations = {}
radio_messages = []
user_channels = {}  # username -> channel
os.makedirs("evidence", exist_ok=True)
os.makedirs("static", exist_ok=True)

USERS_FILE = "users.json"

def load_users():
    if not os.path.exists(USERS_FILE):
        default = {
            "client01": {"password": generate_password_hash("client123"), "role": "client", "email": "client@zps.co.za"},
            "patrol01": {"password": generate_password_hash("patrol123"), "role": "patrol", "email": "patrol@zps.co.za"},
            "zondi_dev": {"password": generate_password_hash("zondi123"), "role": "dev", "email": "dev@zps.co.za"}
        }
        with open(USERS_FILE, 'w') as f: json.dump(default, f, indent=2)
        return default
    with open(USERS_FILE, 'r') as f: return json.load(f)

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
    return render_template('login.html', error="❌ Invalid username or password - Encrypted check failed")

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
    print(f"✅ NEW USER REGISTERED: {username} as {role} - ENCRYPTED")
    return render_template('login.html', success=f"✅ Account {username} created! Login with encrypted password")

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
    if len(new_pw) < 6:
        return render_template('forgot.html', error="Password too short")
    users[username]['password'] = generate_password_hash(new_pw)
    save_users(users)
    print(f"🔑 PASSWORD RESET FOR {username}")
    return render_template('login.html', success="✅ Password reset! Login with new encrypted password")

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
        files = os.listdir('evidence')
        users = load_users()
        return render_template('dev.html', locations=locations, files=files, user=user, all_users=users)

#... KEEP YOUR WORKING ROUTES...
@app.route('/update_location', methods=['POST'])
def update_location():
    data = request.json
    locations[data.get('user')] = {"lat": data.get('lat'), "lng": data.get('lng'), "time": datetime.now().strftime("%H:%M:%S")}
    return jsonify({"ok": True})

@app.route('/trigger', methods=['POST'])
def trigger():
    user = session.get('user','unknown')
    now = datetime.now().strftime("%H:%M:%S")
    radio_messages.append({"user": user, "text": f"🚨🚨 PANIC ALERT FROM {user.upper()} - NEEDS IMMEDIATE RESPONSE! 🚨🚨", "type": "panic", "time": now, "file": None})
    return jsonify({"status":"PANIC RECEIVED"})

@app.route('/upload_evidence', methods=['POST'])
def upload_evidence():
    user = session.get('user','unknown')
    if 'video' in request.files:
        f = request.files['video']
        name = f"ZONDI_{user}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.webm"
        f.save(os.path.join("evidence", name))
        return jsonify({"saved": name})
    return jsonify({"error":"no video"})

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

user_channels = {}

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

import os, time
from flask import request, jsonify
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = 'static/radio'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
radio_messages = []

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
    filtered = [m for m in radio_messages if m['channel']==channel or m['channel']=='ch_all']
    return jsonify(filtered[-30:])

@app.route('/static/radio/<filename>')
def serve_radio(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

if __name__ == '__main__':
    load_users()
    print("ZPS V4 - ENCRYPTED AUTH READY")
    app.run(host='0.0.0.0', port=5000, debug=True)