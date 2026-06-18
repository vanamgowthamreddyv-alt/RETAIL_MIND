"""
🏪 SHOP SETTINGS API — AI Shop Pro Enterprise Backend
Covers:
  - Get/Update shop profile (name, address, phone, UPI ID, GST)
  - Upload shop logo (stored as URL or base64)
  - Toggle online store on/off
  - Get QR code data for UPI payment
"""

import os
import qrcode
import base64
from io import BytesIO
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db import get_db
from models import ShopProfile, User, UniversalTransaction
from security import get_current_user, owner_only, sanitize_input

router = APIRouter(prefix="/shop", tags=["Shop Settings"])

# =====================
# SCHEMAS
# =====================
class ShopProfileCreate(BaseModel):
    shop_name: str = Field(..., min_length=2, max_length=100)
    address: Optional[str] = None
    phone: Optional[str] = Field(None, min_length=10, max_length=10, pattern=r"^\d{10}$")
    upi_id: Optional[str] = None
    gst_number: Optional[str] = None
    logo_url: Optional[str] = None

class ShopProfileUpdate(BaseModel):
    shop_name: Optional[str] = Field(None, min_length=2, max_length=100)
    address: Optional[str] = None
    phone: Optional[str] = Field(None, min_length=10, max_length=10, pattern=r"^\d{10}$")
    upi_id: Optional[str] = None
    gst_number: Optional[str] = None
    logo_url: Optional[str] = None
    is_online_store_enabled: Optional[bool] = None

class ShopProfileResponse(BaseModel):
    id: int
    shop_id: int
    shop_name: str
    address: Optional[str]
    phone: Optional[str]
    upi_id: Optional[str]
    gst_number: Optional[str]
    logo_url: Optional[str]
    is_online_store_enabled: bool

    class Config:
        from_attributes = True

# =====================
# HELPERS
# =====================
def _generate_upi_qr_base64(upi_id: str, payee_name: str, amount: Optional[float] = None) -> str:
    """Generate a UPI QR code and return it as a base64 encoded PNG string"""
    if amount:
        upi_uri = f"upi://pay?pa={upi_id}&pn={payee_name}&am={amount:.2f}&cu=INR"
    else:
        upi_uri = f"upi://pay?pa={upi_id}&pn={payee_name}&cu=INR"

    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(upi_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    encoded = base64.b64encode(buffer.read()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"

# =====================
# ENDPOINTS
# =====================

@router.post("/profile", response_model=ShopProfileResponse)
def create_shop_profile(
    data: ShopProfileCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(owner_only),
):
    """Create the shop profile (one per owner)"""
    owner_id = current_user["user_id"]

    # Check if profile already exists
    existing = db.query(ShopProfile).filter(ShopProfile.shop_id == owner_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="Shop profile already exists. Use PUT to update.")

    # Sanitize inputs
    shop_name = sanitize_input(data.shop_name, "shop_name")
    address = sanitize_input(data.address or "", "address") or None

    profile = ShopProfile(
        shop_id=owner_id,
        shop_name=shop_name,
        address=address,
        phone=data.phone,
        upi_id=data.upi_id,
        gst_number=data.gst_number,
        logo_url=data.logo_url,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@router.get("/profile", response_model=ShopProfileResponse)
def get_shop_profile(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get the current user's shop profile"""
    owner_id = current_user["user_id"]
    profile = db.query(ShopProfile).filter(ShopProfile.shop_id == owner_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Shop profile not found. Please create one first.")
    return profile


@router.put("/profile", response_model=ShopProfileResponse)
def update_shop_profile(
    data: ShopProfileUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(owner_only),
):
    """Update shop profile (all fields optional)"""
    owner_id = current_user["user_id"]
    profile = db.query(ShopProfile).filter(ShopProfile.shop_id == owner_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Shop profile not found. Create one first via POST /shop/profile")

    update_data = data.model_dump(exclude_none=True)
    for key, value in update_data.items():
        if isinstance(value, str):
            value = sanitize_input(value, key)
        setattr(profile, key, value)

    db.commit()
    db.refresh(profile)
    return profile


@router.get("/upi-qr")
def get_upi_qr(
    amount: Optional[float] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Generate a UPI QR code for the shop.
    Optionally pass ?amount=250.00 to create a fixed-amount QR for an invoice.
    Returns a base64 PNG for embedding directly in the app.
    """
    owner_id = current_user["user_id"]
    profile = db.query(ShopProfile).filter(ShopProfile.shop_id == owner_id).first()

    if not profile:
        raise HTTPException(status_code=404, detail="Shop profile not found.")
    if not profile.upi_id:
        raise HTTPException(status_code=422, detail="No UPI ID configured. Please update your shop profile.")

    qr_base64 = _generate_upi_qr_base64(
        upi_id=profile.upi_id,
        payee_name=profile.shop_name,
        amount=amount,
    )
    return {
        "upi_id": profile.upi_id,
        "payee_name": profile.shop_name,
        "amount": amount,
        "qr_base64": qr_base64,
        "upi_uri": f"upi://pay?pa={profile.upi_id}&pn={profile.shop_name}&cu=INR"
        + (f"&am={amount:.2f}" if amount else ""),
    }


@router.post("/toggle-online-store")
def toggle_online_store(
    enable: bool,
    db: Session = Depends(get_db),
    current_user: dict = Depends(owner_only),
):
    """Enable or disable the online store for this shop"""
    owner_id = current_user["user_id"]
    profile = db.query(ShopProfile).filter(ShopProfile.shop_id == owner_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Shop profile not found.")

    profile.is_online_store_enabled = enable
    db.commit()
    return {
        "message": f"Online store {'ENABLED' if enable else 'DISABLED'} successfully.",
        "is_online_store_enabled": enable,
    }


@router.get("/public/{shop_id}")
def get_public_shop_info(
    shop_id: int,
    db: Session = Depends(get_db),
):
    """Public endpoint: Returns basic shop info for the Customer app (name, location)"""
    profile = db.query(ShopProfile).filter(
        ShopProfile.shop_id == shop_id,
        ShopProfile.is_online_store_enabled == True,
    ).first()

    if not profile:
        raise HTTPException(status_code=404, detail="Shop not found or online store is disabled.")

    # Return LIMITED info (never expose UPI or GST to public)
    return {
        "shop_id": profile.shop_id,
        "shop_name": profile.shop_name,
        "address": profile.address,
        "phone": profile.phone,
        "logo_url": profile.logo_url,
    }
