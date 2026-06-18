"""
Loyalty Points Service (Feature 7)
Manages customer loyalty points, tiers, and redemption
₹100 = 1 point. Tiers: Bronze/Silver/Gold
"""

from sqlalchemy.orm import Session
from models import Customer, CustomerLoyalty, LoyaltyTier, LoyaltyTransaction
from models import Invoice
from datetime import datetime
from decimal import Decimal


class LoyaltyService:
    
    @staticmethod
    def initialize_customer_loyalty(db: Session, customer_id: int) -> CustomerLoyalty:
        """Create loyalty record for new customer"""
        loyalty = CustomerLoyalty(
            customer_id=customer_id,
            total_points=0,
            available_points=0
        )
        db.add(loyalty)
        db.commit()
        return loyalty
    
    @staticmethod
    def earn_points(db: Session, customer_id: int, invoice_id: int, amount: Decimal) -> dict:
        """
        Earn points from purchase.
        ₹100 = 1 point
        Returns: {points_earned, new_total, tier_name, tier_bumped}
        """
        loyalty = db.query(CustomerLoyalty).filter_by(customer_id=customer_id).first()
        if not loyalty:
            loyalty = LoyaltyService.initialize_customer_loyalty(db, customer_id)
        
        # Calculate points: 100 rupees = 1 point
        points_earned = int(float(amount) // 100)
        
        if points_earned > 0:
            loyalty.total_points += points_earned
            loyalty.available_points += points_earned
            
            # Create transaction record
            LoyaltyService._record_transaction(
                db, loyalty.id, "EARN", points_earned, 
                reference_id=str(invoice_id), notes=f"Purchase: ₹{amount}"
            )
            
            # Check for tier upgrade
            tier_bumped = LoyaltyService.check_and_update_tier(db, customer_id)
            
            db.commit()
            
            tier = db.query(LoyaltyTier).filter_by(id=loyalty.current_tier_id).first()
            tier_name = tier.tier_name if tier else "Bronze"
            
            return {
                "points_earned": points_earned,
                "total_points": loyalty.total_points,
                "available_points": loyalty.available_points,
                "tier_name": tier_name,
                "tier_bumped": tier_bumped
            }
        
        return {"points_earned": 0, "total_points": loyalty.total_points, "tier_bumped": False}
    
    @staticmethod
    def redeem_points(db: Session, customer_id: int, points: int, invoice_id: int) -> dict:
        """
        Redeem points as discount.
        Returns: {points_redeemed, discount_amount, tier_discount, final_discount}
        """
        loyalty = db.query(CustomerLoyalty).filter_by(customer_id=customer_id).first()
        if not loyalty or loyalty.available_points < points:
            return {"success": False, "error": "Insufficient points"}
        
        # Get current tier for discount multiplier
        tier = db.query(LoyaltyTier).filter_by(id=loyalty.current_tier_id).first()
        tier_discount_pct = tier.discount_percentage if tier else 0
        
        # Base: 1 point = ₹1, plus tier discount
        discount_amount = points * (1 + tier_discount_pct / 100)
        
        loyalty.available_points -= points
        loyalty.points_redeemed += points
        
        LoyaltyService._record_transaction(
            db, loyalty.id, "REDEEM", points, 
            reference_id=str(invoice_id), 
            notes=f"Redeemed for ₹{discount_amount} discount"
        )
        
        db.commit()
        
        return {
            "success": True,
            "points_redeemed": points,
            "discount_amount": discount_amount,
            "tier_discount_pct": tier_discount_pct,
            "remaining_points": loyalty.available_points
        }
    
    @staticmethod
    def check_and_update_tier(db: Session, customer_id: int) -> bool:
        """
        Check if customer should upgrade tier.
        Tiers: Bronze (<500), Silver (500-1000), Gold (>1000)
        Returns: True if tier changed
        """
        loyalty = db.query(CustomerLoyalty).filter_by(customer_id=customer_id).first()
        if not loyalty:
            return False
        
        old_tier_id = loyalty.current_tier_id
        
        if loyalty.total_points >= 1000:
            new_tier = db.query(LoyaltyTier).filter_by(tier_level=3).first()
        elif loyalty.total_points >= 500:
            new_tier = db.query(LoyaltyTier).filter_by(tier_level=2).first()
        else:
            new_tier = db.query(LoyaltyTier).filter_by(tier_level=1).first()
        
        if new_tier and new_tier.id != old_tier_id:
            loyalty.current_tier_id = new_tier.id
            loyalty.tier_updated_at = datetime.now()
            loyalty.last_tier_bump_notified = False
            db.commit()
            return True
        
        return False
    
    @staticmethod
    def setup_default_tiers(db: Session, user_id: int):
        """Initialize Bronze/Silver/Gold tiers for new shop"""
        tiers = [
            LoyaltyTier(user_id=user_id, tier_name="Bronze", tier_level=1, min_points=0, discount_percentage=0),
            LoyaltyTier(user_id=user_id, tier_name="Silver", tier_level=2, min_points=500, discount_percentage=5),
            LoyaltyTier(user_id=user_id, tier_name="Gold", tier_level=3, min_points=1000, discount_percentage=10)
        ]
        db.add_all(tiers)
        db.commit()
    
    @staticmethod
    def get_customer_loyalty_status(db: Session, customer_id: int) -> dict:
        """Get complete loyalty status for customer card display"""
        loyalty = db.query(CustomerLoyalty).filter_by(customer_id=customer_id).first()
        if not loyalty:
            return {"status": "inactive"}
        
        tier = db.query(LoyaltyTier).filter_by(id=loyalty.current_tier_id).first()
        
        return {
            "total_points": loyalty.total_points,
            "available_points": loyalty.available_points,
            "tier_name": tier.tier_name if tier else "Bronze",
            "tier_level": tier.tier_level if tier else 1,
            "discount_percentage": tier.discount_percentage if tier else 0,
            "points_to_next_tier": max(0, tier.min_points - loyalty.total_points) if tier else 0
        }
    
    @staticmethod
    def _record_transaction(db: Session, loyalty_id: int, txn_type: str, points: int, 
                           reference_id: str = None, notes: str = None):
        """Helper to record loyalty transaction"""
        txn = LoyaltyTransaction(
            customer_loyalty_id=loyalty_id,
            transaction_type=txn_type,
            points=points,
            reference_id=reference_id,
            notes=notes
        )
        db.add(txn)
