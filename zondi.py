import os, json, time
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, session, redirect, send_from_directory
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__)
app.secret_key = "ZONDI_2026_SECRET"
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

# use threading so Render free doesn't crash
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

locations = {}
groups = {}
EVIDENCE = "evidence"
os.makedirs(EVIDENCE, exist_ok=True)
USERS_FILE = "users.json"
GROUPS_FILE = "groups.json"

def load_users():
    if not os.path.exists(USERS_FILE): return {}
    try: return json.load(open(USERS_FILE,'r'))
    except: return {}

def save_users(u): json.dump(u, open(USERS_FILE,'w'), indent=2)

def load_groups():
    if not os.path.exists(GROUPS_FILE):
        default = {
            "patrol": {"name":"🚓 Patrol Unit","members":[],"messages":[]},
            "tactical": {"name":"⚡ Tactical","members":[],"messages":[]},
            "command": {"name":"🏛️ Command","members":[],"messages":[]}
        }
        json.dump(default, open(GROUPS_FILE,'w'), indent=2)
        return default
    try: return json.load(open(GROUPS_FILE,'r'))
    except: return {}

def save_groups_func(): json.dump(groups, open(GROUPS_FILE,'w'), indent=2)

groups = load_groups()

@app.route('/')
def home():
    if 'user' in session: return redirect('/dashboard')
    return render_template('login.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='GET': return render_template('login.html')
    u = request.form.get('username','').strip()
    p = request.form.get('password','')
    users = load_users()
    # support both hashed and plain
    if u in users:
        stored = users[u].get('password','')
        ok = False
        if stored == p: ok = True
        else:
            try:
                from werkzeug.security import check_password_hash
                if check_password_hash(stored, p): ok=True
            except: pass
        if ok:
            session['user']=u; session['role']=users[u].get('role','patrol'); session.permanent=True
            return redirect('/dashboard')
    return render_template('login.html', error="Invalid login")

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method=='GET': return render_template('register.html')
    username = request.form.get('username','').strip()
    email = request.form.get('email','').strip()
    password = request.form.get('password','')
    role = request.form.get('role','patrol')
    users = load_users()
    if username in users: return render_template('register.html', error="Exists")
    users[username]={"password":password,"role":role,"email":email,"created":datetime.now().isoformat()}
    save_users(users)
    return render_template('login.html', success="Created! Login")

@app.route('/dashboard')
def dashboard():
    if 'user' not in session: return redirect('/')
    role=session.get('role'); user=session.get('user')
    if role=='client': return render_template('client.html', user=user)
    elif role=='patrol': return render_template('hq.html', user=user)
    else:
        files=os.listdir(EVIDENCE)
        return render_template('dev.html', locations=locations, files=files, user=user, all_users=load_users(), radio_messages=[], groups=groups)

@app.route('/update_location', methods=['POST'])
def update_location():
    data=request.json; user=data.get('user', session.get('user','unknown'))
    locations[user]={"lat":data.get('lat'),"lng":data.get('lng'),"time":datetime.now().strftime("%H:%M:%S")}
    socketio.emit('location_update', {'user':user,'location':locations[user]}, broadcast=True)
    return jsonify(ok=True)

@app.route('/evidence/<path:filename>')
def evidence_file(filename): return send_from_directory(EVIDENCE, filename)

@app.route('/logout')
def logout(): session.clear(); return redirect('/')

# ---- NEW WHATSAPP API ----
@app.route('/api/groups')
def api_groups(): return jsonify(groups)

@app.route('/api/create_group', methods=['POST'])
def api_create_group():
    global groups
    data=request.get_json(); gid=data.get('id','').lower().strip().replace(' ','_'); name=data.get('name','').strip()
    if not gid or not name: return jsonify(ok=False, error="need id and name")
    if gid in groups: return jsonify(ok=False, error="ID exists")
    groups[gid]={"name":name,"members":[session.get('user')], "messages":[]}
    save_groups_func()
    socketio.emit('groups_updated', groups, broadcast=True)
    return jsonify(ok=True, groups=groups)

@app.route('/api/send_text', methods=['POST'])
def api_send_text():
    data=request.get_json(); gid=data.get('group'); text=data.get('text','').strip()
    if gid not in groups or not text: return jsonify(ok=False)
    msg={"user":session.get('user'),"text":text,"type":"text","time":datetime.now().strftime("%H:%M"),"file":None}
    groups[gid]['messages'].append(msg); groups[gid]['messages']=groups[gid]['messages'][-200:]; save_groups_func()
    socketio.emit('new_msg', {"group":gid,"msg":msg}, room=gid, broadcast=True)
    socketio.emit('new_msg', {"group":gid,"msg":msg}, broadcast=True)
    return jsonify(ok=True)

@app.route('/api/send_voice', methods=['POST'])
def api_send_voice():
    f=request.files.get('voice'); gid=request.form.get('group','patrol')
    if gid not in groups: return jsonify(ok=False, error="no group"),404
    if not f: return jsonify(ok=False, error="no file"),400
    data=f.read()
    print(f"VOICE size {len(data)} for {gid}")
    if len(data)<500: return jsonify(ok=False, error="too short"),400
    fname=f"VOICE_{gid}_{session.get('user')}_{int(time.time())}.webm"
    open(os.path.join(EVIDENCE,fname),'wb').write(data)
    msg={"user":session.get('user'),"text":"🎙️ Voice","type":"audio","time":datetime.now().strftime("%H:%M"),"file":fname}
    groups[gid]['messages'].append(msg); save_groups_func()
    socketio.emit('new_msg', {"group":gid,"msg":msg}, room=gid, broadcast=True)
    socketio.emit('new_msg', {"group":gid,"msg":msg}, broadcast=True)
    return jsonify(ok=True)

@app.route('/api/group_messages/<gid>')
def api_group_messages(gid):
    if gid not in groups: return jsonify([])
    return jsonify(groups[gid]['messages'][-50:])

@socketio.on('join_group')
def handle_join(data):
    gid=data.get('group')
    if gid: join_room(gid); print(f"{session.get('user')} joined {gid}")

@socketio.on('location_update')
def handle_loc(data):
    user=session.get('user','unknown'); locations[user]=data
    emit('location_update', {'user':user,'location':data}, broadcast=True, include_self=False)

if __name__=='__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
