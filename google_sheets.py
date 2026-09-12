import os
import json
import logging

logger = logging.getLogger(__name__)
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
_service = None


def _get_service():
    global _service
    if _service is not None:
        return _service
    creds_json = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
    if not creds_json:
        return None
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
        info = json.loads(creds_json)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
        _service = build('sheets', 'v4', credentials=creds)
        return _service
    except Exception as e:
        logger.error(f"Google Sheets auth failed: {e}")
        return None


def append_patrol_log(user, lat, lng, time_str, role):
    """Append a patrol log row to the configured Google Sheet."""
    service = _get_service()
    if service is None:
        return
    spreadsheet_id = os.environ.get('GOOGLE_SPREADSHEET_ID')
    if not spreadsheet_id:
        return
    try:
        row = [time_str, user, str(lat), str(lng), role]
        service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range='A:E',
            valueInputOption='RAW',
            body={'values': [row]}
        ).execute()
        logger.info(f"Synced patrol log to Google Sheets: {user} at {time_str}")
    except Exception as e:
        logger.error(f"Google Sheets append failed: {e}")
