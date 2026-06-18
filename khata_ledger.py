"""
📒 KHATA LEDGER API — AI Shop Pro Enterprise Backend
Covers:
  - Create/get customer credit (Khata) accounts
  - Add credit (customer bought on Khata)
  - Record repayment (customer paid back)
  - Full transaction history
  - WhatsApp reminder URL generation
  - Auto-write to UniversalTransaction journal
"""

from typing import Optional, List
from datetime import datetime, timezone
from fastapi import APIRouter, Path, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func

from db import get_db
from models import KhataBalance, KhataHistory, UniversalTransaction
from security import owner_only, sanitize_input
import urllib.parse

router = APIRouter(prefix="/khata", tags=["Khata Ledger"])

# =====================
# SCHEMAS
# =====================
class KhataEntryCreate(BaseModel):
    customer_phone: str = Field(..., min_length=10, max_length=10, pattern=r"^\d{10}$")
    customer_name: Optional[str] = None
    amount: float = Field(..., gt=0)
    description: Optional[str] = None

class KhataRepayment(BaseModel):
    customer_phone: str = Field(..., min_length=10, max_length=10, pattern=r"^\d{10}$")
    amount: float = Field(..., gt=0)
    description: Optional[str] = "Payment received"

class KhataHistoryOut(BaseModel):
    id: int
    transaction_type: str
    amount: float
    reference_id: Optional[str]
    description: Optional[str]
    transaction_date: datetime

    class Config:
        from_attributes = True

# =====================
# HELPERS
# =====================
def _get_or_create_khata(db: Session, shop_id: int, customer_phone: str, customer_name: Optional[str]) -> KhataBalance:
    """Get existing Khata account or create a new one"""
    khata = db.query(KhataBalance).filter(
        KhataBalance.shop_id == shop_id,
        KhataBalance.customer_phone == customer_phone,
    ).first()
    if not khata:
        khata = KhataBalance(
            shop_id=shop_id,
            customer_phone=customer_phone,
            customer_name=customer_name or "Customer",
            khata_balance=0,
        )
        db.add(khata)
        db.flush()  # Get ID without commit
    elif customer_name and not khata.customer_name:
        khata.customer_name = customer_name
    return khata

def _write_universal_tx(db: Session, shop_id: int, tx_type: str, category: str, amount: float, ref_id: str, desc: str):
    """Write every Khata movement to the universal journal"""
    tx = UniversalTransaction(
        shop_id=shop_id,
        tx_type=tx_type,
        category=category,
        amount=amount,
        reference_id=ref_id,
        description=desc,
    )
    db.add(tx)

# =====================
# ENDPOINTS
# =====================

@router.post("/credit")
def add_khata_credit(
    data: KhataEntryCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(owner_only),
):
    """Record that a customer bought on credit (Udhar/Khata)"""
    shop_id = current_user["user_id"]
    desc = sanitize_input(data.description or "Purchased on Khata", "description")

    khata = _get_or_create_khata(db, shop_id, data.customer_phone, data.customer_name)
    khata.khata_balance = float(khata.khata_balance or 0) + data.amount
    khata.last_transaction = datetime.now(timezone.utc)

    history = KhataHistory(
        khata_id=khata.id,
        transaction_type="INVOICE",
        amount=data.amount,
        description=desc,
        reference_id=f"KHATA-{khata.id}-{int(datetime.now().timestamp())}",
    )
    db.add(history)

    _write_universal_tx(db, shop_id, "INCOME", "KHATA_CREDIT",
        data.amount, f"KHATA-{khata.id}", f"Khata credit for {data.customer_phone}")

    db.commit()
    return {
        "message": "Khata credit recorded successfully",
        "customer_phone": data.customer_phone,
        "amount_added": data.amount,
        "total_outstanding": float(khata.khata_balance),
    }


@router.post("/repayment")
def record_repayment(
    data: KhataRepayment,
    db: Session = Depends(get_db),
    current_user: dict = Depends(owner_only),
):
    """Record a customer's partial or full repayment"""
    shop_id = current_user["user_id"]

    khata = db.query(KhataBalance).filter(
        KhataBalance.shop_id == shop_id,
        KhataBalance.customer_phone == data.customer_phone,
    ).first()

    if not khata:
        raise HTTPException(status_code=404, detail="No Khata account found for this customer.")

    current_balance = float(khata.khata_balance or 0)
    if data.amount > current_balance:
        raise HTTPException(
            status_code=400,
            detail=f"Payment of ₹{data.amount} exceeds outstanding balance of ₹{current_balance:.2f}"
        )

    khata.khata_balance = current_balance - data.amount
    khata.last_transaction = datetime.now(timezone.utc)

    history = KhataHistory(
        khata_id=khata.id,
        transaction_type="PAYMENT",
        amount=data.amount,
        description=data.description,
        reference_id=f"PAY-{khata.id}-{int(datetime.now().timestamp())}",
    )
    db.add(history)

    _write_universal_tx(db, shop_id, "INCOME", "KHATA_REPAY",
        data.amount, f"KHATA-PAY-{khata.id}", f"Khata repayment from {data.customer_phone}")

    db.commit()
    return {
        "message": "Repayment recorded successfully",
        "customer_phone": data.customer_phone,
        "amount_paid": data.amount,
        "remaining_balance": float(khata.khata_balance),
    }


@router.get("/customers")
def list_khata_customers(
    skip: int = 0,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current_user: dict = Depends(owner_only),
):
    """List all customers with outstanding Khata balances"""
    shop_id = current_user["user_id"]
    accounts = (
        db.query(KhataBalance)
        .filter(KhataBalance.shop_id == shop_id, KhataBalance.khata_balance > 0)
        .order_by(KhataBalance.khata_balance.desc())
        .offset(skip).limit(limit).all()
    )
    total_outstanding = db.query(func.sum(KhataBalance.khata_balance)).filter(
        KhataBalance.shop_id == shop_id
    ).scalar() or 0

    return {
        "total_outstanding": float(total_outstanding),
        "customers": [
            {
                "id": a.id,
                "customer_name": a.customer_name,
                "customer_phone": a.customer_phone,
                "khata_balance": float(a.khata_balance),
                "last_transaction": a.last_transaction,
            }
            for a in accounts
        ],
    }


@router.get("/history/{customer_phone}", response_model=List[KhataHistoryOut])
def get_customer_khata_history(
    customer_phone: str = Path(..., min_length=10, max_length=10, pattern=r"^\d{10}$"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(owner_only),
):
    """Full transaction history for a specific customer"""
    shop_id = current_user["user_id"]
    khata = db.query(KhataBalance).filter(
        KhataBalance.shop_id == shop_id,
        KhataBalance.customer_phone == customer_phone,
    ).first()

    if not khata:
        raise HTTPException(status_code=404, detail="No Khata found for this customer.")

    history = (
        db.query(KhataHistory)
        .filter(KhataHistory.khata_id == khata.id)
        .order_by(KhataHistory.transaction_date.desc())
        .all()
    )
    return history


@router.get("/whatsapp-reminder/{customer_phone}")
def get_whatsapp_reminder_url(
    customer_phone: str = Path(..., min_length=10, max_length=10, pattern=r"^\d{10}$"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(owner_only),
):
    """Generate a pre-filled WhatsApp reminder URL for a customer with outstanding Khata"""
    shop_id = current_user["user_id"]
    khata = db.query(KhataBalance).filter(
        KhataBalance.shop_id == shop_id,
        KhataBalance.customer_phone == customer_phone,
    ).first()

    if not khata:
        raise HTTPException(status_code=404, detail="No Khata found for this customer.")

    balance = float(khata.khata_balance or 0)
    if balance <= 0:
        return {"message": "Customer has no outstanding balance.", "balance": 0}

    message = (
        f"Namaste {khata.customer_name or 'ji'} 🙏\n\n"
        f"Aapka khata balance hai: *₹{balance:.2f}*\n\n"
        f"Kripaya jaldi payment karein.\n\n"
        f"Shukriya! 🏪"
    )
    encoded_msg = urllib.parse.quote(message)
    # Remove leading + or 0 for WhatsApp international format
    clean_phone = customer_phone.lstrip("+").lstrip("0")
    wa_url = f"https://wa.me/91{clean_phone}?text={encoded_msg}"

    return {
        "customer_name": khata.customer_name,
        "customer_phone": customer_phone,
        "outstanding_balance": balance,
        "whatsapp_url": wa_url,
        "message_preview": message,
    }
