"""
Festival Stock Predictor Service (Feature 3)
Indian festival calendar with last year sales comparison
Festivals: Diwali, Holi, Eid, Pongal, Navratri, Durga Puja, Rakhi, etc.
"""

from sqlalchemy.orm import Session
from models import FestivalEvent, StockMovement, Product
from sqlalchemy import func
from datetime import date, timedelta
import json


# Indian Festival Calendar (static for now - can be loaded from config)
INDIAN_FESTIVALS = {
    "Diwali": (11, 1),  # November 1 approx
    "Holi": (3, 25),  # March 25 approx
    "Eid": (4, 10),  # April 10 approx (varies)
    "Pongal": (1, 14),  # January 14
    "Navratri": (10, 1),  # October 1 approx
    "Durga Puja": (10, 15),  # October 15 approx
    "Rakhi": (8, 15),  # August 15 approx
    "Janmashtami": (8, 25),  # August 25 approx
    "Ganesh Chaturthi": (9, 7),  # September 7 approx
    "Makar Sankranti": (1, 14),  # January 14
}


class FestivalService:
    
    @staticmethod
    def initialize_festival_calendar(db: Session, year: int):
        """Initialize festival events for a year"""
        from datetime import datetime
        
        for festival_name, (month, day) in INDIAN_FESTIVALS.items():
            festival_date = date(year, month, day)
            
            # Check if already exists
            existing = db.query(FestivalEvent).filter_by(
                festival_name=festival_name,
                festival_year=year
            ).first()
            
            if not existing:
                event = FestivalEvent(
                    festival_name=festival_name,
                    festival_date=festival_date,
                    festival_year=year
                )
                db.add(event)
        
        db.commit()
    
    @staticmethod
    def get_upcoming_festivals(db: Session, days_ahead: int = 30) -> list:
        """Get festivals coming in next N days"""
        today = date.today()
        future_date = today + timedelta(days=days_ahead)
        
        year = today.year
        
        # Check if festivals initialized for this year
        existing_festivals = db.query(FestivalEvent).filter_by(festival_year=year).count()
        if existing_festivals == 0:
            FestivalService.initialize_festival_calendar(db, year)
        
        festivals = db.query(FestivalEvent).filter(
            FestivalEvent.festival_year == year,
            FestivalEvent.festival_date >= today,
            FestivalEvent.festival_date <= future_date
        ).order_by(FestivalEvent.festival_date).all()
        
        return [{
            "festival_name": f.festival_name,
            "festival_date": f.festival_date.isoformat(),
            "days_until": (f.festival_date - today).days
        } for f in festivals]
    
    @staticmethod
    def get_festival_stock_prediction(db: Session, user_id: int, festival_id: int) -> dict:
        """
        Get stock prediction for a festival.
        Compare last year's sales for 10 days before festival.
        """
        festival = db.query(FestivalEvent).filter_by(id=festival_id).first()
        if not festival:
            return {"error": "Festival not found"}
        
        # Get festival date range (7-14 days before festival)
        festival_date = festival.festival_date
        lookback_start = festival_date - timedelta(days=14)
        lookback_end = festival_date - timedelta(days=7)
        
        # Query last year's same period
        last_year_start = lookback_start.replace(year=lookback_start.year - 1)
        last_year_end = lookback_end.replace(year=lookback_end.year - 1)
        
        # Get top selling products from last year during this period
        top_products = db.query(
            Product.id,
            Product.product_name,
            func.sum(StockMovement.quantity).label("qty_sold")
        ).join(StockMovement).filter(
            Product.user_id == user_id,
            StockMovement.movement_type == "OUT",
            StockMovement.created_at >= last_year_start,
            StockMovement.created_at <= last_year_end
        ).group_by(Product.id, Product.product_name).order_by(
            func.sum(StockMovement.quantity).desc()
        ).limit(5).all()
        
        top_5 = [{
            "product_id": p[0],
            "product_name": p[1],
            "qty_last_year": int(p[2]) if p[2] else 0,
            "suggested_stock": int((p[2] or 0) * 1.2)  # 20% buffer
        } for p in top_products]
        
        days_until = (festival_date - date.today()).days
        
        return {
            "festival_name": festival.festival_name,
            "festival_date": festival_date.isoformat(),
            "days_until": days_until,
            "should_alert": days_until <= 14,  # Alert if 7-14 days away
            "top_5_products": top_5,
            "recommendation": f"Stock up on these {len(top_5)} products. Based on last year's {festival.festival_name} sales."
        }
    
    @staticmethod
    def get_all_festival_predictions(db: Session, user_id: int) -> list:
        """Get predictions for all upcoming festivals (7-14 days away)"""
        today = date.today()
        future_date = today + timedelta(days=14)
        
        year = today.year
        existing = db.query(FestivalEvent).filter_by(festival_year=year).count()
        if existing == 0:
            FestivalService.initialize_festival_calendar(db, year)
        
        festivals = db.query(FestivalEvent).filter(
            FestivalEvent.festival_year == year,
            FestivalEvent.festival_date >= today,
            FestivalEvent.festival_date <= future_date
        ).all()
        
        predictions = []
        for festival in festivals:
            pred = FestivalService.get_festival_stock_prediction(db, user_id, festival.id)
            if pred.get("should_alert"):
                predictions.append(pred)
        
        return predictions
    
    @staticmethod
    def format_festival_banner(prediction: dict) -> str:
        """Format festival prediction as banner text"""
        banner = f"""🎉 {prediction['festival_name']} Alert!

{prediction['days_until']} days away - Time to stock up!

Top 5 Products (Last Year):"""
        
        for i, product in enumerate(prediction["top_5_products"], 1):
            banner += f"\n{i}. {product['product_name']}"
            banner += f"\n   Last Year: {product['qty_last_year']} units"
            banner += f"\n   Suggested: {product['suggested_stock']} units"
        
        return banner
    
    @staticmethod
    def get_festival_top_products(db: Session, user_id: int, festival_name: str) -> list:
        """Get top products for a specific festival"""
        year = date.today().year
        festival = db.query(FestivalEvent).filter_by(
            festival_name=festival_name,
            festival_year=year
        ).first()
        
        if not festival:
            return []
        
        prediction = FestivalService.get_festival_stock_prediction(db, user_id, festival.id)
        return prediction.get("top_5_products", [])
