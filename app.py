import io
import re
import os
import math
import requests
import msoffcrypto
import pandas as pd
from flask import Flask, render_template, jsonify
from datetime import date, datetime

app = Flask(__name__)

ONEDRIVE_URL = os.environ.get("ONEDRIVE_URL", "YOUR_ONEDRIVE_LINK_HERE")
FILE_PASSWORD = os.environ.get("FILE_PASSWORD", "ASR1234")

SHEET_CONFIG = {
    "Fraser 2026":        [("ASR005", 1), ("ASR007", 22), ("ASR008", 40)],
    "Sunshine Coast 2026":[("ASR001", 1), ("ASR002", 22), ("ASR011", 42), ("ASR012", 62)],
    "Gatton 2026":        [("ASR003", 1), ("ASR006", 21), ("ASR010", 40)],
}

def safe_float(v):
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except:
        return None

def find_current_week_row(df, target_date=None):
    if target_date is None:
        target_date = date.today()
    for i, row in df.iterrows():
        val = str(row.iloc[0])
        m = re.match(r"(\d{1,2}/\d{1,2}/\d{2,4})\s*-\s*(\d{1,2}/\d{1,2}/\d{2,4})", val)
        if m:
            for fmt in ["%d/%m/%Y", "%d/%m/%y"]:
                try:
                    start = datetime.strptime(m.group(1).strip(), fmt).date()
                    end   = datetime.strptime(m.group(2).strip(), fmt).date()
                    if start <= target_date <= end:
                        return i, f"{m.group(1).strip()} - {m.group(2).strip()}"
                except:
                    pass
    return None, None

def fetch_and_decrypt():
    resp = requests.get(ONEDRIVE_URL, timeout=30)
    resp.raise_for_status()
    raw = io.BytesIO(resp.content)
    office = msoffcrypto.OfficeFile(raw)
    office.load_key(password=FILE_PASSWORD)
    decrypted = io.BytesIO()
    office.decrypt(decrypted)
    decrypted.seek(0)
    return decrypted

def extract_data():
    decrypted = fetch_and_decrypt()
    all_sheets = pd.read_excel(decrypted, sheet_name=None)
    all_data = {}

    for sheet_name, trucks in SHEET_CONFIG.items():
        df = all_sheets.get(sheet_name)
        if df is None:
            continue
        region = sheet_name.replace(" 2026", "")
        week_row, week_str = find_current_week_row(df)
        if week_row is None:
            continue

        for truck_id, s in trucks:
            days = ["Mon", "Tue", "Wed", "Thu", "Fri"]
            daily = []
            for di, day in enumerate(days):
                row = df.iloc[week_row + 1 + di]
                loc = str(row.iloc[s]).strip()
                if loc == "nan":
                    loc = ""
                daily.append({
                    "day":         day,
                    "loc":         loc,
                    "installAvg":  safe_float(row.iloc[s + 4]),
                    "remvdAvg":    safe_float(row.iloc[s + 8]),
                    "totalHrs":    safe_float(row.iloc[s + 9]),
                    "jobsInst":    safe_float(row.iloc[s + 1]),
                    "jobsRemvd":   safe_float(row.iloc[s + 5]),
                })

            summary = df.iloc[week_row + 7]
            inst_avgs  = [d["installAvg"] for d in daily if d["installAvg"] is not None]
            remvd_avgs = [d["remvdAvg"]   for d in daily if d["remvdAvg"]   is not None]

            all_data[truck_id] = {
                "truck":          truck_id,
                "region":         region,
                "week":           week_str,
                "daily":          daily,
                "weekJobsInst":   safe_float(summary.iloc[s + 1]),
                "weekJobsRemvd":  safe_float(summary.iloc[s + 5]),
                "weekInstallAvg": round(sum(inst_avgs)  / len(inst_avgs),  2) if inst_avgs  else None,
                "weekRemvdAvg":   round(sum(remvd_avgs) / len(remvd_avgs), 2) if remvd_avgs else None,
            }

    return all_data

@app.route("/")
def index():
    return render_template("dashboard.html")

@app.route("/api/data")
def api_data():
    try:
        data = extract_data()
        return jsonify({"status": "ok", "data": data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
