# Cardless Cash Withdrawal System using Dynamic QR & Dual-Factor Authentication (2FA)

> **B.Tech 2nd-Year Project** | Computer Science & Engineering / Information Technology  
> **Tech Stack:** Python 3.12 (FastAPI), SQLite / SQLAlchemy, OpenCV, WebSockets, HTML5 / TailwindCSS / JavaScript

---

## 📌 Project Overview & Motivation
Imagine a student on campus or an individual facing an urgent medical/travel emergency who needs physical cash but has left their ATM debit card in their hostel or lost it. 

Inspired by metro token/QR ticketing machines, this project introduces **Cardless Cash Withdrawal**:
1. Walk up to any ATM and choose **"Payment by Scan"**.
2. The ATM screen dynamically generates an encrypted, time-bounded QR code (valid for **60 seconds**).
3. The user scans the QR using their secure mobile banking app.
4. The system enforces **Two-Factor Authentication (2FA)**:
   - **Factor 1 (Knowledge):** 4-digit MPIN.
   - **Factor 2 (Biometric):** Live Face Recognition verification via OpenCV (toggleable in user settings).
5. Once authenticated, the server instantly signals the ATM terminal via **WebSockets** to dispense the cash and print a receipt.

---

## 🎓 Academic Subjects & Engineering Disciplines Included

During college viva evaluations, lab examinations, and project report presentations, you can map this system directly to core B.Tech subjects:

| B.Tech Subject | Application in this Project |
| :--- | :--- |
| **Cryptography & Network Security (CNS)** | Dynamic HMAC-SHA256 signatures, cryptographic Nonces (preventing **Replay Attacks**), Time-To-Live (TTL) tokens, PBKDF2/SHA256 PIN hashing, and session rate-limiting ($\le 3$ attempts). |
| **Database Management Systems (DBMS)** | Multi-table relational schema (`User`, `ATMTerminal`, `QRSession`, `Transaction`), ACID transactional integrity (ensuring balance cannot be deducted without recording the audit ledger and signaling the dispenser). |
| **Computer Networks (CN)** | Full-duplex **WebSockets** (`/ws/atm/{session_id}`) for instant zero-latency ATM trigger, RESTful APIs, and Client-Server architecture. |
| **Artificial Intelligence & Computer Vision (CV)** | Face detection using OpenCV Haar Cascades, image normalization & histogram equalization, and template/histogram cross-correlation matching for biometric verification. |
| **Software Engineering (SE)** | Threat modeling, state machines (`PENDING` $\to$ `AUTHORIZED` $\to$ `USED`/`EXPIRED`), sequence diagrams, and automated integration test coverage. |

---

## 🔒 Security Constraints Implemented

1. **Strict Dynamic Expiry (60–120s TTL):**
   - The QR code payload contains an `expires_at` Unix timestamp signed by the server's private secret.
   - If the timer hits zero, the token is automatically invalidated (`EXPIRED`).
2. **Attempt Rate Limiter (Max 3 Attempts Per Session):**
   - Users or ATMs can refresh an expired QR a maximum of **3 times** per session.
   - Any further attempt terminates the session with `HTTP 429 Too Many Requests` to prevent Denial-of-Service (DoS) and session hijacking.
3. **Replay Attack Protection:**
   - Every QR generation embeds a unique cryptographically random 16-byte nonce.
   - Once a session transitions to `AUTHORIZED` or `USED`, the nonce is permanently burned and cannot be reused.
4. **User-Controlled Biometric 2FA:**
   - Users can toggle Face Recognition in their mobile app settings.
   - If enabled, withdrawal requires both MPIN and a live selfie match against the enrolled reference photo.

---

## 🚀 How to Run the Project

### 1. Activate Environment
Open PowerShell and navigate to the project directory:
```powershell
cd "C:\Users\abhishek_pc\.gemini\antigravity\scratch\cardless-cash-withdrawal"
.\.venv\Scripts\Activate.ps1
```

### 2. Start the Backend Server
```powershell
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

### 3. Open the Interfaces in Your Browser
- **Project Hub & Presentation Portal:** [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **ATM Terminal Screen:** [http://127.0.0.1:8000/atm](http://127.0.0.1:8000/atm)
- **Mobile Banking App:** [http://127.0.0.1:8000/mobile](http://127.0.0.1:8000/mobile)
- **Interactive Swagger API Docs:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## 🧪 Automated Testing
To run the automated test suite verifying all 8 security checks and business logic:
```powershell
python test_system.py
```

---

## 💡 Default Demo Credentials
- **Student Name:** Abhishek Sharma
- **Account Number:** `AC9876543210`
- **Initial Balance:** `₹15,000.00`
- **Default 4-Digit MPIN:** `1234`
- **ATM Terminal:** `ATM_CAMPUS_01` (Cash Reserve: `₹75,000.00`)

