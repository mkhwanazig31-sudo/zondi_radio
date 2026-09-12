from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_from_directory
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os, json, time
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "ZONDI_SUPER_SECRET_2026"
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config['SESSION_PERMANENT'] = True

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

DEV_PORTAL_PASSWORD = "zondi@123"

# Global state
locations = {}
radio_messages = []
user_channels = {}
active_users = {}
ptt_active = {}
panic_alerts = []

EVIDENCE = "evidence"
os.makedirs(EVIDENCE, exist_ok=True)
USERS_FILE = "users.json"
GROUPS_FILE = "groups.json"

def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, 'r') as f:
            data = json.load(f)
            return data if data else {}
    except:
        return {}

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)

def load_groups():
    if not os.path.exists(GROUPS_FILE):
        default = {
            "patrol": {"name": "Patrol Unit", "members": [], "messages": [], "created_by": "system", "created_at": datetime.now().isoformat()},
            "tactical": {"name": "Tactical Unit", "members": [], "messages": [], "created_by": "system", "created_at": datetime.now().isoformat()},
            "command": {"name": "Command Center", "members": [], "messages": [], "created_by": "system", "created_at": datetime.now().isoformat()}
        }
        json.dump(default, open(GROUPS_FILE,'w'), indent=2)
        return default
    try:
        with open(GROUPS_FILE,'r') as f:
            data = json.load(f)
            return data if data else {}
    except:
        return {}

def save_groups():
    with open(GROUPS_FILE,'w') as f:
        json.dump(groups, f, indent=2)

groups = load_groups()

@app.route('/')
def home():
    if 'user' in session:
        return redirect('/dashboard')
    return render_template('login.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')
    user = request.form.get('username','').strip()
    pw = request.form.get('password','')
    users = load_users()
    if user in users and check_password_hash(users[user]['password'], pw):
        session['user'] = user
        session['role'] = users[user]['role']
        session.permanent = True
        return redirect('/dashboard')
    return render_template('login.html', error="❌ Invalid username or password")

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'GET':
        return render_template('register.html')
    username = request.form.get('username','').strip()
    email = request.form.get('email','').strip()
    password = request.form.get('password','')
    role = request.form.get('role','')
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
    username = request.form.get('username','').strip()
    new_pw = request.form.get('new_password','')
    confirm = request.form.get('confirm_password','')
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
        files = os.listdir(EVIDENCE) if os.path.exists(EVIDENCE) else []
        all_users = load_users()
        return render_template('dev.html', locations=locations, files=files, user=user, all_users=all_users, radio_messages=radio_messages, panic_alerts=panic_alerts, groups=groups)

@app.route('/dev', methods=['GET','POST'])
def dev_portal():
    if session.get('dev_auth') == True:
        files = os.listdir(EVIDENCE) if os.path.exists(EVIDENCE) else []
        all_users = load_users()
        return render_template('dev.html', locations=locations, files=files, user="DEV-PORTAL", all_users=all_users, radio_messages=radio_messages, panic_alerts=panic_alerts, groups=groups)
    if request.method == 'POST':
        pw = request.form.get('devpass')
        if pw == DEV_PORTAL_PASSWORD:
            session['dev_auth'] = True
            files = os.listdir(EVIDENCE) if os.path.exists(EVIDENCE) else []
            all_users = load_users()
            return render_template('dev.html', locations=locations, files=files, user="DEV-PORTAL", all_users=all_users, radio_messages=radio_messages, panic_alerts=panic_alerts, groups=groups)
        else:
            return render_template('dev_login.html', error="❌ Wrong Dev Password")
    return render_template('dev_login.html')

@app.route('/dev/logout')
def dev_logout():
    session.pop('dev_auth', None)
    return redirect('/dev')

@app.route('/update_location', methods=['POST'])
def update_location():
    data = request.json
    user = data.get('user', session.get('user','unknown'))
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
    user = session.get('user','unknown')
    now = datetime.now().strftime("%H:%M:%S")
    panic_data = {
        "user": user,
        "time": now,
        "location": locations.get(user, {"lat":0,"lng":0}),
        "message": f"🚨 PANIC ALERT FROM {user.upper()}!"
    }
    panic_alerts.append(panic_data)
    for gid in groups:
        groups[gid]['messages'].append({"user":user,"text":f"🚨 PANIC ALERT FROM {user.upper()}!","type":"panic","time":now,"file":None})
    save_groups()
    socketio.emit('panic_alert', panic_data, broadcast=True)
    return jsonify({"status":"PANIC RECEIVED"})

@app.route('/upload_evidence', methods=['POST'])
def upload_evidence():
    video = request.files.get('video')
    user = session.get('user','unknown')
    if video:
        fname = f"CLIENT_{user}_{int(time.time())}.webm"
        path = os.path.join(EVIDENCE, fname)
        video.save(path)
        socketio.emit('evidence_uploaded', {'user': user, 'file': fname}, broadcast=True)
        return jsonify(ok=True, file=fname)
    return jsonify(error="no video"), 400

@app.route('/set_channel/<int:ch>')
def set_channel(ch):
    user = session.get('user','guest')
    user_channels[user] = ch
    return 'ok'

@app.route('/get_radio')
def get_radio():
    u = session.get('user','guest')
    ch = user_channels.get(u,1)
    filtered = [r for r in radio_messages if r.get('channel',1)==ch]
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

# NEW WHATSAPP API
@app.route('/api/groups')
def api_groups():
    return jsonify(groups)

@app.route('/api/create_group', methods=['POST'])
def api_create_group():
    global groups
    data = request.get_json()
    gid = data.get('id','').lower().strip().replace(' ','_')
    name = data.get('name','').strip()
    if not gid or not name:
        return jsonify(ok=False, error="id and name required")
    if gid in groups:
        return jsonify(ok=False, error="Group ID exists")
    groups[gid] = {"name":name, "members":[session.get('user')], "messages":[], "created_by":session.get('user'), "created_at":datetime.now().isoformat()}
    save_groups()
    socketio.emit('groups_updated', groups, broadcast=True)
    return jsonify(ok=True, groups=groups)

@app.route('/api/join_group/<gid>')
def api_join_group(gid):
    if gid not in groups:
        return jsonify(ok=False)
    u = session.get('user')
    if u not in groups[gid]['members']:
        groups[gid]['members'].append(u)
        save_groups()
        socketio.emit('groups_updated', groups, broadcast=True)
    return jsonify(ok=True)

@app.route('/api/send_text', methods=['POST'])
def api_send_text():
    data = request.get_json()
    gid = data.get('group')
    text = data.get('text','').strip()
    if gid not in groups or not text:
        return jsonify(ok=False)
    msg = {"user":session.get('user'), "text":text, "type":"text", "time":datetime.now().strftime("%H:%M"), "file":None}
    groups[gid]['messages'].append(msg)
    if len(groups[gid]['messages'])>200:
        groups[gid]['messages']=groups[gid]['messages'][-200:]
    save_groups()
    socketio.emit('new_msg', {"group":gid, "msg":msg}, room=gid, broadcast=True)
    socketio.emit('new_msg_global', {"group":gid, "msg":msg}, broadcast=True)
    return jsonify(ok=True)

@app.route('/api/send_voice', methods=['POST'])
def api_send_voice():
    f = request.files.get('voice')
    gid = request.form.get('group','patrol')
    if gid not in groups:
        return jsonify(ok=False, error="group not found"), 404
    if not f:
        return jsonify(ok=False, error="no file"), 400
    data = f.read()
    print(f"VOICE UPLOAD: group={gid} size={len(data)}")
    if len(data)<500:
        return jsonify(ok=False, error="too short"), 400
    fname = f"VOICE_{gid}_{session.get('user')}_{int(time.time())}.webm"
    open(os.path.join(EVIDENCE,fname),'wb').write(data)
    msg = {"user":session.get('user'), "text":"🎙️ Voice", "type":"audio", "time":datetime.now().strftime("%H:%M"), "file":fname}
    groups[gid]['messages'].append(msg)
    save_groups()
    socketio.emit('new_msg', {"group":gid, "msg":msg}, room=gid, broadcast=True)
    socketio.emit('new_msg_global', {"group":gid, "msg":msg}, broadcast=True)
    return jsonify(ok=True, file=fname)

@app.route('/api/group_messages/<gid>')
def api_group_messages(gid):
    if gid not in groups:
        return jsonify([])
    return jsonify(groups[gid]['messages'][-50:])

@socketio.on('connect')
def handle_connect():
    user = session.get('user','unknown')
    role = session.get('role','unknown')
    active_users[user] = {'role': role, 'sid': request.sid}
    print(f"✅ {user} ({role}) connected")

@socketio.on('disconnect')
def handle_disconnect():
    user = session.get('user','unknown')
    if user in active_users:
        del active_users[user]
    print(f"❌ {user} disconnected")

@socketio.on('join_group')
def handle_join_group(data):
    gid = data.get('group')
    if gid:
        join_room(gid)
        print(f"{session.get('user')} joined {gid}")

@socketio.on('leave_group')
def handle_leave_group(data):
    gid = data.get('group')
    if gid:
        leave_room(gid)

@socketio.on('location_update')
def handle_location_update(data):
    user = session.get('user','unknown')
    locations[user]=data
    emit('location_update', {'user':user,'location':data}, broadcast=True, include_self=False)

if __name__ == '__main__':
    print("🚨 ZONDI WHATSAPP SYSTEM READY")
    print(" - Groups:", list(groups.keys()))
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
