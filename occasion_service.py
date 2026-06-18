"""
Customer Occasion Service (Feature 14)
Track birthdays and send auto-discount messages on WhatsApp
"""

from sqlalchemy.orm import Session
from models import CustomerOccasion, Customer
from datetime import date, datetime, timedelta


class OccasionService:
    
    @staticmethod
    def add_occasion(db: Session, customer_id: int, occasion_type: str, 
                    occasion_date: date, discount_percentage: float = 10) -> dict:
        """Add birthday/anniversary/occasion for customer"""
        customer = db.query(Customer).filter_by(id=customer_id).first()
        if not customer:
            return {"error": "Customer not found"}
        
        occasion = CustomerOccasion(
            customer_id=customer_id,
            occasion_type=occasion_type,
            occasion_date=occasion_date,
            discount_percentage=discount_percentage
        )
        db.add(occasion)
        db.commit()
        
        return {
            "occasion_id": occasion.id,
            "customer_name": customer.customer_name,
            "occasion_type": occasion_type,
            "discount": discount_percentage,
            "status": "added"
        }
    
    @staticmethod
    def get_today_occasions(db: Session, user_id: int) -> list:
        """Get all customers with occasions today"""
        today = date.today()
        
        # Query occasions where MM-DD matches today
        occasions = db.query(CustomerOccasion).join(Customer).filter(
            Customer.user_id == user_id
        ).all()
        
        today_occasions = []
        for occ in occasions:
            # Compare month-day only (for annual occasions)
            if occ.occasion_date.month == today.month and occ.occasion_date.day == today.day:
                customer = db.query(Customer).filter_by(id=occ.customer_id).first()
                today_occasions.append({
                    "occasion_id": occ.id,
                    "customer_id": occ.customer_id,
                    "customer_name": customer.customer_name,
                    "customer_whatsapp": customer.whatsapp_number,
                    "occasion_type": occ.occasion_type,
                    "discount_percentage": occ.discount_percentage,
                    "last_notified": occ.last_notification_sent.isoformat() if occ.last_notification_sent else None
                })
        
        return today_occasions
    
    @staticmethod
    def send_occasion_notification(db: Session, occasion_id: int) -> dict:
        """
        Send WhatsApp message for occasion.
        Returns: WhatsApp template with customer data to send.
        """
        occasion = db.query(CustomerOccasion).filter_by(id=occasion_id).first()
        if not occasion:
            return {"error": "Occasion not found"}
        
        customer = db.query(Customer).filter_by(id=occasion.customer_id).first()
        
        # Generate message
        if occasion.occasion_type == "BIRTHDAY":
            message = f"""🎂 Happy Birthday {customer.customer_name}! 🎉

On your special day, enjoy {occasion.discount_percentage}% discount on your purchase!

Valid Today Only
Use this offer at our store. Thank you for being a loyal customer! 💝

Shop Name: [Your Shop]"""
        elif occasion.occasion_type == "ANNIVERSARY":
            message = f"""🎊 Happy Anniversary {customer.customer_name}! 🎊

Celebrating with you! Get {occasion.discount_percentage}% off today!

Valid Today Only
Shop Name: [Your Shop]"""
        else:
            message = f"""🎉 Special {occasion.occasion_type} Offer for {customer.customer_name}!

Enjoy {occasion.discount_percentage}% discount today!

Shop Name: [Your Shop]"""
        
        # Mark as notified
        occasion.last_notification_sent = datetime.now()
        db.commit()
        
        return {
            "occasion_id": occasion.occasion_id,
            "customer_whatsapp": customer.whatsapp_number,
            "customer_name": customer.customer_name,
            "message": message,
            "discount": occasion.discount_percentage,
            "action": "Send this WhatsApp message to customer"
        }
    
    @staticmethod
    def get_upcoming_occasions(db: Session, user_id: int, days_ahead: int = 30) -> list:
        """Get upcoming occasions for the next N days"""
        from datetime import datetime as dt
        today = date.today()
        future_date = today + timedelta(days=days_ahead)
        
        occasions = db.query(CustomerOccasion).join(Customer).filter(
            Customer.user_id == user_id
        ).all()
        
        upcoming = []
        for occ in occasions:
            # For simplicity, assume current year
            occasion_this_year = occ.occasion_date.replace(year=today.year)
            
            # If already passed this year, check next year
            if occasion_this_year < today:
                occasion_this_year = occ.occasion_date.replace(year=today.year + 1)
            
            # If within range
            if today <= occasion_this_year <= future_date:
                days_until = (occasion_this_year - today).days
                customer = db.query(Customer).filter_by(id=occ.customer_id).first()
                upcoming.append({
                    "occasion_id": occ.id,
                    "customer_name": customer.customer_name,
                    "occasion_type": occ.occasion_type,
                    "occasion_date": occasion_this_year.isoformat(),
                    "days_until": days_until,
                    "discount": occ.discount_percentage
                })
        
        return sorted(upcoming, key=lambda x: x["days_until"])
    
    @staticmethod
    def send_batch_occasion_notifications(db: Session, user_id: int) -> dict:
        """Send all pending occasion notifications for today"""
        today_occasions = OccasionService.get_today_occasions(db, user_id)
        
        notifications = []
        for occ in today_occasions:
            # Only send if not already sent today
            if not occ["last_notified"] or date.fromisoformat(occ["last_notified"].split("T")[0]) < date.today():
                result = OccasionService.send_occasion_notification(db, occ["occasion_id"])
                notifications.append(result)
        
        return {
            "total_to_send": len(notifications),
            "notifications": notifications,
            "message": f"Ready to send {len(notifications)} WhatsApp messages"
        }
    
    @staticmethod
    def delete_occasion(db: Session, occasion_id: int) -> bool:
        """Delete an occasion record"""
        occasion = db.query(CustomerOccasion).filter_by(id=occasion_id).first()
        if occasion:
            db.delete(occasion)
            db.commit()
            return True
        return False
    
    @staticmethod
    def get_customer_occasions(db: Session, customer_id: int) -> list:
        """Get all occasions for a customer"""
        occasions = db.query(CustomerOccasion).filter_by(customer_id=customer_id).all()
        
        return [{
            "occasion_id": occ.id,
            "occasion_type": occ.occasion_type,
            "occasion_date": occ.occasion_date.isoformat(),
            "discount_percentage": occ.discount_percentage,
            "created_at": occ.created_at.isoformat()
        } for occ in occasions]
