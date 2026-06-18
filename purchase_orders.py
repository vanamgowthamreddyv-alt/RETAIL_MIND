"""
📦 PURCHASE ORDERS API — AI Shop Pro Enterprise Backend
Covers:
  - Create purchase orders to wholesalers
  - Mark order as delivered (auto-adds stock to inventory)
  - List all POs with status
  - Cancel PO
  - Auto-write to UniversalTransaction journal on delivery
"""

from typing import Optional, List
from datetime import date, datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db import get_db
from models import PurchaseOrder, Product, StockMovement, UniversalTransaction
from security import owner_only, sanitize_input
import json

router = APIRouter(prefix="/purchase-orders", tags=["Purchase Orders"])

# =====================
# SCHEMAS
# =====================
class POItem(BaseModel):
    product_id: Optional[int] = None
    product_name: str
    quantity: int = Field(..., gt=0)
    unit_cost: float = Field(..., ge=0)

class PurchaseOrderCreate(BaseModel):
    supplier_name: str = Field(..., min_length=2, max_length=100)
    expected_delivery: Optional[date] = None
    items: List[POItem] = Field(..., min_length=1)
    notes: Optional[str] = None

class PurchaseOrderResponse(BaseModel):
    id: int
    supplier_name: str
    status: str
    total_cost: float
    expected_delivery: Optional[date]
    items_json: str
    created_at: datetime

    class Config:
        from_attributes = True

# =====================
# ENDPOINTS
# =====================

@router.post("/", response_model=PurchaseOrderResponse)
def create_purchase_order(
    data: PurchaseOrderCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(owner_only),
):
    """Create a new purchase order to a supplier"""
    shop_id = current_user["user_id"]
    supplier_name = sanitize_input(data.supplier_name, "supplier_name")

    items_data = [item.model_dump() for item in data.items]
    total_cost = sum(item["quantity"] * item["unit_cost"] for item in items_data)

    po = PurchaseOrder(
        shop_id=shop_id,
        supplier_name=supplier_name,
        status="DRAFT",
        total_cost=total_cost,
        items_json=json.dumps(items_data),
        expected_delivery=data.expected_delivery,
    )
    db.add(po)
    db.commit()
    db.refresh(po)
    return po


@router.get("/", response_model=List[PurchaseOrderResponse])
def list_purchase_orders(
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current_user: dict = Depends(owner_only),
):
    """List all purchase orders for this shop"""
    shop_id = current_user["user_id"]
    q = db.query(PurchaseOrder).filter(PurchaseOrder.shop_id == shop_id)
    if status:
        q = q.filter(PurchaseOrder.status == status.upper())
    orders = q.order_by(PurchaseOrder.created_at.desc()).offset(skip).limit(limit).all()
    return orders


@router.post("/{po_id}/mark-delivered")
def mark_po_delivered(
    po_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(owner_only),
):
    """
    Mark a PO as delivered.
    This AUTOMATICALLY adds received stock quantities to inventory.
    """
    shop_id = current_user["user_id"]
    po = db.query(PurchaseOrder).filter(
        PurchaseOrder.id == po_id,
        PurchaseOrder.shop_id == shop_id,
    ).first()

    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found.")
    if po.status == "DELIVERED":
        raise HTTPException(status_code=409, detail="This PO is already marked as delivered.")
    if po.status == "CANCELLED":
        raise HTTPException(status_code=409, detail="Cannot deliver a cancelled PO.")

    items = json.loads(po.items_json)
    stock_updates = []

    for item in items:
        if item.get("product_id"):
            product = db.query(Product).filter(
                Product.id == item["product_id"],
                Product.user_id == shop_id,
            ).first()
            if product:
                product.current_stock = (product.current_stock or 0) + item["quantity"]
                # Log stock movement
                movement = StockMovement(
                    product_id=product.id,
                    movement_type="IN",
                    quantity=item["quantity"],
                    reason="Purchase Order Delivery",
                    reference_id=f"PO-{po.id}",
                )
                db.add(movement)
                stock_updates.append({
                    "product_name": product.product_name,
                    "qty_added": item["quantity"],
                    "new_stock": product.current_stock,
                })

    po.status = "DELIVERED"

    # Write to universal transaction journal
    tx = UniversalTransaction(
        shop_id=shop_id,
        tx_type="EXPENSE",
        category="PO_PAYMENT",
        amount=float(po.total_cost),
        reference_id=f"PO-{po.id}",
        description=f"Purchase Order from {po.supplier_name}",
    )
    db.add(tx)
    db.commit()

    return {
        "message": f"PO #{po.id} marked as delivered. Stock updated.",
        "stock_updates": stock_updates,
        "total_cost": float(po.total_cost),
    }


@router.post("/{po_id}/cancel")
def cancel_purchase_order(
    po_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(owner_only),
):
    """Cancel a purchase order"""
    shop_id = current_user["user_id"]
    po = db.query(PurchaseOrder).filter(
        PurchaseOrder.id == po_id,
        PurchaseOrder.shop_id == shop_id,
    ).first()

    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found.")
    if po.status == "DELIVERED":
        raise HTTPException(status_code=409, detail="Cannot cancel a delivered PO.")

    po.status = "CANCELLED"
    db.commit()
    return {"message": f"Purchase order #{po_id} has been cancelled."}
