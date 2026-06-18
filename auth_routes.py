import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db import get_db
from models import User, ShopProfile
from security import hash_password, verify_password, create_access_token, ROLE_OWNER
from email_notifications import EmailNotificationService

router = APIRouter()
logger = logging.getLogger(__name__)

class UserCreate(BaseModel):
    username: str
    password: str
    email: str

class UserLogin(BaseModel):
    username: str
    password: str

@router.post("/register")
def register(user: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.user_name == user.username).first():
        raise HTTPException(status_code=400, detail="Username already registered")
    
    hashed_pwd = hash_password(user.password)
    
    # 🔒 Assign strict OWNER role upon registration
    new_user = User(
        user_name=user.username,
        email=user.email,
        password=hashed_pwd
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Auto-create Shop Profile
    shop_profile = ShopProfile(shop_id=new_user.id, shop_name=f"{user.username}'s Shop")
    db.add(shop_profile)
    db.commit()

    # Send Welcome Email with Credentials
    try:
        subject, body = EmailNotificationService.welcome_credentials_template(user.username, user.password, "Shop Owner")
        EmailNotificationService.send_email(
            recipient_email=user.email,
            subject=subject,
            body=body
        )
    except Exception as e:
        logger.error(f"Failed to send welcome email: {e}")

    return {"msg": "User registered successfully", "user_id": new_user.id}

import random
import time
from typing import Optional
from pydantic import BaseModel

class SendOTPRequest(BaseModel):
    email: str
    purpose: Optional[str] = "Verification"

class VerifyOTPRequest(BaseModel):
    email: str
    otp: str

otp_cache = {}

@router.post("/send-otp")
def send_otp(request: SendOTPRequest, db: Session = Depends(get_db)):
    otp_code = str(random.randint(100000, 999999))
    
    # Store in memory for 10 minutes
    otp_cache[request.email] = {
        "otp": otp_code,
        "expires_at": time.time() + 600
    }
    
    # Send email
    try:
        subject, body = EmailNotificationService.send_otp_template(otp_code, request.purpose)
        EmailNotificationService.send_email(
            recipient_email=request.email,
            subject=subject,
            body=body
        )
        return {"msg": "OTP sent successfully", "otp": otp_code} # Keep OTP in response for frontend backward compatibility if needed
    except Exception as e:
        logger.error(f"Failed to send OTP email: {e}")
        raise HTTPException(status_code=500, detail="Failed to send OTP email")

@router.post("/verify-otp")
def verify_otp(request: VerifyOTPRequest):
    record = otp_cache.get(request.email)
    
    if not record:
        raise HTTPException(status_code=400, detail="OTP not requested or expired")
        
    if time.time() > record["expires_at"]:
        del otp_cache[request.email]
        raise HTTPException(status_code=400, detail="OTP has expired")
        
    if record["otp"] != request.otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")
        
    # Valid OTP
    del otp_cache[request.email] # OTP used up
    return {"msg": "OTP verified successfully", "verified": True}

@router.post("/login")
def login(user: UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.user_name == user.username).first()
    
    if not db_user or not verify_password(user.password, db_user.password):
        raise HTTPException(status_code=400, detail="Invalid username or password")
    
    # Update last login
    db_user.last_login = datetime.utcnow()
    db.commit()

    # Create Secure JWT
    access_token = create_access_token(
        data={"sub": db_user.user_name, "user_id": db_user.id, "role": db_user.role}
    )
    
    return {"access_token": access_token, "token_type": "bearer", "role": db_user.role, "user_id": db_user.id}

@router.get("/health")
def health_check():
    return {"status": "ok", "message": "Auth API is up and running"}







