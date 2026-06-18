"""
Customer Management Router
Customer CRUD, contact preferences, credit profiles
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, EmailStr
from datetime import datetime
from typing import List, Optional
from db import sessionLocal, get_db
from security import get_current_user as check_current_user
from models import Customer

router = APIRouter(prefix="/api/customers", tags=["customers"])

# ==================== PYDANTIC MODELS ====================

class CustomerCreate(BaseModel):
    customer_name: str
    email: Optional[EmailStr] = None
    phone: str = Field(..., min_length=10, max_length=10, pattern=r"^\d{10}$")
    whatsapp_number: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    credit_limit: float = 0
    payment_terms: Optional[str] = None
    contact_preference: str = "EMAIL"  # EMAIL, WHATSAPP, CALL, SMS

class CustomerUpdate(BaseModel):
    customer_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = Field(None, min_length=10, max_length=10, pattern=r"^\d{10}$")
    whatsapp_number: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    credit_limit: Optional[float] = None
    payment_terms: Optional[str] = None
    contact_preference: Optional[str] = None

class CustomerResponse(BaseModel):
    id: int
    customer_name: str
    email: Optional[str]
    phone: str = Field(..., min_length=10, max_length=10, pattern=r"^\d{10}$")
    whatsapp_number: Optional[str]
    address: Optional[str]
    city: Optional[str]
    state: Optional[str]
    postal_code: Optional[str]
    credit_limit: float
    payment_terms: Optional[str]
    contact_preference: str
    created_at: datetime

    class Config:
        from_attributes = True

# ==================== CRUD OPERATIONS ====================

@router.post("/", response_model=CustomerResponse)
def create_customer(
    customer: CustomerCreate,
    user_id: int = Depends(check_current_user),
    db: Session = Depends(get_db)
):
    """Create a new customer"""
    # Check if customer with same phone already exists
    existing = db.query(Customer).filter(
        Customer.user_id == user_id,
        Customer.phone == customer.phone
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Customer with this phone number already exists")
    
    db_customer = Customer(
        user_id=user_id,
        **customer.dict()
    )
    
    db.add(db_customer)
    db.commit()
    db.refresh(db_customer)
    
    return db_customer

@router.get("/", response_model=List[CustomerResponse])
def get_customers(
    user_id: int = Depends(check_current_user),
    city: Optional[str] = None,
    skip: int = Query(0),
    limit: int = Query(100),
    db: Session = Depends(get_db)
):
    """Get all customers — only active (non-deleted)"""
    query = db.query(Customer).filter(
        Customer.user_id == user_id,
        Customer.is_active == True  # Soft-delete filter
    )
    
    if city:
        query = query.filter(Customer.city == city)
    
    return query.offset(skip).limit(limit).all()

@router.get("/{customer_id}", response_model=CustomerResponse)
def get_customer(
    customer_id: int,
    user_id: int = Depends(check_current_user),
    db: Session = Depends(get_db)
):
    """Get customer details"""
    customer = db.query(Customer).filter(
        Customer.id == customer_id,
        Customer.user_id == user_id
    ).first()
    
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    return customer

@router.put("/{customer_id}", response_model=CustomerResponse)
def update_customer(
    customer_id: int,
    customer_update: CustomerUpdate,
    user_id: int = Depends(check_current_user),
    db: Session = Depends(get_db)
):
    """Update customer — account-scoped"""
    db_customer = db.query(Customer).filter(
        Customer.id == customer_id,
        Customer.user_id == user_id
    ).first()
    
    if not db_customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    update_data = customer_update.dict(exclude_unset=True)
    
    for field, value in update_data.items():
        setattr(db_customer, field, value)
    
    db.add(db_customer)
    db.commit()
    db.refresh(db_customer)
    
    return db_customer

@router.delete("/{customer_id}")
def delete_customer(
    customer_id: int,
    user_id: int = Depends(check_current_user),
    db: Session = Depends(get_db)
):
    """Soft-delete customer — archives them, preserving all Khata and invoice history"""
    customer = db.query(Customer).filter(
        Customer.id == customer_id,
        Customer.user_id == user_id
    ).first()
    
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    customer.is_active = False  # Soft delete — preserves all transaction history
    db.commit()
    
    return {"message": f"Customer '{customer.customer_name}' archived. Khata and invoice history preserved."}

@router.post("/{customer_id}/set-contact-preference")
def set_contact_preference(
    customer_id: int,
    preference: str = Query(...),  # EMAIL, WHATSAPP, CALL, SMS
    db: Session = Depends(get_db)
):
    """Set preferred contact method for customer"""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    if preference not in ["EMAIL", "WHATSAPP", "CALL", "SMS"]:
        raise HTTPException(status_code=400, detail="Invalid contact preference")
    
    customer.contact_preference = preference
    db.commit()
    
    return {"message": f"Contact preference set to {preference}"}

@router.get("/search/by-phone")
def search_by_phone(
    phone: str = Query(..., min_length=10, max_length=10, pattern=r"^\d{10}$"),
    user_id: int = Depends(check_current_user),
    db: Session = Depends(get_db)
):
    """Search customer by phone number — active customers only"""
    customer = db.query(Customer).filter(
        Customer.user_id == user_id,
        Customer.phone == phone,
        Customer.is_active == True
    ).first()
    
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    return customer

@router.get("/search/by-name")
def search_by_name(
    name: str = Query(...),
    user_id: int = Depends(check_current_user),
    db: Session = Depends(get_db)
):
    """Search customers by name (partial match) — active customers only"""
    customers = db.query(Customer).filter(
        Customer.user_id == user_id,
        Customer.customer_name.ilike(f"%{name}%"),
        Customer.is_active == True
    ).all()
    
    return {
        "search_term": name,
        "results": customers,
        "count": len(customers)
    }
