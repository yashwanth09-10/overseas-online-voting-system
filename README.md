# 🏛️ Overseas Indian E-Voting Portal (Form 6A)

An institutional-grade Electronic Voting System prototype designed for Non-Resident Indians (NRIs), compliant with Election Commission of India (ECI) standards.

## 🚀 Key Features

- **4-Tier Verification Pipeline:**
  1. **Electoral Registry Check:** EPIC ID, Passport, and Verhoeff-validated 12-digit UIDAI identifier.
  2. **Physical Geolocation:** HTML5 GPS + OpenStreetMap reverse geocoding to enforce jurisdictional borders.
  3. **Multi-Factor Authentication:** Session-based mobile OTP dispatch simulation.
  4. **Biometric Liveness Inspection:** Webcam stream with ambient variance checks; auto-terminates hardware access upon confirmation.
- **Cryptographic Blind Ballot Box:** Decouples elector identity from recorded votes using ephemeral single-use tokens to guarantee ballot secrecy.
- **Returning Officer Dashboard (`/admin`):** State machine for electoral phases (`VOTING_ACTIVE`, `VOTING_CLOSED`, `RESULTS_DECLARED`) with an immutable audit ledger.
- **Digital VVPAT Slip:** Generates and exports client-side downloadable PDF receipts (Form 7B).
- **Multilingual Support:** Instant localization in English, हिन्दी, and ಕನ್ನಡ.

## 🛠️ Tech Stack

- **Backend:** Python, Flask, SQLite3
- **Frontend:** Vanilla HTML5, CSS3, JavaScript (ES6+)
- **Libraries:** Chart.js, html2pdf.js

## 💻 Setup & Local Run

1. Clone the repository:
   ```bash
   git clone <YOUR_REPO_URL>
   cd "online voting system"
