"""
Billing Counter Service (Feature 11)
Multi-staff billing with counter tracking and PIN authentication
"""

from sqlalchemy.orm import Session
from models import BillingCounter, SalesByCounter
from sqlalchemy import func
from datetime import date


class CounterService:
    
    @staticmethod
    def create_billing_counter(db: Session, user_id: int, staff_name: str, 
                              counter_number: int, billing_pin: str) -> dict:
        """Create new billing counter for staff"""
        # Check if PIN already exists
        existing_pin = db.query(BillingCounter).filter_by(billing_pin=billing_pin).first()
        if existing_pin:
            return {"error": "PIN already in use"}
        
        counter = BillingCounter(
            user_id=user_id,
            staff_name=staff_name,
            counter_number=counter_number,
            billing_pin=billing_pin
        )
        db.add(counter)
        db.commit()
        
        return {
            "counter_id": counter.id,
            "staff_name": staff_name,
            "counter_number": counter_number,
            "status": "created"
        }
    
    @staticmethod
    def authenticate_counter(db: Session, billing_pin: str) -> dict:
        """Authenticate staff with PIN"""
        counter = db.query(BillingCounter).filter_by(billing_pin=billing_pin).first()
        
        if not counter:
            return {"authenticated": False, "error": "Invalid PIN"}
        
        if not counter.is_active:
            return {"authenticated": False, "error": "Counter disabled"}
        
        return {
            "authenticated": True,
            "counter_id": counter.id,
            "staff_name": counter.staff_name,
            "counter_number": counter.counter_number,
            "user_id": counter.user_id
        }
    
    @staticmethod
    def tag_sale_to_counter(db: Session, shop_id: int, counter_id: int, 
                           invoice_id: int, staff_name: str, 
                           counter_number: int, sale_amount: float) -> dict:
        """Link sale to specific counter/staff"""
        counter_sale = SalesByCounter(
            shop_id=shop_id,
            counter_id=counter_id,
            invoice_id=invoice_id,
            staff_name=staff_name,
            counter_number=counter_number,
            sale_date=date.today(),
            sale_amount=sale_amount
        )
        db.add(counter_sale)
        db.commit()
        
        return {
            "sale_id": counter_sale.id,
            "counter": counter_number,
            "staff": staff_name,
            "amount": sale_amount
        }
    
    @staticmethod
    def get_all_counters(db: Session, user_id: int) -> list:
        """Get all billing counters for shop"""
        counters = db.query(BillingCounter).filter_by(user_id=user_id).all()
        
        return [{
            "counter_id": c.id,
            "staff_name": c.staff_name,
            "counter_number": c.counter_number,
            "is_active": c.is_active,
            "created_at": c.created_at.isoformat()
        } for c in counters]
    
    @staticmethod
    def deactivate_counter(db: Session, counter_id: int) -> bool:
        """Disable billing counter (e.g., staff left)"""
        counter = db.query(BillingCounter).filter_by(id=counter_id).first()
        if counter:
            counter.is_active = False
            db.commit()
            return True
        return False
    
    @staticmethod
    def get_counter_daily_sales(db: Session, counter_id: int) -> dict:
        """Get today's sales breakdown for a counter"""
        today = date.today()
        
        sales = db.query(SalesByCounter).filter(
            SalesByCounter.counter_id == counter_id,
            SalesByCounter.sale_date == today
        ).all()
        
        total_sales = sum(float(s.sale_amount) for s in sales if s.sale_amount)
        bill_count = len(sales)
        avg_bill = total_sales / bill_count if bill_count > 0 else 0
        
        return {
            "counter_id": counter_id,
            "date": today.isoformat(),
            "total_sales": total_sales,
            "bill_count": bill_count,
            "avg_bill_value": avg_bill,
            "bills": [{
                "invoice_id": s.invoice_id,
                "amount": float(s.sale_amount),
                "time": s.created_at.isoformat()
            } for s in sales]
        }
    
    @staticmethod
    def get_all_counters_summary(db: Session, shop_id: int) -> dict:
        """Get today's sales summary for all counters"""
        today = date.today()
        
        counters = db.query(
            SalesByCounter.counter_number,
            SalesByCounter.staff_name,
            func.count(SalesByCounter.id).label("bill_count"),
            func.sum(SalesByCounter.sale_amount).label("total")
        ).filter(
            SalesByCounter.shop_id == shop_id,
            SalesByCounter.sale_date == today
        ).group_by(
            SalesByCounter.counter_number,
            SalesByCounter.staff_name
        ).all()
        
        summary = []
        grand_total = 0
        grand_bills = 0
        
        for counter_num, staff, bill_count, total in counters:
            total_amount = float(total) if total else 0
            grand_total += total_amount
            grand_bills += bill_count or 0
            
            summary.append({
                "counter": counter_num,
                "staff": staff,
                "bills": bill_count or 0,
                "total": total_amount,
                "avg_bill": total_amount / (bill_count or 1)
            })
        
        return {
            "date": today.isoformat(),
            "total_revenue": grand_total,
            "total_bills": grand_bills,
            "avg_bill": grand_total / (grand_bills or 1),
            "counters": summary
        }
    
    @staticmethod
    def generate_counter_report(db: Session, shop_id: int, 
                               counter_id: int, days: int = 7) -> dict:
        """Generate sales report for counter over N days"""
        from datetime import timedelta
        start_date = date.today() - timedelta(days=days)
        
        daily_stats = db.query(
            SalesByCounter.sale_date,
            func.count(SalesByCounter.id).label("bills"),
            func.sum(SalesByCounter.sale_amount).label("total")
        ).filter(
            SalesByCounter.counter_id == counter_id,
            SalesByCounter.sale_date >= start_date
        ).group_by(SalesByCounter.sale_date).all()
        
        total_revenue = sum(float(s[2]) if s[2] else 0 for s in daily_stats)
        total_bills = sum(s[1] or 0 for s in daily_stats)
        
        return {
            "period": f"Last {days} days",
            "total_revenue": total_revenue,
            "total_bills": total_bills,
            "avg_daily_revenue": total_revenue / days if days > 0 else 0,
            "daily_breakdown": [{
                "date": s[0].isoformat(),
                "bills": s[1] or 0,
                "total": float(s[2]) if s[2] else 0
            } for s in daily_stats]
        }
