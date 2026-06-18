"""
Inventory Management Router
CRUD operations for Products, Stock Movements, Batches
Low stock alerts, inventory analytics
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Form
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, desc
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
from typing import List, Optional
from db import sessionLocal, get_db
from security import get_current_user as check_current_user
from models import Product, StockMovement, ProductBatch, Notification

router = APIRouter(prefix="/api/inventory", tags=["inventory"])

# ==================== PYDANTIC MODELS ====================

class ProductCreate(BaseModel):
    product_name: str
    sku: str
    description: Optional[str] = None
    current_stock: int = 0
    min_stock: int = 10
    max_stock: int = 100
    reorder_level: int = 20
    unit_price: float
    category: Optional[str] = None

class ProductUpdate(BaseModel):
    product_name: Optional[str] = None
    description: Optional[str] = None
    min_stock: Optional[int] = None
    max_stock: Optional[int] = None
    reorder_level: Optional[int] = None
    unit_price: Optional[float] = None
    category: Optional[str] = None

class StockMovementCreate(BaseModel):
    product_id: int
    movement_type: str  # "IN", "OUT", "ADJUSTMENT"
    quantity: int
    reason: Optional[str] = None
    reference_id: Optional[str] = None

class ProductBatchCreate(BaseModel):
    product_id: int
    batch_number: str
    manufacture_date: Optional[str] = None
    expiry_date: Optional[str] = None
    quantity: int

class ProductResponse(BaseModel):
    id: int
    product_name: str
    sku: str
    current_stock: int
    min_stock: int
    max_stock: int
    unit_price: float
    category: Optional[str]

    class Config:
        from_attributes = True

# ==================== PRODUCTS ====================

@router.post("/products", response_model=ProductResponse)
def create_product(
    product: ProductCreate,
    user_id: int = Depends(check_current_user),
    db: Session = Depends(get_db)
):
    """Create a new product"""
    # Scoped uniqueness per user (not global)
    existing = db.query(Product).filter(
        Product.user_id == user_id,
        Product.sku == product.sku,
        Product.is_active == True
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="SKU already exists for this account")
    
    db_product = Product(
        user_id=user_id,
        **product.dict()
    )
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product

@router.get("/products", response_model=List[ProductResponse])
def get_products(
    user_id: int = Depends(check_current_user),
    category: Optional[str] = None,
    skip: int = Query(0),
    limit: int = Query(100),
    db: Session = Depends(get_db)
):
    """Get all products with optional filtering — only active (non-deleted) products"""
    query = db.query(Product).filter(
        Product.user_id == user_id,
        Product.is_active == True  # Soft-delete filter
    )
    
    if category:
        query = query.filter(Product.category == category)
    
    return query.offset(skip).limit(limit).all()

@router.get("/products/{product_id}", response_model=ProductResponse)
def get_product(
    product_id: int,
    user_id: int = Depends(check_current_user),
    db: Session = Depends(get_db)
):
    """Get product details — account-scoped"""
    product = db.query(Product).filter(
        Product.id == product_id,
        Product.user_id == user_id
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product

@router.put("/products/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: int,
    product_update: ProductUpdate,
    user_id: int = Depends(check_current_user),
    db: Session = Depends(get_db)
):
    """Update product — account-scoped"""
    db_product = db.query(Product).filter(
        Product.id == product_id,
        Product.user_id == user_id
    ).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    update_data = product_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_product, field, value)
    
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product

@router.delete("/products/{product_id}")
def delete_product(
    product_id: int,
    user_id: int = Depends(check_current_user),
    db: Session = Depends(get_db)
):
    """Soft-delete product — marks inactive, all historical invoices remain intact"""
    db_product = db.query(Product).filter(
        Product.id == product_id,
        Product.user_id == user_id
    ).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    db_product.is_active = False  # Soft delete — preserves all invoice line item history
    db.commit()
    return {"message": f"Product '{db_product.product_name}' archived. All invoice history preserved."}

# ==================== STOCK MANAGEMENT ====================

@router.post("/stock-movement", response_model=dict)
def create_stock_movement(
    movement: StockMovementCreate,
    db: Session = Depends(get_db)
):
    """Record stock movement (IN/OUT/ADJUSTMENT)"""
    product = db.query(Product).filter(Product.id == movement.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Update product stock
    if movement.movement_type == "IN":
        product.current_stock += movement.quantity
    elif movement.movement_type == "OUT":
        if product.current_stock < movement.quantity:
            raise HTTPException(status_code=400, detail="Insufficient stock")
        product.current_stock -= movement.quantity
    elif movement.movement_type == "ADJUSTMENT":
        product.current_stock = movement.quantity
    
    # Create stock movement record
    db_movement = StockMovement(**movement.dict())
    db.add(db_movement)
    
    # Check if stock is below minimum
    if product.current_stock <= product.min_stock:
        notification = Notification(
            notification_type="LOW_STOCK",
            channel="EMAIL",
            recipient=f"admin@store.com",
            message=f"Product {product.product_name} (SKU: {product.sku}) is below minimum stock level. Current: {product.current_stock}, Minimum: {product.min_stock}",
            status="PENDING"
        )
        db.add(notification)
    
    db.add(product)
    db.commit()
    
    return {
        "message": "Stock movement recorded",
        "product_id": movement.product_id,
        "current_stock": product.current_stock,
        "movement_type": movement.movement_type
    }

@router.get("/stock-movements/{product_id}")
def get_stock_movements(
    product_id: int,
    days: int = Query(30),
    db: Session = Depends(get_db)
):
    """Get stock movement history"""
    cutoff_date = datetime.now() - timedelta(days=days)
    
    movements = db.query(StockMovement).filter(
        and_(
            StockMovement.product_id == product_id,
            StockMovement.created_at >= cutoff_date
        )
    ).order_by(desc(StockMovement.created_at)).all()
    
    return {
        "product_id": product_id,
        "movements": movements,
        "total_movements": len(movements)
    }

@router.get("/low-stock")
def get_low_stock_products(
    user_id: int = Depends(check_current_user),
    db: Session = Depends(get_db)
):
    """Get all products below minimum stock"""
    low_stock = db.query(Product).filter(
        and_(
            Product.user_id == user_id,
            Product.current_stock <= Product.min_stock
        )
    ).all()
    
    return {
        "low_stock_products": low_stock,
        "count": len(low_stock)
    }

@router.get("/stock-alerts")
def get_stock_alerts(
    user_id: int = Depends(check_current_user),
    db: Session = Depends(get_db)
):
    """Get detailed stock alerts and recommendations"""
    products = db.query(Product).filter(Product.user_id == user_id).all()
    
    alerts = []
    for product in products:
        if product.current_stock <= product.min_stock:
            alerts.append({
                "product_id": product.id,
                "product_name": product.product_name,
                "sku": product.sku,
                "current_stock": product.current_stock,
                "min_stock": product.min_stock,
                "reorder_quantity": max(product.max_stock - product.current_stock, product.reorder_level),
                "status": "CRITICAL" if product.current_stock == 0 else "LOW"
            })
    
    return {
        "alerts": alerts,
        "total_alerts": len(alerts)
    }

# ==================== PRODUCT BATCHES ====================

@router.post("/batches")
def create_batch(
    batch: ProductBatchCreate,
    db: Session = Depends(get_db)
):
    """Create product batch (for expiry tracking)"""
    product = db.query(Product).filter(Product.id == batch.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    db_batch = ProductBatch(**batch.dict())
    db.add(db_batch)
    db.commit()
    db.refresh(db_batch)
    
    return db_batch

@router.get("/batches/{product_id}")
def get_batches(
    product_id: int,
    db: Session = Depends(get_db)
):
    """Get all batches for a product"""
    batches = db.query(ProductBatch).filter(ProductBatch.product_id == product_id).all()
    return batches

@router.get("/expiring-batches")
def get_expiring_batches(
    user_id: int = Query(...),
    days: int = Query(30),
    db: Session = Depends(get_db)
):
    """Get batches expiring within specified days"""
    cutoff_date = datetime.now() + timedelta(days=days)
    
    expiring = db.query(ProductBatch).join(Product).filter(
        and_(
            Product.user_id == user_id,
            ProductBatch.expiry_date <= cutoff_date,
            ProductBatch.expiry_date >= datetime.now()
        )
    ).all()
    
    return {
        "expiring_batches": expiring,
        "count": len(expiring)
    }

# ==================== INVENTORY ANALYTICS ====================

@router.get("/analytics/stock-value")
def get_stock_value(
    user_id: int = Query(...),
    db: Session = Depends(get_db)
):
    """Get total stock value"""
    products = db.query(Product).filter(Product.user_id == user_id).all()
    
    total_value = sum(float(p.current_stock * p.unit_price) for p in products)
    
    return {
        "total_stock_value": total_value,
        "total_items": sum(p.current_stock for p in products),
        "total_products": len(products)
    }

@router.get("/analytics/inventory-status")
def get_inventory_status(
    user_id: int = Query(...),
    db: Session = Depends(get_db)
):
    """Get complete inventory status summary"""
    products = db.query(Product).filter(Product.user_id == user_id).all()
    
    low_stock = sum(1 for p in products if p.current_stock <= p.min_stock)
    critical_stock = sum(1 for p in products if p.current_stock == 0)
    optimal_stock = sum(1 for p in products if p.min_stock < p.current_stock <= p.max_stock)
    overstocked = sum(1 for p in products if p.current_stock > p.max_stock)
    
    return {
        "total_products": len(products),
        "low_stock": low_stock,
        "critical_stock": critical_stock,
        "optimal_stock": optimal_stock,
        "overstocked": overstocked,
        "total_items_in_stock": sum(p.current_stock for p in products),
        "total_stock_value": sum(float(p.current_stock * p.unit_price) for p in products)
    }
