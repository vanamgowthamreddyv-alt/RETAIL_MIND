"""
🧾 INVOICES & BILLING API — AI Shop Pro Enterprise Backend
Covers:
  - Generate invoices
  - Accept offline-synced invoices from app (`/sync` endpoints)
  - Auto-deduct inventory
  - Auto-log in Universal Transactions
  - GST extraction and filtering
"""

from typing import Optional, List
from datetime import datetime, date
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from db import get_db
from models import (
    Invoice, InvoiceLineItem, Product, Customer,
    UniversalTransaction, StockMovement
)
from security import owner_only, worker_or_owner, sanitize_input

router = APIRouter(prefix="/api/invoices", tags=["invoices & billing"])

# =====================
# SCHEMAS
# =====================
class InvoiceLineItemCreate(BaseModel):
    product_id: Optional[int] = None
    product_name: str
    quantity: int = Field(..., gt=0)
    unit_price: float = Field(..., ge=0)

class InvoiceSyncCreate(BaseModel):
    invoice_number: str
    customer_phone: Optional[str] = Field(None, min_length=10, max_length=10, pattern=r"^\d{10}$")
    customer_name: Optional[str] = None
    total_amount: float
    paid_amount: float = 0
    tax: float = 0
    payment_status: str = "PAID"
    line_items: List[InvoiceLineItemCreate]
    invoice_date: str  # YYYY-MM-DD
    notes: Optional[str] = None

class InvoiceResponse(BaseModel):
    id: int
    invoice_number: str
    total_amount: float
    paid_amount: float
    status: str
    payment_status: str
    invoice_date: date
    created_at: datetime

    class Config:
        from_attributes = True

# =====================
# ENDPOINTS
# =====================

@router.post("/sync")
def sync_offline_invoice(
    data: InvoiceSyncCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(worker_or_owner),
):
    """
    Accept an invoice generated while the app was offline.
    This creates the invoice, deducts inventory, and logs revenue.
    """
    shop_id = current_user["user_id"]
    invoice_number = sanitize_input(data.invoice_number, "invoice_number")

    # Check for duplicate sync (idempotency)
    existing = db.query(Invoice).filter(
        Invoice.user_id == shop_id,
        Invoice.invoice_number == invoice_number
    ).first()
    if existing:
        return {"message": "Invoice already synced.", "invoice_id": existing.id}

    # Find/Create Customer
    customer_id = None
    if data.customer_phone:
        phone = sanitize_input(data.customer_phone, "customer_phone")
        cust = db.query(Customer).filter(
            Customer.user_id == shop_id,
            Customer.phone == phone
        ).first()
        if not cust:
            cust = Customer(
                user_id=shop_id,
                name=sanitize_input(data.customer_name or "Cash Customer", "customer_name"),
                phone=phone
            )
            db.add(cust)
            db.flush()
        customer_id = cust.id

    try:
        inv_date = datetime.strptime(data.invoice_date, "%Y-%m-%d").date()
    except ValueError:
        inv_date = date.today()

    # Create Invoice
    invoice = Invoice(
        user_id=shop_id,
        customer_id=customer_id,
        customer_name=sanitize_input(data.customer_name or "Cash Customer", "customer_name"),
        customer_phone=data.customer_phone,
        invoice_number=invoice_number,
        invoice_date=inv_date,
        due_date=inv_date,
        subtotal=data.total_amount - data.tax,
        tax=data.tax,
        total_amount=data.total_amount,
        paid_amount=data.paid_amount,
        status="SENT",
        payment_status=data.payment_status.upper() if data.payment_status else "PAID",
        source="OFFLINE_SYNC",
        notes=sanitize_input(data.notes or "", "notes"),
    )
    db.add(invoice)
    db.flush()

    # Process Line Items & Deduct Inventory
    for item in data.line_items:
        line_total = item.quantity * item.unit_price
        db_line = InvoiceLineItem(
            invoice_id=invoice.id,
            product_id=item.product_id,
            description=sanitize_input(item.product_name, "product_name"),
            quantity=item.quantity,
            unit_price=item.unit_price,
            line_total=line_total,
        )
        db.add(db_line)

        # Inventory Auto-Deduction
        if item.product_id:
            product = db.query(Product).filter(
                Product.id == item.product_id,
                Product.user_id == shop_id
            ).first()
            if product:
                product.current_stock = max(0, (product.current_stock or 0) - item.quantity)
                # Log stock movement
                mov = StockMovement(
                    product_id=product.id,
                    movement_type="OUT",
                    quantity=item.quantity,
                    reason="Sales Sync",
                    reference_id=invoice_number,
                )
                db.add(mov)

    # Universal Journal Entry
    tx = UniversalTransaction(
        shop_id=shop_id,
        tx_type="INCOME",
        category="SALE",
        amount=data.paid_amount,
        reference_id=invoice_number,
        description=f"Sales Sync: {invoice_number}",
        tx_date=datetime.combine(inv_date, datetime.min.time()),
    )
    db.add(tx)

    db.commit()
    return {"message": "Invoice synced and inventory deducted.", "invoice_id": invoice.id}


@router.get("/", response_model=List[InvoiceResponse])
def get_invoices(
    status: Optional[str] = None,
    payment_status: Optional[str] = None,
    source: Optional[str] = None,
    skip: int = Query(0),
    limit: int = Query(100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(owner_only),
):
    """Get all invoices for the shop"""
    shop_id = current_user["user_id"]
    query = db.query(Invoice).filter(Invoice.user_id == shop_id)
    
    if status:
        query = query.filter(Invoice.status == status.upper())
    if payment_status:
        query = query.filter(Invoice.payment_status == payment_status.upper())
    if source:
        query = query.filter(Invoice.source == source.upper())
        
    return query.order_by(desc(Invoice.created_at)).offset(skip).limit(limit).all()


@router.get("/{invoice_id}", response_model=InvoiceResponse)
def get_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(worker_or_owner),
):
    """Get specific invoice details"""
    shop_id = current_user["user_id"]
    invoice = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.user_id == shop_id
    ).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice

@router.delete("/{invoice_id}")
def delete_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(owner_only),
):
    """Delete an invoice (Owner only)"""
    shop_id = current_user["user_id"]
    invoice = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.user_id == shop_id
    ).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    db.delete(invoice)
    db.commit()
    return {"message": "Invoice deleted securely."}
