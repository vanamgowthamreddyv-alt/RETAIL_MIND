"""
🏦 BANK RECONCILIATION API — AI Shop Pro Enterprise Backend
📊 RETAIL INTELLIGENCE API — AI Shop Pro Enterprise Backend
Covers:
  - Daily UPI/Cash reconciliation entries
  - Discrepancy flagging
  - Unified P&L (Profit & Loss) from Universal Transactions
  - Expense Tracker endpoints
  - Fast-moving vs Dead-stock analysis
  - Worker Management (salary tracking, shift assignment)
"""

import json
from typing import Optional, List
from datetime import date, datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from db import get_db
from models import (
    BankReconciliation, UniversalTransaction, ShopExpense,
    Worker, Product, sales, Invoice
)
from security import owner_only, worker_or_owner, sanitize_input

router = APIRouter(tags=["Enterprise Intelligence"])

# =====================================
# EXPENSE TRACKER
# =====================================
class ExpenseCreate(BaseModel):
    category: str = Field(..., min_length=2, max_length=50)
    amount: float = Field(..., gt=0)
    description: Optional[str] = None
    expense_date: date
    payment_method: Optional[str] = "cash"

@router.post("/expenses", tags=["Expense Tracker"])
def add_expense(
    data: ExpenseCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(owner_only),
):
    """Log a shop expense (rent, salary, utilities, etc.)"""
    shop_id = current_user["user_id"]
    category = sanitize_input(data.category, "category")
    desc = sanitize_input(data.description or "", "description") or None

    expense = ShopExpense(
        shop_id=shop_id,
        category=category,
        amount=data.amount,
        description=desc,
        expense_date=data.expense_date,
        payment_method=data.payment_method,
    )
    db.add(expense)

    # Mirror to universal journal
    tx = UniversalTransaction(
        shop_id=shop_id,
        tx_type="EXPENSE",
        category=category.upper(),
        amount=data.amount,
        description=desc or f"{category} expense",
    )
    db.add(tx)
    db.commit()

    return {"message": "Expense logged successfully.", "amount": data.amount, "category": category}


@router.get("/expenses", tags=["Expense Tracker"])
def list_expenses(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    category: Optional[str] = None,
    skip: int = 0,
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    current_user: dict = Depends(owner_only),
):
    """List shop expenses with optional date/category filters"""
    shop_id = current_user["user_id"]
    q = db.query(ShopExpense).filter(ShopExpense.shop_id == shop_id)
    if start_date:
        q = q.filter(ShopExpense.expense_date >= start_date)
    if end_date:
        q = q.filter(ShopExpense.expense_date <= end_date)
    if category:
        q = q.filter(ShopExpense.category.ilike(f"%{category}%"))

    expenses = q.order_by(ShopExpense.expense_date.desc()).offset(skip).limit(limit).all()
    total = db.query(func.sum(ShopExpense.amount)).filter(ShopExpense.shop_id == shop_id).scalar() or 0

    return {
        "total_expenses": float(total),
        "expenses": [
            {
                "id": e.id,
                "category": e.category,
                "amount": float(e.amount),
                "description": e.description,
                "expense_date": e.expense_date,
                "payment_method": e.payment_method,
            }
            for e in expenses
        ],
    }


# =====================================
# WORKER MANAGEMENT
# =====================================
class WorkerCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    phone: Optional[str] = Field(None, min_length=10, max_length=10, pattern=r"^\d{10}$")
    address: Optional[str] = None
    salary: float = Field(0, ge=0)
    assigned_work: Optional[str] = None
    position: Optional[str] = "Staff"
    pin: Optional[str] = None

class WorkerUpdate(BaseModel):
    salary: Optional[float] = None
    assigned_work: Optional[str] = None
    position: Optional[str] = None
    status: Optional[str] = None
    pin: Optional[str] = None

@router.post("/workers", tags=["Worker Management"])
def add_worker(
    data: WorkerCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(owner_only),
):
    """Add a new worker/staff member"""
    shop_id = current_user["user_id"]
    worker = Worker(
        shopkeeper_id=shop_id,
        name=sanitize_input(data.name, "name"),
        phone=data.phone,
        address=data.address,
        salary=data.salary,
        assigned_work=data.assigned_work,
        position=data.position or "Staff",
        pin=data.pin,
    )
    db.add(worker)
    db.commit()
    db.refresh(worker)
    return {"message": "Worker added successfully.", "worker_id": worker.id, "name": worker.name}


@router.get("/workers", tags=["Worker Management"])
def list_workers(
    db: Session = Depends(get_db),
    current_user: dict = Depends(owner_only),
):
    """List all workers for this shop"""
    shop_id = current_user["user_id"]
    workers = db.query(Worker).filter(
        Worker.shopkeeper_id == shop_id,
        Worker.status == "active",
    ).all()

    total_monthly_salary = sum(float(w.salary or 0) for w in workers)
    return {
        "total_monthly_salary": total_monthly_salary,
        "workers": [
            {
                "id": w.id,
                "name": w.name,
                "phone": w.phone,
                "position": w.position,
                "salary": float(w.salary or 0),
                "assigned_work": w.assigned_work,
                "status": w.status,
                "join_date": w.join_date,
            }
            for w in workers
        ],
    }


@router.put("/workers/{worker_id}", tags=["Worker Management"])
def update_worker(
    worker_id: int,
    data: WorkerUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(owner_only),
):
    """Update worker details (salary, position, status)"""
    shop_id = current_user["user_id"]
    worker = db.query(Worker).filter(
        Worker.id == worker_id,
        Worker.shopkeeper_id == shop_id,
    ).first()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found.")

    update_data = data.model_dump(exclude_none=True)
    for key, value in update_data.items():
        setattr(worker, key, value)

    db.commit()
    return {"message": "Worker updated.", "worker_id": worker_id}


@router.post("/workers/{worker_id}/pay-salary", tags=["Worker Management"])
def pay_worker_salary(
    worker_id: int,
    month: str = Query(..., description="Format: YYYY-MM"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(owner_only),
):
    """Mark salary as paid for a specific month and record in expenses"""
    shop_id = current_user["user_id"]
    worker = db.query(Worker).filter(
        Worker.id == worker_id,
        Worker.shopkeeper_id == shop_id,
    ).first()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found.")

    salary = float(worker.salary or 0)
    if salary <= 0:
        raise HTTPException(status_code=400, detail="Worker has no salary configured.")

    # Log as expense
    expense = ShopExpense(
        shop_id=shop_id,
        category="salary",
        amount=salary,
        description=f"Salary payment for {worker.name} - {month}",
        expense_date=date.today(),
        payment_method="bank_transfer",
    )
    db.add(expense)

    # Universal journal
    tx = UniversalTransaction(
        shop_id=shop_id,
        tx_type="EXPENSE",
        category="SALARY",
        amount=salary,
        reference_id=f"SALARY-W{worker_id}-{month}",
        description=f"Salary: {worker.name} ({month})",
    )
    db.add(tx)
    db.commit()

    return {
        "message": f"Salary of ₹{salary:.2f} paid to {worker.name} for {month}.",
        "amount": salary,
        "worker_name": worker.name,
    }


# =====================================
# BANK RECONCILIATION
# =====================================
class ReconCreate(BaseModel):
    recon_date: date
    expected_upi_amount: float = Field(0, ge=0)
    actual_bank_deposit: float = Field(0, ge=0)
    notes: Optional[str] = None

@router.post("/bank-recon", tags=["Bank Reconciliation"])
def add_reconciliation(
    data: ReconCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(owner_only),
):
    """Record daily UPI vs bank deposit reconciliation"""
    shop_id = current_user["user_id"]

    diff = abs(data.expected_upi_amount - data.actual_bank_deposit)
    status = "MATCHED" if diff < 1.0 else "DISCREPANCY"

    recon = BankReconciliation(
        shop_id=shop_id,
        recon_date=data.recon_date,
        expected_upi_amount=data.expected_upi_amount,
        actual_bank_deposit=data.actual_bank_deposit,
        status=status,
        notes=data.notes,
    )
    db.add(recon)
    db.commit()

    return {
        "message": "Reconciliation recorded.",
        "status": status,
        "difference": diff,
        "date": data.recon_date,
        "alert": f"⚠️ Discrepancy of ₹{diff:.2f} detected!" if status == "DISCREPANCY" else "✅ Accounts balanced!",
    }


@router.get("/bank-recon", tags=["Bank Reconciliation"])
def list_reconciliations(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(owner_only),
):
    """View bank reconciliation history"""
    shop_id = current_user["user_id"]
    q = db.query(BankReconciliation).filter(BankReconciliation.shop_id == shop_id)
    if start_date:
        q = q.filter(BankReconciliation.recon_date >= start_date)
    if end_date:
        q = q.filter(BankReconciliation.recon_date <= end_date)
    records = q.order_by(BankReconciliation.recon_date.desc()).all()

    return {
        "records": [
            {
                "id": r.id,
                "date": r.recon_date,
                "expected_upi": float(r.expected_upi_amount),
                "actual_bank": float(r.actual_bank_deposit),
                "status": r.status,
                "difference": abs(float(r.expected_upi_amount) - float(r.actual_bank_deposit)),
                "notes": r.notes,
            }
            for r in records
        ]
    }


# =====================================
# ENTERPRISE TRACKER (Unified P&L)
# =====================================
@router.get("/enterprise/pnl", tags=["Enterprise Intelligence"])
def get_profit_and_loss(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(owner_only),
):
    """
    Full Profit & Loss summary:
    Revenue (sales) - Expenses (all categories) = Net Profit
    """
    shop_id = current_user["user_id"]
    if not start_date:
        start_date = date.today().replace(day=1)  # Current month
    if not end_date:
        end_date = date.today()

    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt = datetime.combine(end_date, datetime.max.time())

    # Total income from universal journal
    income = db.query(func.sum(UniversalTransaction.amount)).filter(
        UniversalTransaction.shop_id == shop_id,
        UniversalTransaction.tx_type == "INCOME",
        UniversalTransaction.tx_date >= start_dt,
        UniversalTransaction.tx_date <= end_dt,
    ).scalar() or 0

    # Total expenses
    expenses = db.query(func.sum(UniversalTransaction.amount)).filter(
        UniversalTransaction.shop_id == shop_id,
        UniversalTransaction.tx_type == "EXPENSE",
        UniversalTransaction.tx_date >= start_dt,
        UniversalTransaction.tx_date <= end_dt,
    ).scalar() or 0

    # Breakdown by category
    breakdown = db.query(
        UniversalTransaction.category,
        UniversalTransaction.tx_type,
        func.sum(UniversalTransaction.amount).label("total"),
        func.count(UniversalTransaction.id).label("count"),
    ).filter(
        UniversalTransaction.shop_id == shop_id,
        UniversalTransaction.tx_date >= start_dt,
        UniversalTransaction.tx_date <= end_dt,
    ).group_by(UniversalTransaction.category, UniversalTransaction.tx_type).all()

    net_profit = float(income) - float(expenses)

    return {
        "period": {"start": str(start_date), "end": str(end_date)},
        "total_income": float(income),
        "total_expenses": float(expenses),
        "net_profit": net_profit,
        "profit_margin_pct": round((net_profit / float(income) * 100) if income else 0, 2),
        "status": "PROFIT" if net_profit >= 0 else "LOSS",
        "breakdown": [
            {
                "category": b.category,
                "type": b.tx_type,
                "total": float(b.total),
                "transactions": b.count,
            }
            for b in breakdown
        ],
    }


@router.get("/enterprise/transactions", tags=["Enterprise Intelligence"])
def get_all_transactions(
    tx_type: Optional[str] = None,
    category: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    skip: int = 0,
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    current_user: dict = Depends(owner_only),
):
    """All Transactions view: every money movement (sales, expenses, khata, PO)"""
    shop_id = current_user["user_id"]
    q = db.query(UniversalTransaction).filter(UniversalTransaction.shop_id == shop_id)
    if tx_type:
        q = q.filter(UniversalTransaction.tx_type == tx_type.upper())
    if category:
        q = q.filter(UniversalTransaction.category.ilike(f"%{category}%"))
    if start_date:
        q = q.filter(UniversalTransaction.tx_date >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        q = q.filter(UniversalTransaction.tx_date <= datetime.combine(end_date, datetime.max.time()))

    txs = q.order_by(UniversalTransaction.tx_date.desc()).offset(skip).limit(limit).all()
    return {
        "transactions": [
            {
                "id": t.id,
                "type": t.tx_type,
                "category": t.category,
                "amount": float(t.amount),
                "reference_id": t.reference_id,
                "description": t.description,
                "date": t.tx_date,
            }
            for t in txs
        ]
    }


# =====================================
# RETAIL INTELLIGENCE
# =====================================
@router.get("/retail/stock-analysis", tags=["Retail Intelligence"])
def stock_analysis(
    db: Session = Depends(get_db),
    current_user: dict = Depends(owner_only),
):
    """Identify fast-moving and dead-stock items"""
    shop_id = current_user["user_id"]

    products = db.query(Product).filter(
        Product.user_id == shop_id,
        Product.is_active == True,
    ).all()

    fast_movers = []
    dead_stock = []
    low_stock = []

    for p in products:
        if p.current_stock <= 0:
            dead_stock.append({"id": p.id, "name": p.product_name, "stock": 0, "category": p.category})
        elif p.current_stock <= (p.min_stock or 10):
            low_stock.append({
                "id": p.id,
                "name": p.product_name,
                "stock": p.current_stock,
                "min_stock": p.min_stock,
                "category": p.category,
            })

    # Top selling products (from sales table)
    top_sales = (
        db.query(sales.product_name, func.sum(sales.quantity).label("total_qty"))
        .filter(sales.shopkeeper_id == shop_id)
        .group_by(sales.product_name)
        .order_by(func.sum(sales.quantity).desc())
        .limit(10)
        .all()
    )

    return {
        "fast_moving_products": [{"name": r.product_name, "total_sold": int(r.total_qty)} for r in top_sales],
        "low_stock_alerts": low_stock,
        "out_of_stock": dead_stock,
        "summary": {
            "total_products": len(products),
            "low_stock_count": len(low_stock),
            "out_of_stock_count": len(dead_stock),
        },
    }
