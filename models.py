import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    full_name = Column(String(100), nullable=False)
    account_number = Column(String(20), unique=True, nullable=False)
    balance = Column(Float, default=10000.0, nullable=False)
    pin_hash = Column(String(128), nullable=False)
    face_auth_enabled = Column(Boolean, default=True, nullable=False)
    face_reference_b64 = Column(Text, nullable=True)  # Base64 image string for enrolled face
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    transactions = relationship("Transaction", back_populates="user")


class ATMTerminal(Base):
    __tablename__ = "atm_terminals"

    id = Column(Integer, primary_key=True, index=True)
    terminal_code = Column(String(50), unique=True, index=True, nullable=False)
    location = Column(String(150), nullable=False)
    cash_balance = Column(Float, default=50000.0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    sessions = relationship("QRSession", back_populates="atm")
    transactions = relationship("Transaction", back_populates="atm")


class QRSession(Base):
    __tablename__ = "qr_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), unique=True, index=True, nullable=False)
    atm_id = Column(Integer, ForeignKey("atm_terminals.id"), nullable=False)
    amount = Column(Float, nullable=False)
    nonce = Column(String(64), nullable=False)
    qr_token = Column(String(256), nullable=False)
    attempts_count = Column(Integer, default=1, nullable=False)  # Max 3 attempts
    expires_at = Column(Float, nullable=False)  # Unix timestamp
    status = Column(String(20), default="PENDING", nullable=False)  # PENDING, AUTHORIZED, EXPIRED, USED, CANCELLED
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    atm = relationship("ATMTerminal", back_populates="sessions")
    transaction = relationship("Transaction", back_populates="qr_session", uselist=False)


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(String(64), unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    atm_id = Column(Integer, ForeignKey("atm_terminals.id"), nullable=False)
    qr_session_id = Column(Integer, ForeignKey("qr_sessions.id"), nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(String(20), default="SUCCESS", nullable=False)
    face_verified = Column(Boolean, default=False, nullable=False)
    remarks = Column(String(200), nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="transactions")
    atm = relationship("ATMTerminal", back_populates="transactions")
    qr_session = relationship("QRSession", back_populates="transaction")

