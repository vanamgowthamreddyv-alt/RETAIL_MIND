"""
UPI Ledger Service (Feature 8)
Track all UPI collections separately for dashboard reconciliation
"""

from sqlalchemy.orm import Session
from models import UpiLedger, UpiLedger
from sqlalchemy import func
from decimal import Decimal
from datetime import date


class UpiLedgerService:
    
    @staticmethod
    def record_upi_payment(db: Session, shop_id: int, invoice_id: int, 
                          upi_id: str, amount: Decimal, 
                          customer_upi: str = None, upi_reference: str = None) -> dict:
        """Record a UPI payment in ledger"""
        ledger_entry = UpiLedger(
            shop_id=shop_id,
            invoice_id=invoice_id,
            upi_id=upi_id,
            amount=amount,
            customer_upi=customer_upi,
            upi_reference=upi_reference,
            status="PENDING"
        )
        db.add(ledger_entry)
        db.commit()
        
        return {
            "ledger_id": ledger_entry.id,
            "status": "recorded",
            "amount": amount
        }
    
    @staticmethod
    def confirm_upi_payment(db: Session, upi_reference: str) -> bool:
        """Mark UPI payment as confirmed"""
        entry = db.query(UpiLedger).filter_by(upi_reference=upi_reference).first()
        if entry:
            entry.status = "CONFIRM"
            db.commit()
            return True
        return False
    
    @staticmethod
    def get_today_upi_summary(db: Session, shop_id: int) -> dict:
        """Get today's UPI collections vs total billed"""
        today = date.today()
        
        upi_query = db.query(func.sum(UpiLedger.amount)).filter(
            UpiLedger.shop_id == shop_id,
            func.date(UpiLedger.payment_date) == today,
            UpiLedger.status.in_(["PENDING", "CONFIRM"])
        )
        upi_total = upi_query.scalar() or Decimal("0")
        
        # Count pending (unmatched) payments
        pending_count = db.query(func.count(UpiLedger.id)).filter(
            UpiLedger.shop_id == shop_id,
            func.date(UpiLedger.payment_date) == today,
            UpiLedger.status == "PENDING"
        ).scalar() or 0
        
        confirmed_count = db.query(func.count(UpiLedger.id)).filter(
            UpiLedger.shop_id == shop_id,
            func.date(UpiLedger.payment_date) == today,
            UpiLedger.status == "CONFIRM"
        ).scalar() or 0
        
        return {
            "today_upi_total": float(upi_total),
            "pending_transactions": pending_count,
            "confirmed_transactions": confirmed_count,
            "unmatched_count": pending_count
        }
    
    @staticmethod
    def get_upi_by_id(db: Session, shop_id: int) -> dict:
        """Breakdown today's UPI by each UPI ID"""
        today = date.today()
        
        results = db.query(
            UpiLedger.upi_id,
            func.sum(UpiLedger.amount).label("total"),
            func.count(UpiLedger.id).label("count")
        ).filter(
            UpiLedger.shop_id == shop_id,
            func.date(UpiLedger.payment_date) == today
        ).group_by(UpiLedger.upi_id).all()
        
        breakdown = []
        for upi_id, total, count in results:
            breakdown.append({
                "upi_id": upi_id,
                "amount": float(total),
                "transaction_count": count
            })
        
        return {"upi_breakdown": breakdown}
    
    @staticmethod
    def get_unmatched_payments(db: Session, shop_id: int, limit: int = 10) -> list:
        """Get pending (unmatched) UPI payments"""
        entries = db.query(UpiLedger).filter(
            UpiLedger.shop_id == shop_id,
            UpiLedger.status == "PENDING"
        ).order_by(UpiLedger.payment_date.desc()).limit(limit).all()
        
        return [{
            "id": e.id,
            "upi_id": e.upi_id,
            "customer_upi": e.customer_upi,
            "amount": float(e.amount),
            "payment_date": e.payment_date.isoformat(),
            "upi_reference": e.upi_reference,
            "invoice_id": e.invoice_id
        } for e in entries]
    
    @staticmethod
    def get_monthly_upi_report(db: Session, shop_id: int, year: int, month: int) -> dict:
        """Get UPI collections for a month"""
        from datetime import datetime
        start_date = date(year, month, 1)
        if month == 12:
            end_date = date(year + 1, 1, 1)
        else:
            end_date = date(year, month + 1, 1)
        
        total = db.query(func.sum(UpiLedger.amount)).filter(
            UpiLedger.shop_id == shop_id,
            UpiLedger.payment_date >= start_date,
            UpiLedger.payment_date < end_date
        ).scalar() or Decimal("0")
        
        count = db.query(func.count(UpiLedger.id)).filter(
            UpiLedger.shop_id == shop_id,
            UpiLedger.payment_date >= start_date,
            UpiLedger.payment_date < end_date
        ).scalar() or 0
        
        return {
            "period": f"{month}/{year}",
            "total_upi": float(total),
            "transaction_count": count,
            "avg_transaction": float(total / count) if count > 0 else 0
        }
