"""
🎁 GIFT CARDS & 🧾 GST API — AI Shop Pro Enterprise Backend
Covers:
  - Issue Digital Gift Cards
  - Validate & Redeem Gift Cards
  - Aggregate invoices for GSTR-1 JSON export
"""

from typing import Optional, List
from datetime import date, datetime, timezone
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func

from db import get_db
from models import GiftCard, Invoice, ShopProfile
from security import owner_only, worker_or_owner, sanitize_input

router = APIRouter(tags=["GST & Gift Cards"])

# =====================
# GIFT CARDS
# =====================
class GiftCardCreate(BaseModel):
    card_code: str = Field(..., min_length=6, max_length=20)
    initial_balance: float = Field(..., gt=0)
    issued_to: Optional[str] = None
    expiry_date: Optional[date] = None

class GiftCardRedeem(BaseModel):
    card_code: str
    amount_to_deduct: float = Field(..., gt=0)

@router.post("/gift-cards", tags=["Gift Cards"])
def issue_gift_card(
    data: GiftCardCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(owner_only),
):
    """Issue a new digital gift card"""
    shop_id = current_user["user_id"]
    code = sanitize_input(data.card_code, "card_code")

    existing = db.query(GiftCard).filter(GiftCard.card_code == code).first()
    if existing:
        raise HTTPException(status_code=409, detail="Card code already exists.")

    gc = GiftCard(
        shop_id=shop_id,
        card_code=code,
        initial_balance=data.initial_balance,
        current_balance=data.initial_balance,
        issued_to=sanitize_input(data.issued_to or "", "issued_to"),
        expiry_date=data.expiry_date,
    )
    db.add(gc)
    db.commit()

    return {"message": "Gift card issued successfully.", "card_code": code, "balance": data.initial_balance}


@router.post("/gift-cards/redeem", tags=["Gift Cards"])
def redeem_gift_card(
    data: GiftCardRedeem,
    db: Session = Depends(get_db),
    current_user: dict = Depends(worker_or_owner),
):
    """Redeem or validate a gift card during checkout"""
    shop_id = current_user["user_id"]
    code = sanitize_input(data.card_code, "card_code")

    gc = db.query(GiftCard).filter(
        GiftCard.shop_id == shop_id,
        GiftCard.card_code == code,
        GiftCard.is_active == True
    ).first()

    if not gc:
        raise HTTPException(status_code=404, detail="Invalid or inactive gift card.")
    
    if gc.expiry_date and gc.expiry_date < date.today():
        raise HTTPException(status_code=400, detail="Gift card has expired.")

    balance = float(gc.current_balance)
    if data.amount_to_deduct > balance:
        raise HTTPException(status_code=400, detail=f"Insufficient balance. Only ₹{balance:.2f} available.")

    gc.current_balance = balance - data.amount_to_deduct
    if gc.current_balance == 0:
        gc.is_active = False

    db.commit()

    return {
        "message": f"Successfully deducted ₹{data.amount_to_deduct:.2f}",
        "remaining_balance": float(gc.current_balance),
    }


# =====================
# GST EXPORT
# =====================
@router.get("/gst/export-gstr1", tags=["GST"])
def export_gstr1(
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2000),
    db: Session = Depends(get_db),
    current_user: dict = Depends(owner_only),
):
    """Aggregate all sales for a month and generate GSTR-1 JSON schema"""
    shop_id = current_user["user_id"]
    profile = db.query(ShopProfile).filter(ShopProfile.shop_id == shop_id).first()

    if not profile or not profile.gst_number:
        raise HTTPException(status_code=400, detail="GST number not configured in Shop Settings.")

    # Filter invoices for the month
    invoices = db.query(Invoice).filter(
        Invoice.user_id == shop_id,
        func.extract('month', Invoice.invoice_date) == month,
        func.extract('year', Invoice.invoice_date) == year,
    ).all()

    total_taxable_value = 0
    total_tax = 0
    b2c_invoices = []

    for inv in invoices:
        total_taxable_value += float(inv.subtotal)
        total_tax += float(inv.tax)
        b2c_invoices.append({
            "inum": inv.invoice_number,
            "idt": inv.invoice_date.strftime("%d-%m-%Y"),
            "val": float(inv.total_amount),
            "pos": "27-Maharashtra", # Simplified for MVP
            "txval": float(inv.subtotal),
            "iamt": float(inv.tax),
        })

    # Strict GSTR-1 JSON Schema 
    gstr1_json = {
        "gstin": profile.gst_number,
        "fp": f"{month:02d}{year}",
        "version": "GST1.0.0",
        "b2cs": [
            {
                "sply_ty": "INTRA",
                "txval": total_taxable_value,
                "typ": "OE",
                "iamt": total_tax,
                "rt": 18.0 # Assuming flat 18% for MVP
            }
        ],
        "b2c": b2c_invoices,
    }

    return {
        "message": f"GSTR-1 data generated for {month:02d}/{year}",
        "total_invoices": len(invoices),
        "gstr1_data": gstr1_json
    }
