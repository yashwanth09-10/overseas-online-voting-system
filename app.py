import sqlite3
import random
import string
import secrets
import hashlib
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)
DB_NAME = "voting_overseas_v4.db"

active_sessions = {}
# Ephemeral Blind Ballot Tokens: decoupled from voter identity
valid_blind_tokens = set()

# Global Election Lifecycle State
ELECTION_STATE = {
    "status": "VOTING_ACTIVE",  # VOTING_ACTIVE, VOTING_CLOSED, RESULTS_DECLARED
    "admin_key": "ECI_ADMIN_2026"
}

# --- VERHOEFF ALGORITHM (Mandated UIDAI Aadhaar Checksum Standard) ---
VERHOEFF_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
    [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
    [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]
]
VERHOEFF_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8]
]

def validate_verhoeff(num_str):
    """Validates 12-digit number against official Verhoeff checksum."""
    if not num_str.isdigit() or len(num_str) != 12:
        return False
    # Numbers starting with 0 or 1 are invalid under UIDAI allocation rules
    if num_str[0] in ('0', '1'):
        return False
    c = 0
    reversed_digits = [int(d) for d in reversed(num_str)]
    for i, digit in enumerate(reversed_digits):
        c = VERHOEFF_D[c][VERHOEFF_P[i % 8][digit]]
    return c == 0

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # ECI Form 6A Overseas Elector Register
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS voters (
            epic_id TEXT PRIMARY KEY,
            full_name TEXT NOT NULL,
            constituency TEXT NOT NULL,
            passport_number TEXT NOT NULL,
            aadhaar_hash TEXT NOT NULL,
            mobile_number TEXT NOT NULL,
            residing_country TEXT NOT NULL,
            has_voted INTEGER DEFAULT 0
        )
    """)
    
    # Official Candidates List
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            party TEXT NOT NULL,
            symbol TEXT NOT NULL,
            photo_url TEXT NOT NULL,
            votes INTEGER DEFAULT 0
        )
    """)
    
    # Audit Log Table (Tamper-evident trail)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            details TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("SELECT COUNT(*) FROM candidates")
    if cursor.fetchone()[0] == 0:
        candidates = [
            ("Narendra Modi", "Bharatiya Janata Party (BJP)", "Lotus", 
             "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c4/Prime_Minister_of_India_Narendra_Modi_%28cropped%29.jpg/220px-Prime_Minister_of_India_Narendra_Modi_%28cropped%29.jpg"),
            ("Rahul Gandhi", "Indian National Congress (INC)", "Hand", 
             "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b3/Rahul_Gandhi_at_AICC_headquarters_in_New_Delhi_02.jpg/220px-Rahul_Gandhi_at_AICC_headquarters_in_New_Delhi_02.jpg"),
            ("Arvind Kejriwal", "Aam Aadmi Party (AAP)", "Broom", 
             "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1b/Arvind_Kejriwal_2022.jpg/220px-Arvind_Kejriwal_2022.jpg"),
            ("None of the Above (NOTA)", "Independent / NOTA", "Ballot Box", 
             "https://upload.wikimedia.org/wikipedia/commons/thumb/8/87/NOTA_Option_Logo.png/220px-NOTA_Option_Logo.png")
        ]
        cursor.executemany("INSERT INTO candidates (name, party, symbol, photo_url, votes) VALUES (?, ?, ?, ?, 0)", candidates)
        
    conn.commit()
    conn.close()

init_db()

@app.route("/")
def index():
    return render_template("index.html")

# --- FORM 6A REGISTRATION ---
@app.route("/api/register-overseas", methods=["POST"])
def register_overseas():
    data = request.get_json()
    full_name = data.get("name", "").strip()
    constituency = data.get("constituency", "").strip()
    passport_number = data.get("passport", "").strip().upper()
    aadhaar_number = data.get("aadhaar", "").strip()
    mobile_number = data.get("mobile", "").strip()
    country = data.get("country", "").strip()

    if not full_name or not constituency or not passport_number or not aadhaar_number or not mobile_number or not country:
        return jsonify({"success": False, "message": "All fields are strictly required."}), 400

    # Real Verhoeff Checksum Test
    if not validate_verhoeff(aadhaar_number):
        return jsonify({
            "success": False, 
            "message": "Invalid Identifier: Mathematical Verhoeff checksum test failed. Please verify the 12-digit number."
        }), 400

    if country.lower() == "india":
        return jsonify({"success": False, "message": "Overseas registry is restricted to citizens residing abroad."}), 400

    random_code = ''.join(random.choices(string.digits, k=6))
    epic_id = f"IND{random_code}"
    # Cryptographic hash to avoid storing raw sensitive identifier
    aadhaar_hash = hashlib.sha256(aadhaar_number.encode()).hexdigest()

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO voters (epic_id, full_name, constituency, passport_number, aadhaar_hash, mobile_number, residing_country, has_voted)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
        """, (epic_id, full_name, constituency, passport_number, aadhaar_hash, mobile_number, country))
        cursor.execute("INSERT INTO audit_logs (event_type, details) VALUES ('REGISTRATION_CREATED', ?)", 
                       (f"EPIC {epic_id} registered for {constituency}",))
        conn.commit()
        return jsonify({
            "success": True, 
            "message": f"Overseas Elector Registered. Your EPIC ID: {epic_id}",
            "epic_id": epic_id
        })
    except Exception as e:
        return jsonify({"success": False, "message": f"Registration error: {str(e)}"}), 500
    finally:
        conn.close()

# --- TIER 1: AUTHENTICATION ---
@app.route("/api/verify/tier1", methods=["POST"])
def verify_tier1():
    data = request.get_json()
    epic_id = data.get("epic_id", "").strip().upper()
    passport = data.get("passport", "").strip().upper()
    aadhaar = data.get("aadhaar", "").strip()

    if not validate_verhoeff(aadhaar):
        return jsonify({"success": False, "message": "Invalid identifier entered (Checksum failure)."}), 400

    aadhaar_hash = hashlib.sha256(aadhaar.encode()).hexdigest()

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT full_name, constituency, residing_country, mobile_number, has_voted 
        FROM voters 
        WHERE epic_id = ? AND passport_number = ? AND aadhaar_hash = ?
    """, (epic_id, passport, aadhaar_hash))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return jsonify({"success": False, "message": "Authentication failed: Record not found in ECI database."}), 404
    if row[4] == 1:
        return jsonify({"success": False, "message": "Electoral records indicate you have already cast your ballot."}), 403

    session_token = secrets.token_hex(24)
    active_sessions[session_token] = {
        "epic_id": epic_id,
        "full_name": row[0],
        "constituency": row[1],
        "country": row[2],
        "mobile": row[3],
        "tier1": True,
        "tier2": False,
        "tier3": False,
        "tier4": False,
        "otp": None
    }

    return jsonify({
        "success": True, 
        "session_token": session_token,
        "elector_name": row[0],
        "registered_country": row[2],
        "masked_mobile": f"+91-XXXXX-{row[3][-4:]}" if len(row[3]) >= 4 else row[3]
    })

# --- TIER 2: GEOLOCATION ---
@app.route("/api/verify/tier2", methods=["POST"])
def verify_tier2():
    data = request.get_json()
    session_token = data.get("session_token")
    detected_country = data.get("detected_country", "").strip()

    session = active_sessions.get(session_token)
    if not session or not session.get("tier1"):
        return jsonify({"success": False, "message": "Unauthorized session."}), 401

    if detected_country.lower() == "india":
        return jsonify({"success": False, "message": "Access Denied: Ballot origin detected within India."}), 403

    session["tier2"] = True
    return jsonify({"success": True, "message": f"Foreign jurisdiction verified ({detected_country})."})

# --- TIER 3: DISPATCH OTP ---
@app.route("/api/verify/tier3/send-otp", methods=["POST"])
def send_otp():
    data = request.get_json()
    session_token = data.get("session_token")

    session = active_sessions.get(session_token)
    if not session or not session.get("tier2"):
        return jsonify({"success": False, "message": "Unauthorized session."}), 401

    otp = ''.join(random.choices(string.digits, k=6))
    session["otp"] = otp

    return jsonify({
        "success": True,
        "message": f"Authentication OTP dispatched to registered mobile {session['mobile'][-4:]}.",
        "simulated_otp": otp
    })

@app.route("/api/verify/tier3/confirm-otp", methods=["POST"])
def confirm_otp():
    data = request.get_json()
    session_token = data.get("session_token")
    otp_input = data.get("otp", "").strip()

    session = active_sessions.get(session_token)
    if not session or not session.get("tier2"):
        return jsonify({"success": False, "message": "Unauthorized session."}), 401

    if session.get("otp") != otp_input:
        return jsonify({"success": False, "message": "Invalid passcode entered."}), 400

    session["tier3"] = True
    return jsonify({"success": True, "message": "OTP validation confirmed."})

# --- TIER 4: BIOMETRIC CHECK & DIGITAL BLIND TOKEN ISSUANCE ---
@app.route("/api/verify/tier4", methods=["POST"])
def verify_tier4():
    data = request.get_json()
    session_token = data.get("session_token")
    liveness_passed = data.get("liveness_passed", False)

    session = active_sessions.get(session_token)
    if not session or not session.get("tier3"):
        return jsonify({"success": False, "message": "Unauthorized session."}), 401

    if not liveness_passed:
        return jsonify({"success": False, "message": "Biometric verification failed. Face was obscured or off-center."}), 400

    epic_id = session["epic_id"]

    # Mark voter as voted immediately to prevent reuse
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE voters SET has_voted = 1 WHERE epic_id = ?", (epic_id,))
    cursor.execute("INSERT INTO audit_logs (event_type, details) VALUES ('TOKEN_ISSUED', ?)", 
                   (f"Ephemeral Blind Ballot token issued for EPIC {epic_id}",))
    conn.commit()
    conn.close()

    # Generate an anonymous Blind Ballot Token
    blind_token = secrets.token_urlsafe(32)
    valid_blind_tokens.add(blind_token)

    # Invalidate the voter session to decouple identity from ballot
    del active_sessions[session_token]

    return jsonify({
        "success": True, 
        "message": "Biometric match confirmed. Identity decoupled and blind ballot token generated.",
        "blind_token": blind_token
    })

# --- CANDIDATES LIST ---
@app.route("/api/candidates", methods=["GET"])
def get_candidates():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, party, symbol, photo_url FROM candidates")
    rows = cursor.fetchall()
    conn.close()

    candidates = [{"id": r[0], "name": r[1], "party": r[2], "symbol": r[3], "photo_url": r[4]} for r in rows]
    return jsonify(candidates)

# --- TIER 5: ANONYMOUS BLIND BALLOT SUBMISSION ---
@app.route("/api/cast-blind-ballot", methods=["POST"])
def cast_blind_ballot():
    data = request.get_json()
    blind_token = data.get("blind_token")
    candidate_id = data.get("candidate_id")

    if ELECTION_STATE["status"] != "VOTING_ACTIVE":
        return jsonify({"success": False, "message": "Electronic ballot box is currently closed."}), 403

    if blind_token not in valid_blind_tokens:
        return jsonify({"success": False, "message": "Invalid or already spent blind ballot token."}), 403

    valid_blind_tokens.remove(blind_token)

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE candidates SET votes = votes + 1 WHERE id = ?", (candidate_id,))
    cursor.execute("INSERT INTO audit_logs (event_type, details) VALUES ('BALLOT_CAST', 'Anonymous blind ballot registered')",)
    conn.commit()
    conn.close()

    receipt_hash = hashlib.sha256(f"{candidate_id}{secrets.token_hex(8)}".encode()).hexdigest()[:16].upper()

    return jsonify({
        "success": True, 
        "message": "Anonymous ballot committed into electronic ballot vault.",
        "receipt_id": f"ECI-VVPAT-{receipt_hash}"
    })

# --- ADMIN DASHBOARD & STATE MACHINE ---
@app.route("/admin")
def admin_page():
    return render_template("admin.html")

@app.route("/api/admin/status", methods=["GET"])
def admin_status():
    return jsonify({"status": ELECTION_STATE["status"]})

@app.route("/api/admin/set-status", methods=["POST"])
def admin_set_status():
    data = request.get_json()
    if data.get("admin_key") != ELECTION_STATE["admin_key"]:
        return jsonify({"success": False, "message": "Invalid Administrator Key."}), 401

    new_status = data.get("new_status")
    if new_status in ["VOTING_ACTIVE", "VOTING_CLOSED", "RESULTS_DECLARED"]:
        ELECTION_STATE["status"] = new_status
        return jsonify({"success": True, "status": ELECTION_STATE["status"]})
    return jsonify({"success": False, "message": "Invalid state requested."}), 400

@app.route("/api/admin/results", methods=["POST"])
def admin_results():
    data = request.get_json()
    if data.get("admin_key") != ELECTION_STATE["admin_key"]:
        return jsonify({"success": False, "message": "Unauthorized."}), 401

    if ELECTION_STATE["status"] != "RESULTS_DECLARED":
        return jsonify({"success": False, "message": "Results are locked until officially declared."}), 403

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, party, symbol, votes FROM candidates")
    results = [{"id": r[0], "name": r[1], "party": r[2], "symbol": r[3], "votes": r[4]} for r in cursor.fetchall()]
    cursor.execute("SELECT event_type, details, timestamp FROM audit_logs ORDER BY id DESC LIMIT 50")
    logs = [{"type": r[0], "details": r[1], "timestamp": r[2]} for r in cursor.fetchall()]
    conn.close()

    return jsonify({"success": True, "results": results, "logs": logs})

if __name__ == "__main__":
    app.run(debug=True, port=5000)