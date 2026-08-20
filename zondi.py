from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_from_directory, Response
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import os, json, time

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "zondi_super_secret_2026_encrypted")

# --- UNIFIED CENTRAL TELEMETRY CORE STORES ---
locations = {}
radio_messages = []
user_channels = {}  # username -> channel

EVIDENCE_FOLDER = "evidence"
RADIO_FOLDER = os.path.join("static", "radio")
os.makedirs(EVIDENCE_FOLDER, exist_ok=True)
os.makedirs(RADIO_FOLDER, exist_ok=True)
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


# --- AUTHENTICATION INFRASTRUCTURE ENGINE ---
@app.route('/')
def home():
    if 'user' in session:
        return redirect('/dashboard')
    return render_template('login.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')
   
    username_input = request.form.get('username')
    if not username_input:
        return render_template('login.html', error="❌ Username field missing")
       
    user = username_input.strip()
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
   
    username_input = request.form.get('username')
    email_input = request.form.get('email')
   
    username = username_input.strip() if username_input else ""
    email = email_input.strip() if email_input else ""
    password = request.form.get('password')
    role = request.form.get('role')
    users = load_users()
   
    if username in users:
        return render_template('register.html', error="User already exists")
    if not password or len(password) < 6:
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
       
    username_input = request.form.get('username')
    username = username_input.strip() if username_input else ""
    new_pw = request.form.get('new_password')
   
    users = load_users()
    if username not in users:
        return render_template('forgot.html', error="Username not found")
    if not new_pw or len(new_pw) < 6:
        return render_template('forgot.html', error="Password too short")
       
    users[username]['password'] = generate_password_hash(new_pw)
    save_users(users)
    return render_template('login.html', success="✅ Password reset successfully!")


# --- ROUTING SYSTEM CROSSWAY DISPATCHER ---
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
        files = os.listdir(EVIDENCE_FOLDER)
        users = load_users()
        return render_template('dev.html', locations=locations, files=files, user=user, all_users=users)


# --- COMMUNICATIONS ENGINE & STREAM CHANNELS ---
@app.route('/update_location', methods=['POST'])
def update_location():
    data = request.json
    if data:
        locations[data.get('user')] = {
            "lat": data.get('lat'),
            "lng": data.get('lng'),
            "time": datetime.now().strftime("%H:%M:%S")
        }
    return jsonify({"ok": True})

@app.route('/trigger', methods=['POST'])
@app.route('/api/radio/panic', methods=['POST'])
def trigger():
    user = session.get('user', 'unknown')
    msg = {
        "user": user,
        "text": f"🚨🚨 PANIC ALERT FROM {user.upper()} - NEEDS IMMEDIATE RESPONSE! 🚨🚨",
        "type": "CLIENT_SOS",
        "status": "EMERGENCY_SOS",
        "time": int(time.time()),
        "audioUrl": None
    }
    radio_messages.append(msg)
    return jsonify({"status": "PANIC RECEIVED", "ok": True})

@app.route('/upload_evidence', methods=['POST'])
def upload_evidence():
    user = session.get('user', 'unknown')
    if 'video' in request.files:
        f = request.files['video']
        name = f"ZONDI_{user}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.webm"
        f.save(os.path.join(EVIDENCE_FOLDER, name))
        return jsonify({"saved": name})
    return jsonify({"error": "no video"})

@app.route('/upload_audio', methods=['POST'])
@app.route('/api/radio/upload', methods=['POST'])
def radio_upload():
    file_key = 'audio' if 'audio' in request.files else 'audio[]'
    if file_key not in request.files:
        return jsonify({"error": "No audio file payload found"}), 400
      
    file = request.files[file_key]
    channel = request.form.get('channel', '1')
    user = request.form.get('user', session.get('user', 'HQ-DISPATCH'))
   
    filename = f"{int(time.time()*1000)}_{secure_filename(file.filename)}"
    path = os.path.join(RADIO_FOLDER, filename)
    file.save(path)
   
    msg = {
        'audioUrl': f'/static/radio/{filename}',
        'channel': channel,
        'user': user,
        'time': int(time.time()),
        'type': 'audio'
    }
    radio_messages.append(msg)
    return jsonify(msg)

@app.route('/api/radio/feed')
@app.route('/get_radio')
def radio_feed():
    u = session.get('user', 'guest')
    channel = request.args.get('channel', str(user_channels.get(u, 1)))
   
    if channel == 'ch_all' or channel == 'all':
        return jsonify(radio_messages[-30:])
       
    filtered = [m for m in radio_messages if str(m.get('channel')) == str(channel)]
    return jsonify(filtered[-30:])

@app.route('/get_locations')
def get_locations():
    return jsonify(locations)

@app.route('/evidence/<path:filename>')
def evidence_file(filename):
    return send_from_directory(EVIDENCE_FOLDER, filename)

# FIX: Range-Requests safely stream byte snippets to stop browser loop locks
@app.route('/static/radio/<filename>')
def serve_radio(filename):
    file_path = os.path.join(RADIO_FOLDER, filename)
    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404
        
    file_size = os.path.getsize(file_path)
    range_header = request.headers.get('Range', None)
    
    if not range_header:
        def stream_full():
            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(8192)
                    if not chunk: break
                    yield chunk
        return Response(stream_full(), mimetype="audio/webm", headers={"Accept-Ranges": "bytes"})
        
    byte_str = range_header.replace('bytes=', '')
    start_str, end_str = byte_str.split('-')
    
    start = int(start_str) if start_str else 0
    end = int(end_str) if end_str else file_size - 1
    if end >= file_size: end = file_size - 1
    
    length = end - start + 1
    
    def generate_range(start_byte, length_bytes):
        with open(file_path, "rb") as f:
            f.seek(start_byte)
            remaining = length_bytes
            while remaining > 0:
                chunk_size = min(8192, remaining)
                chunk = f.read(chunk_size)
                if not chunk: break
                remaining -= len(chunk)
                yield chunk

    rv = Response(generate_range(start, length), 206, mimetype="audio/webm", direct_passthrough=True)
    rv.headers.add('Content-Range', f'bytes {start}-{end}/{file_size}')
    rv.headers.add('Accept-Ranges', 'bytes')
    rv.headers.add('Content-Length', str(length))
    return rv

@app.route('/set_channel/<int:ch>')
def set_channel(ch):
    user_channels[session.get('user', 'guest')] = ch
    return 'ok'

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

if __name__ == '__main__':
    load_users()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'GET':
        return render_template('register.html')
  
    username_input = request.form.get('username')
    email_input = request.form.get('email')
  
    username = username_input.strip() if username_input else ""
    email = email_input.strip() if email_input else ""
    password = request.form.get('password')
    role = request.form.get('role')
    users = load_users()
  
    if username in users:
        return render_template('register.html', error="User already exists")
    if not password or len(password) < 6:
        return render_template('register.html', error="Password must be 6+ characters")
      
    users[username] = {
        "password": generate_password_hash(password),
        "role": role,
        "email": email,
        "created": datetime.now().isoformat()
    }
    save_users(users)
    print(f"✅ NEW USER REGISTERED: {username} as {role} - ENCRYPTED")
    return render_template('login.html', success=f"✅ Account {username} created!")

@app.route('/forgot', methods=['GET','POST'])
def forgot():
    if request.method == 'GET':
        return render_template('forgot.html')
      
    username_input = request.form.get('username')
    username = username_input.strip() if username_input else ""
    new_pw = request.form.get('new_password')
  
    users = load_users()
    if username not in users:
        return render_template('forgot.html', error="Username not found")
    if not new_pw or len(new_pw) < 6:
        return render_template('forgot.html', error="Password too short")
      
    users[username]['password'] = generate_password_hash(new_pw)
    save_users(users)
    print(f"🔑 PASSWORD RESET FOR {username}")
    return render_template('login.html', success="✅ Password reset successfully!")


# --- ROUTING SYSTEM CROSSWAY DISPATCHER ---
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
        files = os.listdir(EVIDENCE_FOLDER)
        users = load_users()
        return render_template('dev.html', locations=locations, files=files, user=user, all_users=users)


# --- COMMUNICATIONS ENGINE & STREAM CHANNELS ---
@app.route('/update_location', methods=['POST'])
def update_location():
    data = request.json
    if data:
        locations[data.get('user')] = {
            "lat": data.get('lat'),
            "lng": data.get('lng'),
            "time": datetime.now().strftime("%H:%M:%S")
        }
    return jsonify({"ok": True})

@app.route('/trigger', methods=['POST'])
@app.route('/api/radio/panic', methods=['POST'])
def trigger():
    user = session.get('user', 'unknown')
    msg = {
        "user": user,
        "text": f"🚨🚨 PANIC ALERT FROM {user.upper()} - NEEDS IMMEDIATE RESPONSE! 🚨🚨",
        "type": "CLIENT_SOS",
        "status": "EMERGENCY_SOS",
        "time": int(time.time()),
        "audioUrl": None
    }
    radio_messages.append(msg)
    return jsonify({"status": "PANIC RECEIVED", "ok": True})

@app.route('/upload_evidence', methods=['POST'])
def upload_evidence():
    user = session.get('user', 'unknown')
    if 'video' in request.files:
        f = request.files['video']
        name = f"ZONDI_{user}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.webm"
        f.save(os.path.join(EVIDENCE_FOLDER, name))
        return jsonify({"saved": name})
    return jsonify({"error": "no video"})

@app.route('/upload_audio', methods=['POST'])
@app.route('/api/radio/upload', methods=['POST'])
def radio_upload():
    file_key = 'audio' if 'audio' in request.files else 'audio[]'
    if file_key not in request.files:
        return jsonify({"error": "No audio file payload found"}), 400
     
    file = request.files[file_key]
    channel = request.form.get('channel', '1')
    user = request.form.get('user', session.get('user', 'HQ-DISPATCH'))
  
    filename = f"{int(time.time()*1000)}_{secure_filename(file.filename)}"
    path = os.path.join(RADIO_FOLDER, filename)
    file.save(path)
  
    msg = {
        'audioUrl': f'/static/radio/{filename}',
        'channel': channel,
        'user': user,
        'time': int(time.time()),
        'type': 'audio'
    }
    radio_messages.append(msg)
    return jsonify(msg)

@app.route('/api/radio/feed')
@app.route('/get_radio')
def radio_feed():
    u = session.get('user', 'guest')
    channel = request.args.get('channel', str(user_channels.get(u, 1)))
  
    if channel == 'ch_all' or channel == 'all':
        return jsonify(radio_messages[-30:])
      
    filtered = [m for m in radio_messages if str(m.get('channel')) == str(channel)]
    return jsonify(filtered[-30:])

@app.route('/get_locations')
def get_locations():
    return jsonify(locations)

@app.route('/evidence/<path:filename>')
def evidence_file(filename):
    return send_from_directory(EVIDENCE_FOLDER, filename)

# FIX: Full HTTP-Range Request engine implemented to satisfy Chrome/Safari timeline rendering
@app.route('/static/radio/<filename>')
def serve_radio(filename):
    file_path = os.path.join(RADIO_FOLDER, filename)
    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404
       
    file_size = os.path.getsize(file_path)
    range_header = request.headers.get('Range', None)
   
    if not range_header:
        # Standard delivery if no partial ranges requested
        def stream_full():
            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(8192)
                    if not chunk: break
                    yield chunk
        return Response(stream_full(), mimetype="audio/webm", headers={"Accept-Ranges": "bytes"})
       
    # Process Byte Range Request (e.g. bytes=0-1 or bytes=0-)
    byte_str = range_header.replace('bytes=', '')
    start_str, end_str = byte_str.split('-')
   
    start = int(start_str) if start_str else 0
    end = int(end_str) if end_str else file_size - 1
    if end >= file_size: end = file_size - 1
   
    length = end - start + 1
   
    def generate_range(start_byte, length_bytes):
        with open(file_path, "rb") as f:
            f.seek(start_byte)
            remaining = length_bytes
            while remaining > 0:
                chunk_size = min(8192, remaining)
                chunk = f.read(chunk_size)
                if not chunk: break
                remaining -= len(chunk)
                yield chunk

    rv = Response(generate_range(start, length), 206, mimetype="audio/webm", direct_passthrough=True)
    rv.headers.add('Content-Range', f'bytes {start}-{end}/{file_size}')
    rv.headers.add('Accept-Ranges', 'bytes')
    rv.headers.add('Content-Length', str(length))
    return rv

@app.route('/set_channel/<int:ch>')
def set_channel(ch):
    user_channels[session.get('user', 'guest')] = ch
    return 'ok'

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


if __name__ == '__main__':
    load_users()
    print("ZPS V4 - RANGE RESILIENCE ENGINE ACTIVE")
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
