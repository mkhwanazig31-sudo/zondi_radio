import os, json, time
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, session, redirect, send_from_directory
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__)
app.secret_key = "ZONDI_FINAL_V6"
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

locations = {}
panic_alerts = []
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

def save_groups_func():
    json.dump(groups, open(GROUPS_FILE,'w'), indent=2)

groups = load_groups()

@app.route('/')
def home():
    if 'user' in session: return redirect('/dashboard')
    return render_template('login.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='GET': return render_template('login.html')
    u=request.form.get('username','').strip(); p=request.form.get('password','')
    users=load_users()
    if u in users and users[u].get('password','')==p:
        session['user']=u; session['role']=users[u].get('role','patrol'); session.permanent=True
        return redirect('/dashboard')
    try:
        from werkzeug.security import check_password_hash
        if u in users and check_password_hash(users[u].get('password',''), p):
            session['user']=u; session['role']=users[u].get('role','patrol'); session.permanent=True
            return redirect('/dashboard')
    except: pass
    return render_template('login.html', error="Invalid")

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method=='GET': return render_template('register.html')
    u=request.form.get('username','').strip(); p=request.form.get('password',''); r=request.form.get('role','patrol')
    fullname=request.form.get('fullname','').strip(); phone=request.form.get('phone','').strip()
    users=load_users()
    if u in users: return render_template('register.html', error="Exists")
    users[u]={"password":p,"role":r,"fullname":fullname,"phone":phone,"created":datetime.now().isoformat()}
    save_users(users)
    return render_template('login.html', success="Created! Login")

@app.route('/dashboard')
def dashboard():
    if 'user' not in session: return redirect('/')
    role=session.get('role'); user=session.get('user')
    all_users=load_users()
    if role=='client': return render_template('client.html', user=user, all_users=all_users)
    elif role=='patrol': return render_template('hq.html', user=user, all_users=all_users)
    else: return render_template('dev.html', user=user, all_users=all_users, locations=locations, panic_alerts=panic_alerts, groups=groups)

@app.route('/logout')
def logout(): session.clear(); return redirect('/')
@app.route('/evidence/<path:filename>')
def ev(filename): return send_from_directory(EVIDENCE, filename)

# LOCATION + PANIC
@app.route('/update_location', methods=['POST'])
def upd_loc():
    data=request.json; user=data.get('user', session.get('user','unknown'))
    locations[user]={"lat":data.get('lat'),"lng":data.get('lng'),"time":datetime.now().strftime("%H:%M:%S"),"role":data.get('role','client')}
    socketio.emit('location_update', {'user':user,'location':locations[user]}, broadcast=True)
    return jsonify(ok=True)

@app.route('/trigger_panic', methods=['POST'])
def trigger_panic():
    user=session.get('user','unknown')
    data=request.get_json() or {}
    lat=data.get('lat'); lng=data.get('lng')
    if lat and lng:
        locations[user]={"lat":lat,"lng":lng,"time":datetime.now().strftime("%H:%M:%S"),"role":"client"}
    now=datetime.now().strftime("%H:%M:%S")
    alert={"user":user,"time":now,"location":locations.get(user,{}),"message":f"🚨 SOS FROM {user.upper()}!"}
    panic_alerts.append(alert); panic_alerts[-100:]
    # also push to all groups
    for gid in groups:
        groups[gid]['messages'].append({"user":user,"text":f"🚨 SOS EMERGENCY FROM {user.upper()}! Location: https://maps.google.com/?q={locations.get(user,{}).get('lat',0)},{locations.get(user,{}).get('lng',0)}","type":"panic","time":now,"file":None})
    save_groups_func()
    socketio.emit('panic_alert', alert, broadcast=True)
    socketio.emit('location_update', {'user':user,'location':locations.get(user, {})}, broadcast=True)
    return jsonify(ok=True, alert=alert)

@app.route('/get_locations')
def get_locs(): return jsonify(locations)

@app.route('/get_panic_alerts')
def get_panics(): return jsonify(panic_alerts[-20:])

# CHAT - ONLY TEXT + VOICE
@app.route('/api/groups')
def api_groups(): return jsonify(groups)

@app.route('/api/create_group', methods=['POST'])
def api_create():
    data=request.get_json(); gid=data.get('id','').lower().strip().replace(' ','_'); name=data.get('name','').strip()
    if not gid or not name: return jsonify(ok=False)
    if gid in groups: return jsonify(ok=False, error="exists")
    groups[gid]={"name":name,"members":[session.get('user')], "messages":[]}
    save_groups_func(); socketio.emit('groups_updated', groups, broadcast=True)
    return jsonify(ok=True, groups=groups)

@app.route('/api/send_text', methods=['POST'])
def api_text():
    data=request.get_json(); gid=data.get('group'); text=data.get('text','').strip()
    if not gid or gid not in groups or not text: return jsonify(ok=False)
    msg={"user":session.get('user'),"text":text,"type":"text","time":datetime.now().strftime("%H:%M"),"file":None}
    groups[gid]['messages'].append(msg); groups[gid]['messages']=groups[gid]['messages'][-300:]; save_groups_func()
    socketio.emit('new_msg', {"group":gid,"msg":msg}, broadcast=True)
    return jsonify(ok=True)

@app.route('/api/send_voice', methods=['POST'])
def api_voice():
    f=request.files.get('voice'); gid=request.form.get('group')
    if not gid or gid not in groups or not f: return jsonify(ok=False),400
    data=f.read()
    if len(data)<800: return jsonify(ok=False),400
    fname=f"VOICE_{gid}_{session.get('user')}_{int(time.time())}.webm"
    open(os.path.join(EVIDENCE,fname),'wb').write(data)
    msg={"user":session.get('user'),"text":"Voice","type":"audio","time":datetime.now().strftime("%H:%M"),"file":fname}
    groups[gid]['messages'].append(msg); save_groups_func()
    socketio.emit('new_msg', {"group":gid,"msg":msg}, broadcast=True)
    return jsonify(ok=True)

@app.route('/api/group_messages/<gid>')
def api_msgs(gid):
    if gid not in groups: return jsonify([])
    return jsonify(groups[gid]['messages'][-150:])

@socketio.on('join_group')
def jg(data):
    gid=data.get('group')
    if gid: join_room(gid)

@socketio.on('location_update')
def loc_up(data):
    u=session.get('user','unknown'); locations[u]=data
    emit('location_update', {'user':u,'location':data}, broadcast=True, include_self=False)

if __name__=='__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
