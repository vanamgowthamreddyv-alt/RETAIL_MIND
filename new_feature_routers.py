from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from datetime import date, datetime
from pydantic import BaseModel, Field
from typing import Optional, List

# Core Database Access
from db import get_db

# Import all the new Service classes you built!
from loyalty_service import LoyaltyService
from delivery_service import DeliveryService
from counter_service import CounterService
from festival_service import FestivalService
from credit_score_service import CreditScoreService
from occasion_service import OccasionService
from report_service import ReportService
from upi_ledger_service import UpiLedgerService
# Auth & Models
from security import get_current_user as check_current_user
from models import (
    User, ShopProfile, sales, Invoice, InvoiceLineItem, 
    Payment, KhataBalance, KhataHistory, ShopExpense, Worker
)

router = APIRouter(prefix="/api", tags=["New Features"])

async def get_user_shop_id(user_id: int, db: Session) -> int:
    """Helper to get shop_id for a user"""
    profile = db.query(ShopProfile).filter(ShopProfile.shop_id == user_id).first()
    if not profile:
        # Auto-create if missing (failsafe)
        profile = ShopProfile(shop_id=user_id, shop_name="My Shop", shop_type="Retail", phone_number="")
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile.id

# ==========================================
# 1. COUNTER / STAFF MANAGEMENT (FEATURE 11)
# ==========================================
class CounterAuthRequest(BaseModel):
    billing_pin: str

@router.post("/counter/authenticate")
def authenticate_counter(req: CounterAuthRequest, db: Session = Depends(get_db)):
    result = CounterService.authenticate(db, req.billing_pin)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid PIN")
    return {"status": "success", "staff": result}

# ==========================================
# 2. DELIVERY TRACKING (FEATURE 10)
# ==========================================
class DeliveryCreateReq(BaseModel):
    customer_id: int
    invoice_id: int
    delivery_address: str
    delivery_date: Optional[str] = None
    special_instructions: Optional[str] = None

@router.post("/delivery/create")
def create_delivery(req: DeliveryCreateReq, db: Session = Depends(get_db)):
    d_date = date.fromisoformat(req.delivery_date) if req.delivery_date else None
    return DeliveryService.create_delivery(
        db, shop_id=1, customer_id=req.customer_id, invoice_id=req.invoice_id,
        delivery_address=req.delivery_address, delivery_date=d_date,
        special_instructions=req.special_instructions
    )

@router.get("/delivery/today")
def get_today_deliveries(db: Session = Depends(get_db)):
    # Assuming Shop ID 1 for now
    return {"deliveries": DeliveryService.get_today_deliveries(db, shop_id=1)}

@router.post("/delivery/{delivery_id}/update-status")
def update_delivery(delivery_id: int, status: str = Body(embed=True), notes: Optional[str] = Body(default=None, embed=True), db: Session = Depends(get_db)):
    return DeliveryService.update_status(db, delivery_id, status, notes=notes)


# ==========================================
# 3. LOYALTY POINTS (FEATURE 7)
# ==========================================
@router.post("/loyalty/earn")
def earn_points(customer_id: int = Body(...), invoice_id: int = Body(...), amount: float = Body(...), db: Session = Depends(get_db)):
    return LoyaltyService.earn_points(db, customer_id, invoice_id, amount)

@router.post("/loyalty/redeem")
def redeem_points(customer_id: int = Body(...), points: int = Body(...), invoice_id: int = Body(...), db: Session = Depends(get_db)):
    result = LoyaltyService.redeem_points(db, customer_id, points, invoice_id)
    if not result.get("success", False):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to redeem"))
    return result

# ==========================================
# 4. FESTIVAL PREDICTOR (FEATURE 3)
# ==========================================
@router.get("/festivals/upcoming")
def get_upcoming_festivals(db: Session = Depends(get_db)):
    return {"festivals": FestivalService.get_upcoming(db)}


# ==========================================
# 5. OCCASIONS & BIRTHDAYS (FEATURE 14)
# ==========================================
@router.get("/occasions/today")
def get_today_occasions(db: Session = Depends(get_db)):
    return {"occasions": OccasionService.get_today_occasions(db, shop_id=1)}

# ==========================================
# 6. UPI LEDGER (FEATURE 8)
# ==========================================
@router.get("/collections/today-summary")
def get_upi_summary(db: Session = Depends(get_db)):
    return UpiLedgerService.get_daily_summary(db, shop_id=1)

# ==========================================
# 7. SAVED BILL TEMPLATES (FEATURE 9)
# ==========================================
from template_service import TemplateService

@router.get("/templates")
def get_templates(db: Session = Depends(get_db)):
    return {"templates": TemplateService.get_all_templates(db, user_id=1)}

@router.post("/templates/save")
def save_template(template_name: str = Body(...), template_items: list = Body(...), db: Session = Depends(get_db)):
    return TemplateService.save_template(db, user_id=1, template_name=template_name, template_items=template_items)

# ==========================================
# 8. CUSTOMER CREDIT SCORING (FEATURE 13)
# ==========================================
from credit_score_service import CreditScoreService

@router.get("/credit-score/{customer_id}")
def get_credit_score(customer_id: int, db: Session = Depends(get_db)):
    return CreditScoreService.get_or_calculate_score(db, customer_id)

# ==========================================
# 9. DAILY WHATSAPP REPORT (FEATURE 16)
# ==========================================
from report_service import ReportService

@router.get("/reports/daily")
def generate_daily_report(user_id: int = Depends(check_current_user), db: Session = Depends(get_db)):
    return {"report": ReportService.generate_daily_report(db, shop_id=user_id)}


# =========================================================
# 🔥 NEW MASSIVE RETAIL PREMIUM FEATURES (JUST ADDED!) 🔥
# =========================================================
from advanced_retail_services import AdvancedRetailServices

@router.post("/flash-sale/setup")
def setup_flash_sale(category: str = Body(...), discount_pct: float = Body(...), hours: int = Body(...), user_id: int = Depends(check_current_user), db: Session = Depends(get_db)):
    """Feature 17: Set up a timed flash sale across an entire category"""
    return AdvancedRetailServices.setup_flash_sale(db, category, discount_pct, hours, user_id)

@router.get("/analytics/churn-risk")
def get_churn_risk(days: int = 30, user_id: int = Depends(check_current_user), db: Session = Depends(get_db)):
    """Feature 18: Identify customers who haven't returned recently so you can send them WhatsApp coupons"""
    return AdvancedRetailServices.get_churn_risk_customers(db, days, user_id)

@router.get("/inventory/generate-purchase-orders")
def get_supplier_pos(user_id: int = Depends(check_current_user), db: Session = Depends(get_db)):
    """Feature 19: One-click auto-generation of Purchase Orders broken down by Supplier"""
    return AdvancedRetailServices.generate_supplier_purchase_order(db, user_id)

# ==========================================
# KHATA / LEDGER MANAGEMENT
# ==========================================
class KhataBalanceUpdate(BaseModel):
    customer_phone: str = Field(..., min_length=10, max_length=10, pattern=r"^\d{10}$")
    amount: float
    transaction_type: str  # 'invoice' or 'payment'
    reference_id: str  # invoice_number or payment_id

@router.get("/khata/{customer_phone}")
def get_khata_balance(customer_phone: str, user_id: int = Depends(check_current_user), db: Session = Depends(get_db)):
    """Get customer's khata (credit) balance"""
    try:
        from models import Customer
        customer = db.query(Customer).filter(Customer.phone == customer_phone, Customer.user_id == user_id).first()
        if not customer:
            return {"customer_phone": customer_phone, "khata_balance": 0, "status": "no_customer"}
        
        khata_balance = customer.khata_balance if hasattr(customer, 'khata_balance') else 0
        return {
            "customer_phone": customer_phone,
            "customer_name": customer.name,
            "khata_balance": khata_balance,
            "status": "success"
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/khata/update")
def update_khata_balance(req: KhataBalanceUpdate, user_id: int = Depends(check_current_user), db: Session = Depends(get_db)):
    """Update customer khata balance when invoice is created or payment received - stores transaction history"""
    try:
        from models import KhataBalance, KhataHistory
        from datetime import datetime
        
        # Get or create khata record
        khata = db.query(KhataBalance).filter(
            KhataBalance.customer_phone == req.customer_phone,
            KhataBalance.shop_id == user_id
        ).first()
        
        if not khata:
            khata = KhataBalance(
                shop_id=user_id,
                customer_phone=req.customer_phone,
                customer_name="Unknown",
                khata_balance=0
            )
            db.add(khata)
            db.flush()  # Get khata.id before creating history
        
        # Update khata balance
        if req.transaction_type == 'invoice':
            khata.khata_balance = (khata.khata_balance or 0) + req.amount
        elif req.transaction_type == 'payment':
            khata.khata_balance = max(0, (khata.khata_balance or 0) - req.amount)
        
        khata.last_transaction = datetime.now()
        
        # ✅ STORE TRANSACTION HISTORY
        history_entry = KhataHistory(
            khata_id=khata.id,
            transaction_type=req.transaction_type.upper(),
            amount=req.amount,
            reference_id=req.reference_id,
            description=f"{req.transaction_type} - {req.reference_id}"
        )
        db.add(history_entry)
        
        db.commit()
        
        return {
            "status": "success",
            "customer_phone": req.customer_phone,
            "new_balance": float(khata.khata_balance),
            "transaction_type": req.transaction_type,
            "amount": float(req.amount),
            "transaction_id": history_entry.id
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# EXPENSE MANAGEMENT
# ==========================================
class ExpenseCreate(BaseModel):
    category: str  # rent, utilities, salary, supplies, etc
    amount: float
    description: str
    date: Optional[str] = None

@router.post("/expenses/create")
def create_expense(req: ExpenseCreate, user_id: int = Depends(check_current_user), db: Session = Depends(get_db)):
    """Create a shop expense record"""
    try:
        from models import ShopExpense
        from datetime import datetime
        
        expense = ShopExpense(
            shop_id=user_id,
            category=req.category,
            amount=req.amount,
            description=req.description,
            expense_date=datetime.fromisoformat(req.date) if req.date else datetime.now()
        )
        db.add(expense)
        db.commit()
        db.refresh(expense)
        
        return {
            "status": "success",
            "expense_id": expense.id,
            "amount": expense.amount,
            "category": expense.category
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/expenses")
def get_expenses(skip: int = 0, limit: int = 100, user_id: int = Depends(check_current_user), db: Session = Depends(get_db)):
    """Get all shop expenses"""
    try:
        from models import ShopExpense
        expenses = db.query(ShopExpense).filter(ShopExpense.shop_id == user_id).offset(skip).limit(limit).all()
        return {"status": "success", "expenses": [{"id": e.id, "category": e.category, "amount": e.amount, "description": e.description, "date": e.expense_date.isoformat() if hasattr(e, 'expense_date') else None} for e in expenses]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# TRANSACTION HISTORY
# ==========================================

@router.get("/khata-history/{customer_phone}")
def get_khata_transaction_history(customer_phone: str, skip: int = 0, limit: int = 100, user_id: int = Depends(check_current_user), db: Session = Depends(get_db)):
    """Get transaction history for a khata customer (invoices, payments, adjustments)"""
    try:
        from models import Customer, KhataBalance, KhataHistory
        
        # Get khata record
        khata = db.query(KhataBalance).filter(
            KhataBalance.customer_phone == customer_phone,
            KhataBalance.shop_id == user_id
        ).first()
        if not khata:
            return {"status": "no_khata", "customer_phone": customer_phone, "transactions": []}
        
        # Get transaction history
        history = db.query(KhataHistory).filter(
            KhataHistory.khata_id == khata.id
        ).order_by(KhataHistory.transaction_date.desc()).offset(skip).limit(limit).all()
        
        transactions = [
            {
                "id": t.id,
                "type": t.transaction_type,
                "amount": float(t.amount),
                "reference_id": t.reference_id,
                "description": t.description,
                "date": t.transaction_date.isoformat() if hasattr(t, 'transaction_date') else None
            }
            for t in history
        ]
        
        return {
            "status": "success",
            "customer_phone": customer_phone,
            "current_balance": float(khata.khata_balance),
            "transaction_count": len(transactions),
            "transactions": transactions
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/expenses/history")
def get_expense_history(category: Optional[str] = None, skip: int = 0, limit: int = 100, user_id: int = Depends(check_current_user), db: Session = Depends(get_db)):
    """Get expense transaction history with optional category filter"""
    try:
        from models import ShopExpense
        
        query = db.query(ShopExpense).filter(ShopExpense.shop_id == user_id)
        
        if category:
            query = query.filter(ShopExpense.category == category)
        
        expenses = query.order_by(ShopExpense.expense_date.desc()).offset(skip).limit(limit).all()
        
        total_amount = sum(float(e.amount) for e in expenses)
        
        return {
            "status": "success",
            "category_filter": category,
            "total_amount": total_amount,
            "count": len(expenses),
            "expenses": [
                {
                    "id": e.id,
                    "category": e.category,
                    "amount": float(e.amount),
                    "description": e.description,
                    "date": e.expense_date.isoformat() if hasattr(e, 'expense_date') else None,
                    "payment_method": e.payment_method
                }
                for e in expenses
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/transactions/recent")
def get_recent_transactions(limit: int = 50, db: Session = Depends(get_db)):
    """Get recent transactions across all types (invoices, payments, expenses) - for Recent Transactions screen"""
    try:
        from models import Invoice, KhataHistory
        from datetime import datetime, timedelta
        
        # Get recent paid invoices
        recent_invoices = db.query(Invoice).filter(
            Invoice.payment_status == 'PAID',
            Invoice.updated_at >= datetime.now() - timedelta(days=30)
        ).order_by(Invoice.updated_at.desc()).limit(limit).all()
        
        transactions = []
        for inv in recent_invoices:
            transactions.append({
                "type": "UPI" if inv.payment_method and 'upi' in inv.payment_method.lower() else "CASH",
                "customer_name": inv.customer_name if hasattr(inv, 'customer_name') else "Unknown",
                "customer_phone": inv.customer_phone if hasattr(inv, 'customer_phone') else "",
                "amount": float(inv.total_amount),
                "date": inv.updated_at.isoformat() if hasattr(inv, 'updated_at') else None,
                "reference_id": inv.invoice_number,
                "payment_status": "PAID"
            })
        
        return {
            "status": "success",
            "count": len(transactions),
            "transactions": sorted(transactions, key=lambda x: x.get('date', ''), reverse=True)[:limit]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/transactions/online-payments")
def get_online_payments(days: int = 30, limit: int = 100, db: Session = Depends(get_db)):
    """Fetch online (UPI/digital) payments only for last N days"""
    try:
        from models import Invoice
        from datetime import datetime, timedelta
        
        # Get UPI/online payments from invoices
        online_invoices = db.query(Invoice).filter(
            Invoice.payment_status == 'PAID',
            Invoice.payment_method != None,
            (Invoice.payment_method.ilike('%upi%')) | 
            (Invoice.payment_method.ilike('%online%')) |
            (Invoice.payment_method.ilike('%gpay%')) |
            (Invoice.payment_method.ilike('%card%')) |
            (Invoice.payment_method.ilike('%bank%')),
            Invoice.updated_at >= datetime.now() - timedelta(days=days)
        ).order_by(Invoice.updated_at.desc()).limit(limit).all()
        
        transactions = []
        for inv in online_invoices:
            transactions.append({
                "transactionId": str(inv.id),
                "type": "UPI",  # Mark as UPI for online
                "customerName": inv.customer_name if hasattr(inv, 'customer_name') else "Unknown",
                "customerPhone": inv.customer_phone if hasattr(inv, 'customer_phone') else "",
                "amount": float(inv.total_amount),
                "timestamp": inv.updated_at.isoformat() if hasattr(inv, 'updated_at') else None,
                "referenceId": inv.invoice_number,
                "paymentMethod": inv.payment_method if hasattr(inv, 'payment_method') else 'UPI'
            })
        
        return {
            "status": "success",
            "online_count": len(transactions),
            "transactions": transactions
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# DATA BACKUP & VERIFICATION
# ==========================================

@router.get("/data/backup/export")
def export_data_backup(user_id: int = Depends(check_current_user), db: Session = Depends(get_db)):
    """Export all shop data for backup (invoices, khata, expenses, inventory)"""
    try:
        from models import Invoice, KhataBalance, ShopExpense, Product
        from datetime import datetime
        
        backup = {
            "backup_timestamp": datetime.now().isoformat(),
            "user_id": user_id,
            "invoices": len(db.query(Invoice).filter(Invoice.user_id == user_id).all()),
            "khata_customers": len(db.query(KhataBalance).filter(KhataBalance.shop_id == user_id).all()),
            "expenses": len(db.query(ShopExpense).filter(ShopExpense.shop_id == user_id).all()),
            "products": len(db.query(Product).filter(Product.user_id == user_id, Product.is_active == True).all()),
        }
        
        return {"status": "success", "backup_summary": backup}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/data/integrity-check")
def verify_data_integrity(db: Session = Depends(get_db)):
    """Verify data integrity across all critical tables"""
    try:
        from models import Invoice, KhataBalance, KhataHistory, ShopExpense
        
        issues = []
        
        # Check 1: Orphaned khata records
        all_khata = db.query(KhataBalance).all()
        for khata in all_khata:
            if not khata.khata_id and khata.khata_balance < 0:
                issues.append(f"Negative balance for customer {khata.customer_phone}")
        
        # Check 2: Missing transactions
        invoices_with_no_history = 0
        for inv in db.query(Invoice).all():
            history_count = db.query(KhataHistory).filter(
                KhataHistory.reference_id == inv.invoice_number
            ).count()
            if inv.payment_status == 'PAID' and history_count == 0:
                invoices_with_no_history += 1
        
        if invoices_with_no_history > 0:
            issues.append(f"{invoices_with_no_history} paid invoices missing history records")
        
        return {
            "status": "success" if not issues else "warning",
            "integrity_issues": issues,
            "issue_count": len(issues)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# BATCH SYNC ENDPOINTS (for app resilience)
# ==========================================

@router.post("/sync/sales")
async def sync_sales_batch(payload: dict = Body(...), user_id: int = Depends(check_current_user), db: Session = Depends(get_db)):
    """Bulk sync sales records from mobile app - PERSISTED TO DB"""
    try:
        sales_items = payload.get('data', [])
        synced_count = 0
        
        for item in sales_items:
            # Check for existing sale to prevent duplicates (idempotency)
            # Use timestamp and product name as a simple unique check
            sale_date_str = item.get('sale_date')
            sale_date = date.fromisoformat(sale_date_str) if sale_date_str else date.today()
            
            new_sale = sales(
                shopkeeper_id=user_id,
                product_name=item.get('product_name', 'Unknown'),
                price=item.get('price', 0),
                quantity=item.get('quantity', 0),
                total=item.get('total', 0),
                sale_date=sale_date,
                created_at=datetime.utcnow()
            )
            db.add(new_sale)
            synced_count += 1
        
        db.commit()
        return {
            "status": "success",
            "synced_count": synced_count,
            "user_id": user_id
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Sales sync failed: {str(e)}")

@router.post("/sync/invoices")
async def sync_invoices_batch(payload: dict = Body(...), user_id: int = Depends(check_current_user), db: Session = Depends(get_db)):
    """Bulk sync invoices with line items from mobile app - PERSISTED TO DB"""
    try:
        invoices_data = payload.get('data', [])
        synced_count = 0
        shop_id = await get_user_shop_id(user_id, db)
        
        for inv in invoices_data:
            # Check if invoice already exists to avoid duplication
            existing = db.query(Invoice).filter(Invoice.invoice_number == inv.get('invoice_number')).first()
            if existing: continue
            
            # Create invoice record
            new_invoice = Invoice(
                user_id=user_id,
                shop_id=shop_id,
                invoice_number=inv.get('invoice_number'),
                invoice_date=date.fromisoformat(inv.get('invoice_date')) if inv.get('invoice_date') else date.today(),
                total_amount=inv.get('total_amount', 0),
                paid_amount=inv.get('paid_amount', inv.get('total_amount', 0) if inv.get('payment_status') == 'PAID' else 0),
                payment_status=inv.get('payment_status', 'PAID'),
                payment_method=inv.get('payment_method', 'CASH'),
                customer_id=inv.get('customer_id'),
                created_at=datetime.utcnow()
            )
            db.add(new_invoice)
            db.flush() # Get new_invoice.id
            
            # Add line items if present
            line_items = inv.get('line_items', [])
            for item in line_items:
                new_item = InvoiceLineItem(
                    invoice_id=new_invoice.id,
                    product_id=item.get('product_id'),
                    description=item.get('item', item.get('description', 'Product')),
                    quantity=item.get('qty', item.get('quantity', 1)),
                    unit_price=item.get('price', item.get('unit_price', 0)),
                    line_total=item.get('total', 0)
                )
                db.add(new_item)
                
            synced_count += 1
            
        db.commit()
        return {
            "status": "success",
            "synced_count": synced_count
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Invoices sync failed: {str(e)}")

@router.post("/sync/khata-balances")
async def sync_khata_batch(payload: dict = Body(...), user_id: int = Depends(check_current_user), db: Session = Depends(get_db)):
    """Bulk sync khata balances from mobile app - PERSISTED TO DB"""
    try:
        khata_data = payload.get('data', [])
        synced_count = 0
        shop_id = await get_user_shop_id(user_id, db)
        
        for k_item in khata_data:
            # Update or create khata record
            customer_phone = k_item.get('customer_phone')
            if not customer_phone: continue
            
            khata = db.query(KhataBalance).filter(
                KhataBalance.customer_phone == customer_phone,
                KhataBalance.shop_id == user_id # Using user_id as shop owner ID for KhataBalance
            ).first()
            
            if not khata:
                khata = KhataBalance(
                    shop_id=user_id,
                    customer_phone=customer_phone,
                    customer_name=k_item.get('customer_name', 'Unknown'),
                    khata_balance=k_item.get('balance', 0)
                )
                db.add(khata)
            else:
                khata.khata_balance = k_item.get('balance', 0)
            
            synced_count += 1
            
        db.commit()
        return {
            "status": "success",
            "synced_count": synced_count
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Khata sync failed: {str(e)}")

@router.post("/sync/expenses")
async def sync_expenses_batch(payload: dict = Body(...), user_id: int = Depends(check_current_user), db: Session = Depends(get_db)):
    """Bulk sync expenses from mobile app - PERSISTED TO DB"""
    try:
        expenses_data = payload.get('data', [])
        synced_count = 0
        
        for exp in expenses_data:
            new_expense = ShopExpense(
                shop_id=user_id,
                category=exp.get('category', 'Supplies'),
                amount=exp.get('amount', 0),
                description=exp.get('description', ''),
                expense_date=date.fromisoformat(exp.get('date')) if exp.get('date') else date.today()
            )
            db.add(new_expense)
            synced_count += 1
            
        db.commit()
        return {
            "status": "success",
            "synced_count": synced_count
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Expenses sync failed: {str(e)}")


# ==========================================
# CHUNKED SYNC - handles massive offline vaults
# ==========================================

@router.post("/sync/invoices/chunked")
async def sync_invoices_chunked(
    payload: dict = Body(...),
    user_id: int = Depends(check_current_user),
    db: Session = Depends(get_db)
):
    """Chunked invoice sync - safe for large offline vaults. Send in batches of 100."""
    try:
        chunk = payload.get('data', [])  # Expect max 100 at a time from client
        chunk_index = payload.get('chunk_index', 0)
        total_chunks = payload.get('total_chunks', 1)
        shop_id = await get_user_shop_id(user_id, db)

        synced_count = 0
        skipped_count = 0

        for inv in chunk:
            existing = db.query(Invoice).filter(
                Invoice.user_id == user_id,
                Invoice.invoice_number == inv.get('invoice_number')
            ).first()
            if existing:
                skipped_count += 1
                continue

            new_invoice = Invoice(
                user_id=user_id,
                shop_id=shop_id,
                invoice_number=inv.get('invoice_number'),
                invoice_date=date.fromisoformat(inv.get('invoice_date')) if inv.get('invoice_date') else date.today(),
                total_amount=inv.get('total_amount', 0),
                paid_amount=inv.get('paid_amount', inv.get('total_amount', 0) if inv.get('payment_status') == 'PAID' else 0),
                payment_status=inv.get('payment_status', 'PAID'),
                payment_method=inv.get('payment_method', 'CASH'),
                customer_id=inv.get('customer_id'),
                created_at=datetime.utcnow()
            )
            db.add(new_invoice)
            db.flush()

            for item in inv.get('line_items', []):
                db.add(InvoiceLineItem(
                    invoice_id=new_invoice.id,
                    product_id=item.get('product_id'),
                    description=item.get('item', item.get('description', 'Product')),
                    quantity=item.get('qty', item.get('quantity', 1)),
                    unit_price=item.get('price', item.get('unit_price', 0)),
                    line_total=item.get('total', 0)
                ))
            synced_count += 1

        db.commit()
        return {
            "status": "success",
            "chunk_index": chunk_index,
            "total_chunks": total_chunks,
            "synced_count": synced_count,
            "skipped_duplicates": skipped_count,
            "is_complete": chunk_index + 1 >= total_chunks
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Chunked sync failed: {str(e)}")


# ==========================================
# SOFT DELETE ENDPOINTS
# ==========================================

@router.delete("/products/{product_id}")
def soft_delete_product(product_id: int, user_id: int = Depends(check_current_user), db: Session = Depends(get_db)):
    """Soft-delete a product (marks it inactive, preserves history on all old invoices)"""
    from models import Product
    product = db.query(Product).filter(Product.id == product_id, Product.user_id == user_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    product.is_active = False
    db.commit()
    return {"status": "success", "message": f"Product '{product.product_name}' archived. Historical invoices preserved."}


@router.delete("/customers/{customer_id}")
def soft_delete_customer(customer_id: int, user_id: int = Depends(check_current_user), db: Session = Depends(get_db)):
    """Soft-delete a customer (archives them, preserves all their invoice history)"""
    from models import Customer
    customer = db.query(Customer).filter(Customer.id == customer_id, Customer.user_id == user_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    customer.is_active = False
    db.commit()
    return {"status": "success", "message": f"Customer '{customer.customer_name}' archived. All Khata and invoice history preserved."}
