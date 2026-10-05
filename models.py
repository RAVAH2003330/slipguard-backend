# models.py
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class MerchantAccount(Base):
    __tablename__ = "merchants"

    id = Column(Integer, primary_key=True, index=True)
    business_name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    api_key = Column(String(100), unique=True, index=True, nullable=False)
    
    # Subscription Management
    subscription_plan = Column(String(50), default="STARTER")  # STARTER, PRO, UNLIMITED
    subscription_status = Column(String(50), default="TRIAL")  # TRIAL, ACTIVE, EXPIRED
    monthly_limit = Column(Integer, default=50)                 # මාසික Slips ගණන
    used_credits_this_month = Column(Integer, default=0)
    subscription_expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    slips = relationship("TransactionSlip", back_populates="merchant")

class TransactionSlip(Base):
    __tablename__ = "transaction_slips"

    id = Column(Integer, primary_key=True, index=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False)
    order_id = Column(String(100), nullable=False)
    
    reference_number = Column(String(100), index=True, nullable=True)
    bank_name = Column(String(100), nullable=True)
    detected_amount = Column(Float, default=0.0)
    expected_amount = Column(Float, default=0.0)
    
    # Forensic AI Results
    verdict = Column(String(50), nullable=False) # CLEAN / LOW RISK, TAMPERED, DUPLICATE
    risk_score = Column(Float, default=0.0)
    anomaly_reasons = Column(Text, nullable=True)
    
    status = Column(String(50), default="PENDING") # APPROVED, REJECTED
    created_at = Column(DateTime, default=datetime.utcnow)

    merchant = relationship("MerchantAccount", back_populates="slips")