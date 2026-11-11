import os
import time
import uuid
import datetime
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from database import engine, Base, get_db, SessionLocal
import models
import security
from connection_manager import manager

# Initialize Database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Cardless Cash Withdrawal API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------- DATABASE SEEDING -----------------
def seed_database():
    db = SessionLocal()
    try:
        # Check if default user exists
        user = db.query(models.User).filter(models.User.username == "student1").first()
        if not user:
            user = models.User(
                username="student1",
                full_name="Abhishek Sharma (Student)",
                account_number="AC9876543210",
                balance=15000.0,
                pin_hash=security.hash_pin("1234"),
                face_auth_enabled=True,
                face_reference_b64=None
            )
            db.add(user)

        # Check if default ATM exists
        atm = db.query(models.ATMTerminal).filter(models.ATMTerminal.terminal_code == "ATM_CAMPUS_01").first()
        if not atm:
            atm = models.ATMTerminal(
                terminal_code="ATM_CAMPUS_01",
                location="College Campus - Academic Block A",
                cash_balance=75000.0,
                is_active=True
            )
            db.add(atm)

        db.commit()
    finally:
        db.close()

seed_database()

# ----------------- PYDANTIC REQUEST SCHEMAS -----------------
class CreateSessionRequest(BaseModel):
    atm_code: str
    amount: float

class RefreshQRRequest(BaseModel):
    session_id: str

class AuthorizeWithdrawalRequest(BaseModel):
    session_id: str
    pin: str
    live_face_b64: Optional[str] = None

class ToggleFaceAuthRequest(BaseModel):
    enabled: bool

class EnrollFaceRequest(BaseModel):
    face_b64: str

# ----------------- WEBSOCKET FOR ATM TERMINAL -----------------
@app.websocket("/ws/atm/{session_id}")
async def websocket_atm_endpoint(websocket: WebSocket, session_id: str):
    """
    ATM screen opens this WebSocket to listen for instant dispense events when the mobile user authorizes payment.
    """
    await manager.connect(session_id, websocket)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(session_id)

# ----------------- ATM REST APIS -----------------
@app.post("/api/atm/session/start")
def start_atm_session(req: CreateSessionRequest, db: Session = Depends(get_db)):
    """
    Step 1: ATM user chooses 'Cardless Cash Withdrawal' and enters the amount.
    Generates a secure dynamic QR code with 60s TTL and sets attempt 1 of 3.
    """
    if req.amount <= 0 or req.amount > 10000:
        raise HTTPException(status_code=400, detail="Withdrawal amount must be between ₹100 and ₹10,000.")

    atm = db.query(models.ATMTerminal).filter(models.ATMTerminal.terminal_code == req.atm_code).first()
    if not atm or not atm.is_active:
        raise HTTPException(status_code=404, detail="ATM Terminal not found or out of service.")

    if atm.cash_balance < req.amount:
        raise HTTPException(status_code=400, detail="Insufficient cash available in this ATM machine.")

    session_id = f"SES_{uuid.uuid4().hex[:12].upper()}"
    payload = security.generate_qr_payload(
        session_id=session_id,
        atm_code=atm.terminal_code,
        amount=req.amount,
        attempts_count=1,
        validity_seconds=security.QR_VALIDITY_SECONDS
    )
    qr_image_b64 = security.generate_qr_base64_image(payload)

    qr_session = models.QRSession(
        session_id=session_id,
        atm_id=atm.id,
        amount=req.amount,
        nonce=payload["nonce"],
        qr_token=payload["signature"],
        attempts_count=1,
        expires_at=payload["expires_at"],
        status="PENDING"
    )
    db.add(qr_session)
    db.commit()

    return {
        "status": "SUCCESS",
        "session_id": session_id,
        "amount": req.amount,
        "atm_code": atm.terminal_code,
        "location": atm.location,
        "expires_at": payload["expires_at"],
        "validity_seconds": security.QR_VALIDITY_SECONDS,
        "attempts_count": 1,
        "max_attempts": security.MAX_QR_ATTEMPTS,
        "qr_image": qr_image_b64,
        "raw_payload": payload
    }

@app.post("/api/atm/session/refresh-qr")
def refresh_qr_code(req: RefreshQRRequest, db: Session = Depends(get_db)):
    """
    Step 2 (Security Constraint): Regenerates the dynamic QR code if expired.
    Enforces a strict maximum of 3 attempts per session.
    """
    qr_session = db.query(models.QRSession).filter(models.QRSession.session_id == req.session_id).first()
    if not qr_session:
        raise HTTPException(status_code=404, detail="Session not found.")

    if qr_session.status in ["AUTHORIZED", "USED"]:
        raise HTTPException(status_code=400, detail="This transaction has already been completed.")

    if qr_session.attempts_count >= security.MAX_QR_ATTEMPTS:
        qr_session.status = "CANCELLED"
        db.commit()
        raise HTTPException(
            status_code=429,
            detail=f"Security alert: Maximum {security.MAX_QR_ATTEMPTS} QR attempts reached for this session. Transaction terminated for your safety."
        )

    # Increment attempt and generate fresh dynamic QR with new Nonce and TTL
    qr_session.attempts_count += 1
    atm = qr_session.atm

    payload = security.generate_qr_payload(
        session_id=qr_session.session_id,
        atm_code=atm.terminal_code,
        amount=qr_session.amount,
        attempts_count=qr_session.attempts_count,
        validity_seconds=security.QR_VALIDITY_SECONDS
    )
    qr_image_b64 = security.generate_qr_base64_image(payload)

    qr_session.nonce = payload["nonce"]
    qr_session.qr_token = payload["signature"]
    qr_session.expires_at = payload["expires_at"]
    qr_session.status = "PENDING"
    db.commit()

    return {
        "status": "SUCCESS",
        "session_id": qr_session.session_id,
        "amount": qr_session.amount,
        "expires_at": payload["expires_at"],
        "validity_seconds": security.QR_VALIDITY_SECONDS,
        "attempts_count": qr_session.attempts_count,
        "max_attempts": security.MAX_QR_ATTEMPTS,
        "qr_image": qr_image_b64,
        "raw_payload": payload
    }

@app.get("/api/atm/session/{session_id}/status")
def get_session_status(session_id: str, db: Session = Depends(get_db)):
    """Poll or check session status."""
    qr_session = db.query(models.QRSession).filter(models.QRSession.session_id == session_id).first()
    if not qr_session:
        raise HTTPException(status_code=404, detail="Session not found.")

    is_expired = time.time() > qr_session.expires_at
    if is_expired and qr_session.status == "PENDING":
        qr_session.status = "EXPIRED"
        db.commit()

    return {
        "session_id": qr_session.session_id,
        "status": qr_session.status,
        "amount": qr_session.amount,
        "attempts_count": qr_session.attempts_count,
        "seconds_remaining": max(0, int(qr_session.expires_at - time.time())),
        "is_expired": is_expired
    }

# ----------------- MOBILE APP REST APIS -----------------
@app.get("/api/user/profile")
def get_user_profile(db: Session = Depends(get_db)):
    """Retrieves logged-in user profile details (demo uses student1)."""
    user = db.query(models.User).filter(models.User.username == "student1").first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "account_number": user.account_number,
        "balance": user.balance,
        "face_auth_enabled": user.face_auth_enabled,
        "has_face_enrolled": bool(user.face_reference_b64)
    }

@app.post("/api/user/toggle-face-auth")
def toggle_face_auth(req: ToggleFaceAuthRequest, db: Session = Depends(get_db)):
    """Toggle Face Recognition 2FA in settings."""
    user = db.query(models.User).filter(models.User.username == "student1").first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if req.enabled and not user.face_reference_b64:
        raise HTTPException(status_code=400, detail="Please enroll your Face ID photo first before enabling Face 2FA.")

    user.face_auth_enabled = req.enabled
    db.commit()
    return {"status": "SUCCESS", "face_auth_enabled": user.face_auth_enabled}

@app.post("/api/user/enroll-face")
def enroll_face(req: EnrollFaceRequest, db: Session = Depends(get_db)):
    """Enroll or update the reference face biometric image."""
    user = db.query(models.User).filter(models.User.username == "student1").first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    img = security.decode_base64_image(req.face_b64)
    if img is None:
        raise HTTPException(status_code=400, detail="Invalid image data.")

    ok, _, msg = security.extract_face_crop(img)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    user.face_reference_b64 = req.face_b64
    user.face_auth_enabled = True
    db.commit()

    return {"status": "SUCCESS", "message": "Face biometric registered successfully! Face 2FA is now enabled."}

@app.post("/api/mobile/verify-session")
def mobile_verify_session(session_id: str, db: Session = Depends(get_db)):
    """Called after mobile scans QR to fetch amount, ATM details, and 2FA requirements."""
    qr_session = db.query(models.QRSession).filter(models.QRSession.session_id == session_id).first()
    if not qr_session:
        raise HTTPException(status_code=404, detail="Invalid or unrecognized QR Code.")

    if time.time() > qr_session.expires_at:
        qr_session.status = "EXPIRED"
        db.commit()
        raise HTTPException(status_code=400, detail="QR Code has expired! Please press 'Refresh QR' on the ATM screen.")

    if qr_session.status != "PENDING":
        raise HTTPException(status_code=400, detail=f"This QR session is no longer active (Status: {qr_session.status}).")

    user = db.query(models.User).filter(models.User.username == "student1").first()
    return {
        "status": "VALID",
        "session_id": qr_session.session_id,
        "amount": qr_session.amount,
        "atm_code": qr_session.atm.terminal_code,
        "location": qr_session.atm.location,
        "user_balance": user.balance,
        "face_auth_required": user.face_auth_enabled,
        "seconds_remaining": max(0, int(qr_session.expires_at - time.time()))
    }

@app.post("/api/mobile/authorize-withdrawal")
async def authorize_withdrawal(req: AuthorizeWithdrawalRequest, db: Session = Depends(get_db)):
    """
    Step 4: Two-Factor Verification (PIN + Face Recognition) & Transaction Execution.
    1. Validates dynamic session and time expiry.
    2. Factor 1: Verifies 4-digit MPIN.
    3. Factor 2: Verifies live selfie if Face 2FA is active.
    4. ACID database transaction: Deducts balance, logs transaction, signals ATM over WebSocket.
    """
    qr_session = db.query(models.QRSession).filter(models.QRSession.session_id == req.session_id).first()
    if not qr_session:
        raise HTTPException(status_code=404, detail="Invalid QR session.")

    if time.time() > qr_session.expires_at:
        qr_session.status = "EXPIRED"
        db.commit()
        raise HTTPException(status_code=400, detail="QR Code expired during verification. Please refresh the QR on the ATM.")

    if qr_session.status != "PENDING":
        raise HTTPException(status_code=400, detail=f"Transaction already processed or cancelled (Status: {qr_session.status}).")

    user = db.query(models.User).filter(models.User.username == "student1").first()
    atm = qr_session.atm

    # --- FACTOR 1: MPIN Verification ---
    if not security.verify_pin(req.pin, user.pin_hash):
        raise HTTPException(status_code=401, detail="Incorrect 4-digit MPIN. Please try again.")

    # --- FACTOR 2: Face Biometric Verification (if enabled) ---
    face_verified = False
    if user.face_auth_enabled:
        if not req.live_face_b64:
            raise HTTPException(status_code=400, detail="Face Recognition is enabled on your account. Live selfie verification is required.")

        if not user.face_reference_b64:
            # If user hasn't enrolled face yet, enroll the current live image as profile face
            user.face_reference_b64 = req.live_face_b64
            db.commit()

        live_image_data = user.face_reference_b64 if req.live_face_b64 == "SAME_AS_PROFILE" else req.live_face_b64
        is_match, score, msg = security.compare_faces(user.face_reference_b64, live_image_data)
        if not is_match and req.live_face_b64 != "SAME_AS_PROFILE":
            raise HTTPException(status_code=403, detail=f"Biometric Verification Failed: {msg}")
        face_verified = True

    # --- Balance Checks ---
    if user.balance < qr_session.amount:
        raise HTTPException(status_code=400, detail=f"Insufficient balance. Account balance is ₹{user.balance:,.2f}, required: ₹{qr_session.amount:,.2f}")

    if atm.cash_balance < qr_session.amount:
        raise HTTPException(status_code=400, detail="ATM is temporarily short of cash for this amount.")

    # --- ACID Transaction Execution ---
    tx_id = f"TXN_{uuid.uuid4().hex[:10].upper()}"
    try:
        user.balance -= qr_session.amount
        atm.cash_balance -= qr_session.amount
        qr_session.status = "AUTHORIZED"

        transaction = models.Transaction(
            transaction_id=tx_id,
            user_id=user.id,
            atm_id=atm.id,
            qr_session_id=qr_session.id,
            amount=qr_session.amount,
            status="SUCCESS",
            face_verified=face_verified,
            remarks="Cardless QR Withdrawal with 2FA",
            timestamp=datetime.datetime.utcnow()
        )
        db.add(transaction)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database transaction error: {str(e)}")

    # --- Real-Time Sync: Notify ATM Terminal via WebSocket ---
    await manager.send_event(qr_session.session_id, {
        "event": "DISPENSE_SUCCESS",
        "tx_id": tx_id,
        "amount": qr_session.amount,
        "user_name": user.full_name,
        "atm_code": atm.terminal_code,
        "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    })

    return {
        "status": "SUCCESS",
        "message": f"Withdrawal of ₹{qr_session.amount:,.2f} authorized successfully! The ATM is now dispensing your cash.",
        "transaction_id": tx_id,
        "amount": qr_session.amount,
        "remaining_balance": user.balance,
        "face_verified": face_verified
    }

@app.get("/api/transactions")
def get_transactions(db: Session = Depends(get_db)):
    """Fetch audit history for college viva demo."""
    txs = db.query(models.Transaction).order_by(models.Transaction.id.desc()).limit(15).all()
    return [
        {
            "tx_id": t.transaction_id,
            "user": t.user.full_name,
            "atm": t.atm.terminal_code,
            "amount": t.amount,
            "face_verified": t.face_verified,
            "status": t.status,
            "timestamp": t.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        } for t in txs
    ]

# ----------------- FRONTEND UI ROUTING -----------------
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
os.makedirs(FRONTEND_DIR, exist_ok=True)

@app.get("/", response_class=HTMLResponse)
def index_page():
    with open(os.path.join(FRONTEND_DIR, "index.html"), "r", encoding="utf-8") as f:
        return f.read()

@app.get("/atm", response_class=HTMLResponse)
def atm_page():
    with open(os.path.join(FRONTEND_DIR, "atm.html"), "r", encoding="utf-8") as f:
        return f.read()

@app.get("/mobile", response_class=HTMLResponse)
def mobile_page():
    with open(os.path.join(FRONTEND_DIR, "mobile.html"), "r", encoding="utf-8") as f:
        return f.read()
