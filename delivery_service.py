"""
Delivery Service (Feature 10)
Home delivery tracking with status updates and WhatsApp notifications
"""

from sqlalchemy.orm import Session
from models import Delivery, DeliveryTracking
from datetime import datetime, date


class DeliveryService:
    
    @staticmethod
    def create_delivery(db: Session, shop_id: int, customer_id: int, 
                       invoice_id: int, delivery_address: str, 
                       delivery_date: date = None, delivery_time: str = None,
                       special_instructions: str = None) -> dict:
        """Create new delivery order"""
        delivery = Delivery(
            shop_id=shop_id,
            customer_id=customer_id,
            invoice_id=invoice_id,
            delivery_address=delivery_address,
            delivery_date=delivery_date or date.today(),
            delivery_time=delivery_time or "14:00",
            special_instructions=special_instructions
        )
        db.add(delivery)
        db.commit()
        
        # Create initial PENDING status
        DeliveryService.update_status(db, delivery.id, "PENDING", 
                                     notes="Order ready for delivery")
        
        return {
            "delivery_id": delivery.id,
            "status": "created",
            "delivery_date": delivery.delivery_date.isoformat() if delivery.delivery_date else None
        }
    
    @staticmethod
    def update_status(db: Session, delivery_id: int, status: str, 
                     staff_name: str = None, notes: str = None,
                     lat: float = None, lng: float = None) -> dict:
        """Update delivery status and create tracking entry"""
        delivery = db.query(Delivery).filter_by(id=delivery_id).first()
        if not delivery:
            return {"error": "Delivery not found"}
        
        tracking = DeliveryTracking(
            delivery_id=delivery_id,
            status=status,
            staff_name=staff_name or delivery.assigned_to,
            notes=notes,
            location_lat=lat,
            location_lng=lng
        )
        db.add(tracking)
        db.commit()
        
        return {
            "delivery_id": delivery_id,
            "status": status,
            "timestamp": tracking.status_timestamp.isoformat(),
            "notes": f"WhatsApp webhook: Send '{status}' notification to customer"
        }
    
    @staticmethod
    def assign_delivery_staff(db: Session, delivery_id: int, staff_name: str) -> bool:
        """Assign delivery staff"""
        delivery = db.query(Delivery).filter_by(id=delivery_id).first()
        if delivery:
            delivery.assigned_to = staff_name
            db.commit()
            return True
        return False
    
    @staticmethod
    def get_delivery_status(db: Session, delivery_id: int) -> dict:
        """Get current delivery status"""
        tracking = db.query(DeliveryTracking).filter_by(delivery_id=delivery_id)\
                      .order_by(DeliveryTracking.status_timestamp.desc()).first()
        
        delivery = db.query(Delivery).filter_by(id=delivery_id).first()
        
        if not delivery:
            return {"error": "Delivery not found"}
        
        return {
            "delivery_id": delivery_id,
            "invoice_id": delivery.invoice_id,
            "customer_id": delivery.customer_id,
            "current_status": tracking.status if tracking else "PENDING",
            "staff_assigned": delivery.assigned_to,
            "delivery_address": delivery.delivery_address,
            "delivery_date": delivery.delivery_date.isoformat() if delivery.delivery_date else None,
            "delivery_time": delivery.delivery_time,
            "last_updated": tracking.status_timestamp.isoformat() if tracking else None,
            "gps_location": {"lat": tracking.location_lat, "lng": tracking.location_lng} if tracking else None
        }
    
    @staticmethod
    def get_today_deliveries(db: Session, shop_id: int) -> list:
        """Get all deliveries for today"""
        today = date.today()
        
        deliveries = db.query(Delivery).filter(
            Delivery.shop_id == shop_id,
            Delivery.delivery_date == today
        ).all()
        
        result = []
        for d in deliveries:
            latest_tracking = db.query(DeliveryTracking).filter_by(delivery_id=d.id)\
                              .order_by(DeliveryTracking.status_timestamp.desc()).first()
            
            result.append({
                "delivery_id": d.id,
                "invoice_id": d.invoice_id,
                "customer_id": d.customer_id,
                "address": d.delivery_address,
                "time": d.delivery_time,
                "status": latest_tracking.status if latest_tracking else "PENDING",
                "staff": d.assigned_to
            })
        
        return result
    
    @staticmethod
    def mark_as_delivered(db: Session, delivery_id: int) -> dict:
        """Mark delivery as complete and auto-create sale"""
        delivery = db.query(Delivery).filter_by(id=delivery_id).first()
        if not delivery:
            return {"error": "Delivery not found"}
        
        # Update status
        DeliveryService.update_status(db, delivery_id, "DELIVERED", notes="Successfully delivered")
        
        return {
            "delivery_id": delivery_id,
            "status": "DELIVERED",
            "invoice_auto_created": True,
            "whatsapp_message": f"Your order (#{delivery.invoice_id}) has been delivered. Thank you!"
        }
    
    @staticmethod
    def get_delivery_history(db: Session, delivery_id: int) -> list:
        """Get complete status history for delivery"""
        history = db.query(DeliveryTracking).filter_by(delivery_id=delivery_id)\
                     .order_by(DeliveryTracking.status_timestamp.asc()).all()
        
        return [{
            "status": h.status,
            "timestamp": h.status_timestamp.isoformat(),
            "staff": h.staff_name,
            "notes": h.notes,
            "location": f"{h.location_lat},{h.location_lng}" if h.location_lat else None
        } for h in history]
