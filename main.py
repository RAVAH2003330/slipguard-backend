# main.py
import io
import os
import hashlib
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, Depends, UploadFile, File, Form, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from PIL import Image

from models import Base, MerchantAccount, TransactionSlip
from forensic import inspect_slip_with_gemini

# 1. Database Initialization (SQLite for local testing / PostgreSQL for production)
DATABASE_URL = "sqlite:///./slipguard.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 2. App & Middleware
app = FastAPI(title="SlipGuard AI Central SaaS Engine", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PAYHERE_SECRET = "YOUR_PAYHERE_MERCHANT_SECRET"

# =====================================================================
# Endpoints
# =====================================================================

# 1. Verification Endpoint (WooCommerce Checkout එකෙන් Call වන Endpoint එක)
@app.post("/api/v1/verify-slip")
async def verify_slip_endpoint(
    order_id: str = Form(...),
    expected_amount: float = Form(...),
    slip_file: UploadFile = File(...),
    x_api_key: str = Header(None),
    db: Session = Depends(get_db)
):
    if not x_api_key:
        raise HTTPException(status_code=401, detail="X-API-KEY header is missing")

    # A. Merchant Authentication
    merchant = db.query(MerchantAccount).filter(MerchantAccount.api_key == x_api_key).first()
    if not merchant:
        raise HTTPException(status_code=401, detail="Invalid Merchant API Key")

    # B. Subscription Status & Credit Check
    now = datetime.utcnow()
    is_active = (merchant.subscription_status in ["ACTIVE", "TRIAL"]) and (
        merchant.subscription_expires_at is None or merchant.subscription_expires_at > now
    )
    if not is_active:
        return {
            "verdict": "SUBSCRIPTION_REQUIRED",
            "error": "ඔබගේ SlipGuard මාසික Subscription එක කල් ඉකුත් වී ඇත. කරුණාකර renew කරන්න."
        }

    if merchant.used_credits_this_month >= merchant.monthly_limit:
        return {
            "verdict": "LIMIT_EXCEEDED",
            "error": "මෙම මස සඳහා වෙන් කළ Slips සීමාව අවසන්. කරුණාකර Plan එක Upgrade කරන්න."
        }

    # C. Image Processing
    contents = await slip_file.read()
    try:
        pil_img = Image.open(io.BytesIO(contents))
        if pil_img.mode != "RGB":
            pil_img = pil_img.convert("RGB")
        pil_img.thumbnail((1200, 1200))
    except Exception:
        raise HTTPException(status_code=400, detail="Corrupted image file")

    # D. Gemini AI Inspection
    analysis = inspect_slip_with_gemini(pil_img)
    verdict = analysis.get("verdict", "SUSPICIOUS")
    risk_score = float(analysis.get("risk_score_percentage", 100))
    ref_no = analysis.get("reference_number")
    detected_amount = float(analysis.get("amount", 0.0))
    bank_name = analysis.get("bank_name", "Unknown")

    # E. Duplicate Slip Prevention Check
    if ref_no and str(ref_no).lower() not in ["null", "none", "n/a", ""]:
        duplicate = db.query(TransactionSlip).filter(
            TransactionSlip.merchant_id == merchant.id,
            TransactionSlip.reference_number == ref_no
        ).first()
        if duplicate:
            return {
                "verdict": "DUPLICATE",
                "risk_score": 100,
                "detected_amount": detected_amount,
                "reference_number": ref_no,
                "bank_name": bank_name,
                "error": "මෙම රිසිට්පත මීට පෙරද ඉදිරිපත් කර ඇත."
            }

    # F. Deduct Usage Credit & Save Slip Record
    merchant.used_credits_this_month += 1
    
    amount_matches = abs(detected_amount - expected_amount) <= 2.0
    is_approved = (verdict == "CLEAN / LOW RISK") and (risk_score <= 25) and amount_matches

    slip_record = TransactionSlip(
        merchant_id=merchant.id,
        order_id=order_id,
        reference_number=ref_no,
        bank_name=bank_name,
        detected_amount=detected_amount,
        expected_amount=expected_amount,
        verdict=verdict,
        risk_score=risk_score,
        status="APPROVED" if is_approved else "REJECTED",
        anomaly_reasons="; ".join(analysis.get("anomaly_reasons", []))
    )
    db.add(slip_record)
    db.commit()

    return {
        "verdict": verdict,
        "risk_score": risk_score,
        "detected_amount": detected_amount,
        "reference_number": ref_no,
        "bank_name": bank_name
    }


# 2. Merchant Status Endpoint (Plugin Settings Page එකේ Live Status පෙන්වීමට)
@app.get("/api/v1/merchant-status")
async def get_merchant_status(x_api_key: str = Header(...), db: Session = Depends(get_db)):
    merchant = db.query(MerchantAccount).filter(MerchantAccount.api_key == x_api_key).first()
    if not merchant:
        raise HTTPException(status_code=401, detail="Invalid API Key")

    now = datetime.utcnow()
    is_active = (merchant.subscription_status in ["ACTIVE", "TRIAL"]) and (
        merchant.subscription_expires_at is None or merchant.subscription_expires_at > now
    )

    return {
        "business_name": merchant.business_name,
        "plan_name": merchant.subscription_plan,
        "is_active": is_active,
        "used_slips": merchant.used_credits_this_month,
        "total_limit": merchant.monthly_limit,
        "expires_at": merchant.subscription_expires_at.strftime("%Y-%m-%d") if merchant.subscription_expires_at else "Unlimited / Trial"
    }


# 3. PayHere Subscription Webhook (Auto-Renewal)
@app.post("/webhook/payhere-subscription")
async def payhere_ipn(
    merchant_id: str = Form(...),
    order_id: str = Form(...),
    payhere_amount: str = Form(...),
    payhere_currency: str = Form(...),
    status_code: str = Form(...),
    md5sig: str = Form(...),
    custom_1: str = Form(...),  # Merchant ID pass කරනු ලැබේ
    db: Session = Depends(get_db)
):
    # Verify MD5 Signature
    secret_hash = hashlib.md5(PAYHERE_SECRET.encode('utf-8')).hexdigest().upper()
    check_str = f"{merchant_id}{order_id}{payhere_amount}{payhere_currency}{status_code}{secret_hash}"
    calculated_md5 = hashlib.md5(check_str.encode('utf-8')).hexdigest().upper()

    if calculated_md5 != md5sig:
        raise HTTPException(status_code=400, detail="Invalid PayHere MD5 Signature")

    if status_code == "2":  # Success
        merchant = db.query(MerchantAccount).filter(MerchantAccount.id == int(custom_1)).first()
        if merchant:
            now = datetime.utcnow()
            if merchant.subscription_expires_at and merchant.subscription_expires_at > now:
                merchant.subscription_expires_at += timedelta(days=30)
            else:
                merchant.subscription_expires_at = now + timedelta(days=30)

            merchant.subscription_status = "ACTIVE"
            merchant.used_credits_this_month = 0
            db.commit()
            return {"status": "success"}

    return {"status": "ignored"}