# ZONDI Security System — Base44 Dev Environment

## Overview
Flask + Flask-SocketIO app (real-time patrol/security monitoring with PTT radio, GPS tracking, panic alerts, evidence uploads). File-based storage — no external database.

## Running
- `docker compose -f docker-compose.base44.yml up -d`
- App runs on host port 3000 (container port 5000)
- Dev server with live reload (Werkzeug debug mode + `allow_unsafe_werkzeug=True`)
- Dependencies installed at container start via `pip install -r requirements.txt`

## Key Details
- `zondi.py` is the entire backend (Flask routes + SocketIO events)
- Users stored in `users.json` (file-based, no DB)
- Evidence/recordings stored in `evidence/` directory
- Templates in `templates/`, static assets in `static/`
- No external credentials or secrets needed
- Dev portal at `/dev` (password: `zondi@123`)
- Pre-seeded users: `client01` (client), `patrol01` (patrol), `zondi_dev` (dev)

## Verification
- `curl http://localhost:3000/` should return the login page (HTTP 200)
- SocketIO connects on the same port for real-time features
