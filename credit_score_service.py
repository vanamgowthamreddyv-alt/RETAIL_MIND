"""
Customer Credit Scoring Service (Feature 13)
Calculate credit score (0-100) based on payment history
Tiers: CAUTION, REGULAR, TRUSTED
"""

from sqlalchemy.orm import Session
from models import CustomerCreditScore, Invoice, Payment, Customer
from decorator import decorator
from datetime import datetime, timedelta
from decimal import Decimal


class CreditScoreService:
    
    @staticmethod
    def calculate_credit_score(db: Session, customer_id: int) -> dict:
        """
        Calculate credit score (0-100) based on:
        - Payment history (on-time vs late)
        - Purchase frequency
        - Recency (days since last purchase)
        - Total purchase volume
        """
        customer = db.query(Customer).filter_by(id=customer_id).first()
        if not customer:
            return {"error": "Customer not found"}
        
        # Get all invoices for customer
        invoices = db.query(Invoice).filter_by(customer_id=customer_id).all()
        
        if not invoices:
            # New customer: REGULAR by default
            score_record = db.query(CustomerCreditScore).filter_by(customer_id=customer_id).first()
            if not score_record:
                score_record = CustomerCreditScore(customer_id=customer_id)
                db.add(score_record)
            score_record.credit_score = 50
            score_record.score_badge = "REGULAR"
            db.commit()
            return {
                "customer_id": customer_id,
                "credit_score": 50,
                "badge": "REGULAR",
                "reason": "New customer"
            }
        
        # Calculate metrics
        total_invoices = len(invoices)
        on_time = 0
        late = 0
        total_amount = Decimal("0")
        overdue_days = []
        
        now = datetime.now().date()
        
        for inv in invoices:
            total_amount += inv.total_amount
            
            # Check if paid
            payments = db.query(Payment).filter_by(invoice_id=inv.id).all()
            total_paid = sum(p.amount for p in payments)
            
            if total_paid >= inv.total_amount:
                # Invoice is paid - check if on time
                last_payment = max(payments, key=lambda p: p.payment_date) if payments else None
                if last_payment and last_payment.payment_date.date() <= inv.due_date:
                    on_time += 1
                else:
                    if last_payment:
                        days_late = (last_payment.payment_date.date() - inv.due_date).days
                        late += 1
                        overdue_days.append(days_late)
            else:
                # Unpaid / partial
                days_overdue = (now - inv.due_date).days if now > inv.due_date else 0
                if days_overdue > 0:
                    overdue_days.append(days_overdue)
        
        # Get recency (days since last purchase)
        last_invoice = max(invoices, key=lambda x: x.invoice_date)
        days_since_purchase = (now - last_invoice.invoice_date).days if last_invoice else 999
        
        # Score calculation (0-100)
        score = 50  # Base score
        
        # Payment behavior (40 points)
        if total_invoices > 0:
            on_time_rate = on_time / total_invoices
            score += int(on_time_rate * 40)
        
        # Frequency (20 points)
        if total_invoices >= 10:
            score += 20
        elif total_invoices >= 5:
            score += 15
        elif total_invoices >= 2:
            score += 10
        
        # Recency (20 points) - penalize inactive customers
        if days_since_purchase <= 7:
            score += 20
        elif days_since_purchase <= 30:
            score += 15
        elif days_since_purchase <= 90:
            score += 10
        elif days_since_purchase <= 180:
            score += 5
        
        # Penalize very late payments
        if overdue_days:
            avg_late = sum(overdue_days) / len(overdue_days)
            if avg_late > 30:
                score -= 20
            elif avg_late > 15:
                score -= 10
        
        score = max(0, min(100, score))  # Clamp to 0-100
        
        # Determine badge
        if score >= 75:
            badge = "TRUSTED"
        elif score >= 50:
            badge = "REGULAR"
        else:
            badge = "CAUTION"
        
        # Calculate suggested credit limit (based on avg purchase value)
        avg_purchase = float(total_amount) / total_invoices if total_invoices > 0 else 0
        suggested_limit = Decimal(str(avg_purchase * 3))  # 3x monthly average
        
        # Save score
        score_record = db.query(CustomerCreditScore).filter_by(customer_id=customer_id).first()
        if not score_record:
            score_record = CustomerCreditScore(customer_id=customer_id)
            db.add(score_record)
        
        score_record.credit_score = score
        score_record.score_badge = badge
        score_record.suggested_credit_limit = suggested_limit
        score_record.total_purchases = total_invoices
        score_record.on_time_payments = on_time
        score_record.late_payments = late
        score_record.days_since_last_purchase = days_since_purchase
        score_record.avg_days_to_pay = sum(overdue_days) / len(overdue_days) if overdue_days else 0
        score_record.last_calculated = datetime.now()
        
        db.commit()
        
        return {
            "customer_id": customer_id,
            "credit_score": score,
            "badge": badge,
            "suggested_credit_limit": float(suggested_limit),
            "total_purchases": total_invoices,
            "on_time_rate": f"{(on_time/total_invoices*100):.0f}%" if total_invoices > 0 else "0%",
            "days_since_last_purchase": days_since_purchase
        }
    
    @staticmethod
    def get_credit_score(db: Session, customer_id: int) -> dict:
        """Get current credit score for customer"""
        score = db.query(CustomerCreditScore).filter_by(customer_id=customer_id).first()
        
        if not score:
            return CreditScoreService.calculate_credit_score(db, customer_id)
        
        return {
            "customer_id": customer_id,
            "credit_score": score.credit_score,
            "badge": score.score_badge,
            "suggested_credit_limit": float(score.suggested_credit_limit or 0),
            "last_updated": score.last_calculated.isoformat() if score.last_calculated else None
        }
    
    @staticmethod
    def recalculate_all_scores(db: Session, user_id: int):
        """Recalculate scores for all customers of a shop"""
        customers = db.query(Customer).filter_by(user_id=user_id).all()
        
        results = []
        for customer in customers:
            result = CreditScoreService.calculate_credit_score(db, customer.id)
            results.append({
                "customer_id": customer.id,
                "customer_name": customer.customer_name,
                "new_score": result.get("credit_score"),
                "new_badge": result.get("badge")
            })
        
        return {
            "total_recalculated": len(results),
            "results": results
        }
    
    @staticmethod
    def get_customers_by_badge(db: Session, user_id: int, badge: str) -> list:
        """Get all customers with specific badge"""
        scores = db.query(CustomerCreditScore).join(Customer).filter(
            Customer.user_id == user_id,
            CustomerCreditScore.score_badge == badge
        ).all()
        
        return [{
            "customer_id": s.customer_id,
            "score": s.credit_score,
            "suggested_limit": float(s.suggested_credit_limit or 0)
        } for s in scores]
    
    @staticmethod
    def adjust_score_manually(db: Session, customer_id: int, adjustment: int, reason: str) -> dict:
        """Manual score adjustment (for one-offs)"""
        score = db.query(CustomerCreditScore).filter_by(customer_id=customer_id).first()
        if not score:
            return {"error": "Score not found"}
        
        old_score = score.credit_score
        score.credit_score = max(0, min(100, score.credit_score + adjustment))
        
        # Update badge if needed
        if score.credit_score >= 75:
            score.score_badge = "TRUSTED"
        elif score.credit_score >= 50:
            score.score_badge = "REGULAR"
        else:
            score.score_badge = "CAUTION"
        
        db.commit()
        
        return {
            "old_score": old_score,
            "new_score": score.credit_score,
            "new_badge": score.score_badge,
            "reason": reason
        }
