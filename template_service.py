"""
Billing Template Service (Feature 9)
Save and load frequently used bill templates
"""

from sqlalchemy.orm import Session
from models import BillingTemplate
from datetime import datetime
import json


class TemplateService:
    
    @staticmethod
    def save_template(db: Session, user_id: int, template_name: str, 
                     template_items: list) -> dict:
        """
        Save bill template
        template_items: [{product_id, product_name, qty, price}, ...]
        """
        template_data = json.dumps(template_items)
        
        # Check if template name already exists
        existing = db.query(BillingTemplate).filter_by(
            user_id=user_id, 
            template_name=template_name
        ).first()
        
        if existing:
            existing.template_data = template_data
            db.commit()
            return {
                "template_id": existing.id,
                "template_name": template_name,
                "status": "updated",
                "item_count": len(template_items)
            }
        else:
            template = BillingTemplate(
                user_id=user_id,
                template_name=template_name,
                template_data=template_data
            )
            db.add(template)
            db.commit()
            
            return {
                "template_id": template.id,
                "template_name": template_name,
                "status": "created",
                "item_count": len(template_items)
            }
    
    @staticmethod
    def get_all_templates(db: Session, user_id: int) -> list:
        """Get all saved templates for user"""
        templates = db.query(BillingTemplate).filter_by(user_id=user_id)\
                      .order_by(BillingTemplate.last_used.desc()).all()
        
        result = []
        for t in templates:
            try:
                items = json.loads(t.template_data)
                result.append({
                    "template_id": t.id,
                    "template_name": t.template_name,
                    "item_count": len(items),
                    "last_used": t.last_used.isoformat() if t.last_used else None,
                    "created": t.created_at.isoformat()
                })
            except:
                pass
        
        return result
    
    @staticmethod
    def load_template(db: Session, template_id: int) -> dict:
        """Load template items and mark as recently used"""
        template = db.query(BillingTemplate).filter_by(id=template_id).first()
        
        if not template:
            return {"error": "Template not found"}
        
        # Update last_used
        template.last_used = datetime.now()
        db.commit()
        
        try:
            items = json.loads(template.template_data)
            return {
                "template_id": template.id,
                "template_name": template.template_name,
                "items": items,
                "item_count": len(items)
            }
        except:
            return {"error": "Invalid template data"}
    
    @staticmethod
    def delete_template(db: Session, template_id: int) -> bool:
        """Delete a template"""
        template = db.query(BillingTemplate).filter_by(id=template_id).first()
        if template:
            db.delete(template)
            db.commit()
            return True
        return False
    
    @staticmethod
    def auto_suggest_template(db: Session, user_id: int, customer_phone: str) -> dict:
        """
        Auto-suggest template based on customer's past orders
        (This would require querying historical sales - basic implementation)
        """
        # In a real system, you'd query past invoice history for this customer
        # For now, return top 3 most recently used templates
        
        templates = db.query(BillingTemplate).filter_by(user_id=user_id)\
                      .order_by(BillingTemplate.last_used.desc()).limit(3).all()
        
        if not templates:
            return {"suggestions": []}
        
        suggestions = []
        for t in templates:
            try:
                items = json.loads(t.template_data)
                suggestions.append({
                    "template_id": t.id,
                    "template_name": t.template_name,
                    "item_count": len(items),
                    "last_used": t.last_used.isoformat() if t.last_used else None
                })
            except:
                pass
        
        return {
            "suggestions": suggestions,
            "message": f"Found {len(suggestions)} suggested templates based on recent usage"
        }
    
    @staticmethod
    def get_template_statistics(db: Session, user_id: int) -> dict:
        """Get statistics about template usage"""
        templates = db.query(BillingTemplate).filter_by(user_id=user_id).all()
        
        if not templates:
            return {
                "total_templates": 0,
                "total_items": 0,
                "most_recent": None
            }
        
        total_items = 0
        for t in templates:
            try:
                items = json.loads(t.template_data)
                total_items += len(items)
            except:
                pass
        
        most_recent = max(templates, key=lambda x: x.last_used or x.created_at)
        
        return {
            "total_templates": len(templates),
            "total_items": total_items,
            "most_recent_template": most_recent.template_name,
            "most_recent_used": most_recent.last_used.isoformat() if most_recent.last_used else None
        }
