# ZONDI PATROL - V6 FINAL FIXED - MAP + RADIO LIVE
from flask import Flask, render_template, request, jsonify, session, redirect, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os, json, time, uuid, shutil

app = Flask(__name__)
app.secret_key = "zondi_super_secret_2026_encrypted_final"

locations = {}
radio_messages = []
user_channels = {}

for d in ["evidence", "static/evidence", "static/radio", "static"]:
    os.makedirs(d, exist_ok=True)

USERS_FILE="users.json"
RADIO_FILE="radio.json"
LOC_FILE="locations.json"

def load_users():
    if not os.path.exists(USERS_FILE):
        default={
            "client01":{"password":generate_password_hash("client123"),"role":"client","email":"client@zps.co.za"},
            "patrol01":{"password":generate_password_hash("patrol123"),"role":"patrol","email":"patrol@zps.co.za"},
            "zondi_dev":{"password":generate_password_hash("zondi123"),"role":"dev","email":"dev@zps.co.za"}
        }
        with open(USERS_FILE,'w') as f: json.dump(default,f,indent=2)
        return default
    with open(USERS_FILE,'r') as f: return json.load(f)

def save_users(u):
    with open(USERS_FILE,'w') as f: json.dump(u,f,indent=2)

if os.path.exists(RADIO_FILE):
    try:
        with open(RADIO_FILE,'r') as f: radio_messages=json.load(f)
    except: pass
if os.path.exists(LOC_FILE):
    try:
        with open(LOC_FILE,'r') as f: locations=json.load(f)
    except: pass

def save_radio():
    with open(RADIO_FILE,'w') as f: json.dump(radio_messages[-200:],f)
def save_locs():
    with open(LOC_FILE,'w') as f: json.dump(locations,f)

@app.route('/')
def home():
    if 'user' in session: return redirect('/dashboard')
    return redirect('/login')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='GET': return render_template('login.html')
    u=request.form.get('username','').strip()
    p=request.form.get('password','')
    users=load_users()
    if u in users and check_password_hash(users[u]['password'],p):
        session['user']=u; session['role']=users[u]['role']
        return redirect('/dashboard')
    return render_template('login.html', error="❌ Invalid login")

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method=='GET': return render_template('register.html')
    u=request.form.get('username','').strip()
    e=request.form.get('email','').strip()
    pw=request.form.get('password','')
    role=request.form.get('role','client')
    users=load_users()
    if u in users: return render_template('register.html', error="User exists")
    users[u]={"password":generate_password_hash(pw),"role":role,"email":e}
    save_users(users)
    return render_template('login.html', success=f"✅ {u} created! Login now")

@app.route('/forgot', methods=['GET','POST'])
def forgot():
    if request.method=='GET': return render_template('forgot.html')
    u=request.form.get('username','').strip()
    np=request.form.get('new_password',''); cp=request.form.get('confirm_password','')
    users=load_users()
    if u not in users: return render_template('forgot.html', error="Username not found")
    if np!=cp: return render_template('forgot.html', error="Passwords don't match")
    users[u]['password']=generate_password_hash(np); save_users(users)
    return render_template('login.html', success="✅ Password reset! Login now")

@app.route('/logout')
def logout(): session.clear(); return redirect('/login')

@app.route('/dashboard')
def dashboard():
    if 'user' not in session: return redirect('/login')
    role=session['role']; user=session['user']
    if role=='client': return render_template('client.html', user=user)
    elif role=='patrol': return render_template('hq.html', user=user)
    else:
        files=[]
        for d in ["static/evidence","evidence","static/radio"]:
            if os.path.exists(d): files+=os.listdir(d)
        return render_template('dev.html', user=user, files=list(set(files)), locations=locations)

@app.route('/update_location', methods=['POST'])
def update_location():
    data=request.get_json()
    user=data.get('user') or session.get('user','anon')
    locations[user]={"lat":data['lat'],"lng":data['lng'],"time":datetime.now().strftime("%H:%M:%S"),"ts":int(time.time())}
    save_locs()
    return jsonify({"ok":True})

@app.route('/get_clients')
@app.route('/get_locations')
def get_clients(): return jsonify(locations)

def save_audio(fs, user, ch):
    fname=f"RADIO_CH{ch}_{user}_{int(time.time())}_{uuid.uuid4().hex[:4]}.webm"
    main=os.path.join("static/evidence",fname)
    fs.save(main)
    for folder in ["evidence","static/radio"]:
        try: shutil.copy(main, os.path.join(folder,fname))
        except: pass
    return fname, os.path.getsize(main)

@app.route('/send_radio', methods=['POST'])
def send_radio():
    user=session.get('user','unknown'); ch=user_channels.get(user,1)
    fname=None
    if 'audio' in request.files and request.files['audio']:
        fname,_=save_audio(request.files['audio'],user,ch)
    msg={"user":user,"file":fname,"audioUrl":f"/evidence/{fname}" if fname else None,"channel":ch,"time":datetime.now().strftime("%H:%M:%S"),"ts":int(time.time()),"text":request.form.get('text','')}
    radio_messages.append(msg); save_radio()
    return jsonify({"ok":True})

@app.route('/upload_audio', methods=['POST'])
@app.route('/api/radio/upload', methods=['POST'])
def upload_audio():
    f=request.files.get('audio') or request.files.get('file')
    if not f: return jsonify({"ok":False}),400
    raw=request.form.get('channel','ch1'); user=request.form.get('user') or session.get('user','HQ')
    ch=10 if raw=='ch_all' else int(raw.replace('ch','')) if 'ch' in raw else 1
    fname,_=save_audio(f,user,ch)
    msg={"user":user,"file":fname,"audioUrl":f"/static/evidence/{fname}","channel":ch,"time":datetime.now().strftime("%H:%M:%S"),"ts":int(time.time()),"text":f"TX {raw}"}
    radio_messages.append(msg); save_radio()
    return jsonify({"ok":True,"audioUrl":f"/static/evidence/{fname}"})

@app.route('/get_radio')
def get_radio():
    u=session.get('user','guest'); ch=user_channels.get(u,1); q=request.args.get('channel')
    if q:
        if q=='ch_all': filt=radio_messages[-40:]
        else:
            num=10 if 'all' in q else int(q.replace('ch','')) if 'ch' in q else ch
            filt=[r for r in radio_messages if r.get('channel',1)==num or r.get('channel',1)==10]
    else:
        filt=[r for r in radio_messages if r.get('channel',1)==ch or r.get('channel',1)==10]
    for r in filt:
        if r.get('file') and not r.get('audioUrl'): r['audioUrl']=f"/evidence/{r['file']}"
    return jsonify(filt[-30:])

@app.route('/get_audios')
@app.route('/api/radio/feed')
def get_audios():
    raw=request.args.get('channel','ch1')
    if raw=='ch_all': filt=radio_messages[-50:]
    else:
        num=10 if 'all' in raw else int(raw.replace('ch','')) if 'ch' in raw else 1
        filt=[r for r in radio_messages if r.get('channel',1)==num or r.get('channel',1)==10]
    out=[{"user":r.get('user'),"channel":raw,"file":r.get('file'),"audioUrl":r.get('audioUrl') or f"/evidence/{r.get('file')}" if r.get('file') else None,"time":r.get('ts',int(time.time())),"time_str":r.get('time')} for r in filt[-50:]]
    return jsonify(out)

@app.route('/set_channel/<int:ch>')
def set_channel(ch): user_channels[session.get('user','guest')]=ch; return jsonify({"ok":True})

@app.route('/trigger', methods=['POST'])
def trigger():
    user=session.get('user','unknown')
    radio_messages.append({"user":user,"text":f"🚨 PANIC {user.upper()}","type":"panic","channel":10,"time":datetime.now().strftime("%H:%M:%S"),"ts":int(time.time())})
    save_radio(); return jsonify({"ok":True})

@app.route('/upload_evidence', methods=['POST'])
def upload_evidence():
    if 'video' in request.files:
        f=request.files['video']; name=f"EV_{session.get('user','anon')}_{int(time.time())}.webm"
        p=os.path.join("static/evidence",name); f.save(p)
        try: shutil.copy(p, os.path.join("evidence",name))
        except: pass
        return jsonify({"saved":name})
    return jsonify({"error":"no file"}),400

@app.route('/evidence/<path:filename>')
@app.route('/static/evidence/<path:filename>')
@app.route('/static/radio/<path:filename>')
def serve_ev(filename):
    for folder in ["static/evidence","evidence","static/radio"]:
        if os.path.exists(os.path.join(folder,filename)):
            return send_from_directory(folder,filename)
    return send_from_directory("static/evidence",filename)

if __name__=='__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT',5000)), debug=False)
