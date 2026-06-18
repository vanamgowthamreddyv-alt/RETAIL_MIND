"""
🏪 ONLINE STORE API — AI Shop Pro Enterprise Backend
Covers:
  - Customer Registration & Login (separate from Owner)
  - Discover nearby shops (by city/area or GPS coords)
  - Browse shop inventory 
  - Place an order
  - Track order status in real-time
  - Owner dashboard: view/accept/reject/dispatch orders
"""

import math
import json
import logging
from typing import Optional, List
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session
from sqlalchemy import func

from db import get_db
from models import User, ShopProfile, Product, OnlineOrder, Invoice, InvoiceLineItem, UniversalTransaction
from security import (
    hash_password, verify_password, create_access_token,
    ROLE_CUSTOMER, ROLE_OWNER,
    check_login_lockout, record_login_failure, record_login_success,
    owner_only, customer_only, get_current_user, sanitize_input
)
from email_notifications import EmailNotificationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/store", tags=["Online Store"])

# =====================
# CUSTOMER AUTH SCHEMAS
# =====================
class CustomerRegister(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    phone: str = Field(..., min_length=10, max_length=10, pattern=r"^\d{10}$")
    password: str = Field(..., min_length=6)
    city: Optional[str] = None
    address: Optional[str] = None

class CustomerLogin(BaseModel):
    email: EmailStr
    password: str

class OrderItem(BaseModel):
    product_id: int
    quantity: int = Field(..., gt=0)

class PlaceOrder(BaseModel):
    shop_id: int
    items: List[OrderItem] = Field(..., min_length=1)
    delivery_address: str = Field(..., min_length=5)

# =====================
# CUSTOMER AUTH
# =====================
@router.post("/customer/register")
def register_customer(
    data: CustomerRegister,
    request: Request,
    db: Session = Depends(get_db),
):
    """Register a new customer account"""
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered.")

    name = sanitize_input(data.name, "name")
    customer = User(
        user_name=name,
        email=data.email,
        password=hash_password(data.password),
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)

    # Send Welcome Email with Credentials
    try:
        subject, body = EmailNotificationService.welcome_credentials_template(data.name, data.password, "Customer")
        EmailNotificationService.create_notification(
            db=db,
            recipient_email=data.email,
            subject=subject,
            body=body,
            event_type="WELCOME"
        )
    except Exception as e:
        logger.error(f"Failed to send welcome email to customer: {e}")

    token = create_access_token({"sub": str(customer.id), "role": ROLE_CUSTOMER})
    return {
        "message": "Customer account created successfully.",
        "access_token": token,
        "token_type": "bearer",
        "customer_id": customer.id,
        "name": customer.user_name,
    }


@router.post("/customer/login")
def customer_login(
    data: CustomerLogin,
    request: Request,
    db: Session = Depends(get_db),
):
    """Customer login — returns JWT with CUSTOMER role"""
    ip = request.client.host
    check_login_lockout(ip)

    user = db.query(User).filter(User.email == data.email).first()
    if not user or not verify_password(data.password, user.password):
        record_login_failure(ip)
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    record_login_success(ip)
    token = create_access_token({"sub": str(user.id), "role": ROLE_CUSTOMER})
    return {
        "access_token": token,
        "token_type": "bearer",
        "customer_id": user.id,
        "name": user.user_name,
    }


# =====================
# SHOP DISCOVERY
# =====================
@router.get("/shops/nearby")
def find_nearby_shops(
    city: Optional[str] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    radius_km: float = 5.0,
    skip: int = 0,
    limit: int = Query(20, le=100),
    db: Session = Depends(get_db),
):
    """
    Find shops near a location.
    Supports two modes:
    1. ?city=Mumbai — simple string matching
    2. ?lat=19.0&lng=72.8&radius_km=5 — GPS radius (Haversine formula)
    Only returns shops with is_online_store_enabled=True
    """
    query = db.query(ShopProfile).filter(ShopProfile.is_online_store_enabled == True)

    if city:
        city_clean = sanitize_input(city, "city")
        query = query.filter(ShopProfile.address.ilike(f"%{city_clean}%"))

    all_shops = query.all()

    if lat is not None and lng is not None:
        # Filter by Haversine distance
        def haversine(lat1, lon1, lat2_str, lon2_str):
            """Calculate distance in km between two lat/lng points"""
            try:
                # We store location as "lat,lng" in address if GPS mode used
                parts = str(lat2_str).split(",")
                if len(parts) != 2:
                    return float("inf")
                lat2, lon2 = float(parts[0]), float(parts[1])
            except Exception:
                return float("inf")
            R = 6371  # Earth radius in km
            dlat = math.radians(lat2 - lat1)
            dlon = math.radians(lon2 - lon1)
            a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
            return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

        all_shops = [s for s in all_shops if haversine(lat, lng, s.address, s.address) <= radius_km]

    all_shops = all_shops[skip:skip + limit]

    return {
        "shops": [
            {
                "shop_id": s.shop_id,
                "shop_name": s.shop_name,
                "address": s.address,
                "phone": s.phone,
                "logo_url": s.logo_url,
            }
            for s in all_shops
        ],
        "count": len(all_shops),
    }


@router.get("/shops/{shop_id}/products")
def browse_shop_products(
    shop_id: int,
    category: Optional[str] = None,
    skip: int = 0,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    """Browse a shop's available inventory (only active, in-stock products)"""
    # Verify shop exists and has online store enabled
    profile = db.query(ShopProfile).filter(
        ShopProfile.shop_id == shop_id,
        ShopProfile.is_online_store_enabled == True,
    ).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Shop not found or online store disabled.")

    q = db.query(Product).filter(
        Product.user_id == shop_id,
        Product.is_active == True,
        Product.current_stock > 0,
    )
    if category:
        q = q.filter(Product.category == category)

    products = q.offset(skip).limit(limit).all()

    return {
        "shop_name": profile.shop_name,
        "products": [
            {
                "id": p.id,
                "name": p.product_name,
                "category": p.category,
                "price": float(p.unit_price),
                "stock_available": p.current_stock,
                "description": p.description,
            }
            for p in products
        ],
    }


# =====================
# ORDER PLACEMENT
# =====================
@router.post("/order")
def place_order(
    data: PlaceOrder,
    db: Session = Depends(get_db),
    current_user: dict = Depends(customer_only),
):
    """Place an online order at a specific shop"""
    customer_id = current_user["user_id"]

    # Validate shop
    profile = db.query(ShopProfile).filter(
        ShopProfile.shop_id == data.shop_id,
        ShopProfile.is_online_store_enabled == True,
    ).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Shop not found or not accepting online orders.")

    # Validate all items and calculate total
    order_items = []
    total_amount = 0.0

    for item in data.items:
        product = db.query(Product).filter(
            Product.id == item.product_id,
            Product.user_id == data.shop_id,
            Product.is_active == True,
        ).first()
        if not product:
            raise HTTPException(status_code=404, detail=f"Product ID {item.product_id} not found in this shop.")
        if product.current_stock < item.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock for '{product.product_name}'. Available: {product.current_stock}"
            )
        line_total = float(product.unit_price) * item.quantity
        total_amount += line_total
        order_items.append({
            "product_id": product.id,
            "product_name": product.product_name,
            "quantity": item.quantity,
            "unit_price": float(product.unit_price),
            "line_total": line_total,
        })

    delivery_address = sanitize_input(data.delivery_address, "delivery_address")

    order = OnlineOrder(
        shop_id=data.shop_id,
        customer_id=customer_id,
        total_amount=total_amount,
        delivery_address=delivery_address,
        items_json=json.dumps(order_items),
        order_status="PENDING",
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    return {
        "message": "Order placed successfully! The shop will confirm shortly.",
        "order_id": order.id,
        "shop_name": profile.shop_name,
        "total_amount": total_amount,
        "items": order_items,
        "status": "PENDING",
    }


@router.get("/my-orders")
def get_my_orders(
    db: Session = Depends(get_db),
    current_user: dict = Depends(customer_only),
):
    """Customer: View all their orders"""
    customer_id = current_user["user_id"]
    orders = db.query(OnlineOrder).filter(
        OnlineOrder.customer_id == customer_id
    ).order_by(OnlineOrder.created_at.desc()).all()

    return {
        "orders": [
            {
                "order_id": o.id,
                "shop_id": o.shop_id,
                "status": o.order_status,
                "total_amount": float(o.total_amount),
                "delivery_address": o.delivery_address,
                "items": json.loads(o.items_json),
                "created_at": o.created_at,
                "updated_at": o.updated_at,
            }
            for o in orders
        ]
    }


@router.get("/order/{order_id}/track")
def track_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Track a specific order by ID"""
    order = db.query(OnlineOrder).filter(OnlineOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")

    # Security: only the customer who placed the order or the shop owner can view it
    uid = current_user["user_id"]
    if order.customer_id != uid and order.shop_id != uid:
        raise HTTPException(status_code=403, detail="You do not have access to this order.")

    STATUS_STEPS = ["PENDING", "ACCEPTED", "DISPATCHED", "DELIVERED"]
    current_step = STATUS_STEPS.index(order.order_status) if order.order_status in STATUS_STEPS else 0

    return {
        "order_id": order.id,
        "status": order.order_status,
        "progress_step": current_step + 1,
        "total_steps": len(STATUS_STEPS),
        "total_amount": float(order.total_amount),
        "delivery_address": order.delivery_address,
        "items": json.loads(order.items_json),
        "created_at": order.created_at,
        "updated_at": order.updated_at,
    }


# =====================
# OWNER ORDER MANAGEMENT
# =====================
@router.get("/owner/orders")
def get_incoming_orders(
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current_user: dict = Depends(owner_only),
):
    """Owner: View all incoming online orders for their shop"""
    shop_id = current_user["user_id"]
    q = db.query(OnlineOrder).filter(OnlineOrder.shop_id == shop_id)
    if status:
        q = q.filter(OnlineOrder.order_status == status.upper())
    orders = q.order_by(OnlineOrder.created_at.desc()).offset(skip).limit(limit).all()

    return {
        "orders": [
            {
                "order_id": o.id,
                "customer_id": o.customer_id,
                "status": o.order_status,
                "total_amount": float(o.total_amount),
                "delivery_address": o.delivery_address,
                "items": json.loads(o.items_json),
                "created_at": o.created_at,
            }
            for o in orders
        ],
        "total": len(orders),
    }


@router.post("/owner/orders/{order_id}/action")
def update_order_status(
    order_id: int,
    action: str = Query(..., description="ACCEPT, DISPATCH, DELIVER, REJECT"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(owner_only),
):
    """Owner: Accept, Dispatch, Deliver, or Reject an order"""
    shop_id = current_user["user_id"]
    order = db.query(OnlineOrder).filter(
        OnlineOrder.id == order_id,
        OnlineOrder.shop_id == shop_id,
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")

    ACTION_MAP = {
        "ACCEPT": "ACCEPTED",
        "DISPATCH": "DISPATCHED",
        "DELIVER": "DELIVERED",
        "REJECT": "REJECTED",
    }
    new_status = ACTION_MAP.get(action.upper())
    if not new_status:
        raise HTTPException(status_code=400, detail=f"Invalid action. Choose from: {list(ACTION_MAP.keys())}")

    if order.order_status in ("DELIVERED", "REJECTED"):
        raise HTTPException(status_code=409, detail="Order is already finalized.")

    # If delivered, deduct stock and create official invoice
    if new_status == "DELIVERED":
        items = json.loads(order.items_json)
        
        # Get customer details
        customer = db.query(User).filter(User.id == order.customer_id).first()
        customer_name = customer.user_name if customer else "Online Customer"
        
        # Create Invoice
        invoice = Invoice(
            user_id=shop_id,
            customer_name=customer_name,
            invoice_number=f"ONL-{order.id}-{int(datetime.now().timestamp())}",
            invoice_date=date.today(),
            due_date=date.today(),
            subtotal=float(order.total_amount), # Assuming no tax for MVP
            tax=0,
            total_amount=float(order.total_amount),
            paid_amount=float(order.total_amount),
            status="SENT",
            payment_status="PAID",
            source="ONLINE_ORDER",
            notes=f"Online Order Delivery to: {order.delivery_address}"
        )
        db.add(invoice)
        db.flush()

        for item in items:
            if item.get("product_id"):
                product = db.query(Product).filter(
                    Product.id == item["product_id"],
                    Product.user_id == shop_id,
                ).first()
                if product:
                    product.current_stock = max(0, (product.current_stock or 0) - item["quantity"])
            
            # Create InvoiceLineItem
            db_line = InvoiceLineItem(
                invoice_id=invoice.id,
                product_id=item.get("product_id"),
                description=item.get("product_name", "Item"),
                quantity=item.get("quantity", 1),
                unit_price=item.get("unit_price", item.get("line_total", 0) / max(1, item.get("quantity", 1))),
                line_total=item.get("line_total", 0),
            )
            db.add(db_line)
            
        # Write to universal journal
        tx = UniversalTransaction(
            shop_id=shop_id,
            tx_type="INCOME",
            category="SALE",
            amount=float(order.total_amount),
            reference_id=f"ONL-{order.id}",
            description=f"Online Order Delivered: #{order.id}",
            tx_date=datetime.now(),
        )
        db.add(tx)

    order.order_status = new_status
    db.commit()

    return {
        "message": f"Order #{order_id} status updated to {new_status}.",
        "order_id": order_id,
        "new_status": new_status,
    }
