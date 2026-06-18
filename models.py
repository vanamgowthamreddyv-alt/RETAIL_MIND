"""
Enhanced Database Models for Hybrid Search RAG
Includes: Inventory, Attendance, Invoices, Payments, Customers, Notifications, Stock Management
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Text, Numeric, Date, Enum, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime, date
import enum
from db import Base


# ==================== EXISTING MODELS ====================

class User(Base):
    __tablename__ = "user_details"
    
    id = Column(Integer, primary_key=True, nullable=False)
    user_name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    password = Column(String(100), nullable=False)
    
    # Relationships
    products = relationship("Product", back_populates="owner")
    sales = relationship("sales", back_populates="shopkeeper")
    attendance = relationship("Attendance", back_populates="employee")
    invoices = relationship("Invoice", back_populates="user")
    customers = relationship("Customer", back_populates="user")


class sales(Base):
    __tablename__ = "sales"
    
    id = Column(Integer, primary_key=True)
    shopkeeper_id = Column(Integer, ForeignKey("user_details.id", ondelete="CASCADE"), nullable=False, index=True)
    product_name = Column(String(100), nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    quantity = Column(Integer, nullable=False)
    total = Column(Numeric(10, 2), nullable=False)
    sale_date = Column(Date, index=True)
    
    # Relationship
    shopkeeper = relationship("User", back_populates="sales")


# ==================== NEW MODELS ====================

# ========== INVENTORY MANAGEMENT ==========

class Product(Base):
    __tablename__ = "products"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_details.id", ondelete="CASCADE"), nullable=False, index=True)
    product_name = Column(String(100), nullable=False)
    sku = Column(String(50), nullable=False)
    description = Column(Text)
    current_stock = Column(Integer, default=0)
    min_stock = Column(Integer, default=10)  # Alert when below this
    max_stock = Column(Integer, default=100)
    reorder_level = Column(Integer, default=20)
    unit_price = Column(Numeric(10, 2), nullable=False)
    purchase_price = Column(Numeric(10, 2), default=0)  # For margin calculation (Feature 15)
    category = Column(String(50), index=True)
    is_active = Column(Boolean, default=True)  # Soft-delete: False = deleted from catalogue
    
    __table_args__ = (UniqueConstraint('user_id', 'sku', name='uix_user_sku'),)
    
    # Relationships
    owner = relationship("User", back_populates="products")
    stock_movements = relationship("StockMovement", back_populates="product")
    batches = relationship("ProductBatch", back_populates="product")
    line_items = relationship("InvoiceLineItem", back_populates="product")


class StockMovement(Base):
    __tablename__ = "stock_movements"
    
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    movement_type = Column(Enum("IN", "OUT", "ADJUSTMENT", name="movement_type"), nullable=False)
    quantity = Column(Integer, nullable=False)
    reason = Column(String(200))  # e.g., "Purchase", "Sale", "Damage", "Inventory Adjustment"
    reference_id = Column(String(100))  # e.g., invoice_id, purchase_order_id
    
    # Relationship
    product = relationship("Product", back_populates="stock_movements")


class ProductBatch(Base):
    __tablename__ = "product_batches"
    
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    batch_number = Column(String(100), unique=True)
    manufacture_date = Column(Date)
    expiry_date = Column(Date)
    quantity = Column(Integer)
    
    # Relationship
    product = relationship("Product", back_populates="batches")


# ========== ATTENDANCE MANAGEMENT ==========

class Attendance(Base):
    __tablename__ = "attendance"
    
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("user_details.id", ondelete="CASCADE"), nullable=False)
    attendance_date = Column(Date, nullable=False)
    check_in_time = Column(DateTime)
    check_out_time = Column(DateTime)
    status = Column(Enum("PRESENT", "ABSENT", "LEAVE", "HALF_DAY", "LATE", name="attendance_status"), default="ABSENT")
    working_hours = Column(Float, default=0.0)  # Calculated automatically
    notes = Column(Text)
    
    # Relationship
    employee = relationship("User", back_populates="attendance")


class LeaveRequest(Base):
    __tablename__ = "leave_requests"
    
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("user_details.id", ondelete="CASCADE"), nullable=False)
    leave_type = Column(Enum("VACATION", "SICK", "PERSONAL", name="leave_type"), nullable=False)
    from_date = Column(Date, nullable=False)
    to_date = Column(Date, nullable=False)
    reason = Column(Text)
    status = Column(Enum("PENDING", "APPROVED", "REJECTED", name="leave_status"), default="PENDING")


# ========== CUSTOMER MANAGEMENT ==========

class Customer(Base):
    __tablename__ = "customers"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_details.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_name = Column(String(100), nullable=False)
    email = Column(String(100))
    phone = Column(String(20), nullable=False, index=True)
    whatsapp_number = Column(String(20))  # For WhatsApp notifications
    address = Column(Text)
    city = Column(String(50))
    credit_limit = Column(Numeric(10, 2), default=0)
    payment_terms = Column(String(50))  # e.g., "Net 30", "COD"
    contact_preference = Column(Enum("EMAIL", "WHATSAPP", "CALL", "SMS", name="contact_preference"), default="EMAIL")
    is_active = Column(Boolean, default=True)  # Soft-delete: False = customer archived
    
    # Relationship
    user = relationship("User", back_populates="customers")
    invoices = relationship("Invoice", back_populates="customer")


# ========== INVOICE & PAYMENT MANAGEMENT ==========

class Invoice(Base):
    __tablename__ = "invoices"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_details.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=True)
    customer_name = Column(String(100), nullable=True)
    customer_phone = Column(String(20), nullable=True)
    invoice_number = Column(String(50), nullable=False, index=True)
    invoice_date = Column(Date, server_default=func.now(), index=True)
    due_date = Column(Date, nullable=False)
    subtotal = Column(Numeric(10, 2), default=0)
    tax = Column(Numeric(10, 2), default=0)
    total_amount = Column(Numeric(10, 2), nullable=False)
    paid_amount = Column(Numeric(10, 2), default=0)
    status = Column(Enum("DRAFT", "SENT", "PAID", "OVERDUE", "PARTIAL", "CANCELLED", name="invoice_status"), default="DRAFT")
    payment_status = Column(Enum("UNPAID", "PARTIAL", "PAID", "OVERDUE", name="payment_status"), default="UNPAID", index=True)
    source = Column(String(50), default="MANUAL_ENTRY") # OFFLINE_SYNC, ONLINE_ORDER, MANUAL_ENTRY
    notes = Column(Text)
    
    __table_args__ = (UniqueConstraint('user_id', 'invoice_number', name='uix_user_invoice_number'),)
    
    # Relationships
    user = relationship("User", back_populates="invoices")
    customer = relationship("Customer", back_populates="invoices")
    line_items = relationship("InvoiceLineItem", back_populates="invoice")
    payments = relationship("Payment", back_populates="invoice")


class InvoiceLineItem(Base):
    __tablename__ = "invoice_line_items"
    
    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"))
    description = Column(String(255))
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)
    line_total = Column(Numeric(10, 2), nullable=False)
    
    # Relationships
    invoice = relationship("Invoice", back_populates="line_items")
    product = relationship("Product", back_populates="line_items")


class Payment(Base):
    __tablename__ = "payments"
    
    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False)
    payment_method = Column(Enum("CASH", "CARD", "TRANSFER", "CHEQUE", "ONLINE", name="payment_method"), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    payment_date = Column(DateTime, server_default=func.now())
    reference_number = Column(String(100))  # Transaction ID, check number, etc.
    notes = Column(Text)
    
    # Relationship
    invoice = relationship("Invoice", back_populates="payments")


# ========== NOTIFICATION & ESCALATION ==========

class Notification(Base):
    __tablename__ = "notifications"
    
    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"))
    notification_type = Column(Enum("PAYMENT_REMINDER", "INVOICE_SENT", "PAYMENT_RECEIVED", "OVERDUE_ALERT", "LOW_STOCK", name="notification_type"), nullable=False)
    channel = Column(Enum("EMAIL", "WHATSAPP", "SMS", "CALL", name="notification_channel"), nullable=False)
    recipient = Column(String(255), nullable=False)  # Email, phone, or contact number
    message = Column(Text)
    status = Column(Enum("PENDING", "SENT", "FAILED", name="notification_status"), default="PENDING")
    attempted_at = Column(DateTime)
    sent_at = Column(DateTime)
    error_message = Column(Text)
    
    # Relationship
    invoice = relationship("Invoice")


class AgentEscalation(Base):
    __tablename__ = "agent_escalations"
    
    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False)
    agent_id = Column(Integer, ForeignKey("user_details.id", ondelete="SET NULL"))
    escalation_reason = Column(String(200))  # e.g., "PAYMENT_OVERDUE_7_DAYS", "MULTIPLE_REMINDERS_IGNORED"
    escalation_level = Column(Integer, default=1)  # 1, 2, 3 (increasing severity)
    priority = Column(Enum("LOW", "MEDIUM", "HIGH", "CRITICAL", name="priority"), default="MEDIUM")
    status = Column(Enum("PENDING", "IN_PROGRESS", "RESOLVED", "FAILED", name="escalation_status"), default="PENDING")
    call_initiated = Column(Boolean, default=False)
    call_timestamp = Column(DateTime)
    call_duration = Column(Integer)  # in seconds
    call_status = Column(Enum("NOT_CALLED", "RINGING", "ANSWERED", "DECLINED", "FAILED", name="call_status"), default="NOT_CALLED")
    notes = Column(Text)
    resolution_date = Column(DateTime)


class PasswordReset(Base):
    __tablename__ = "password_resets"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_details.id", ondelete="CASCADE"), nullable=False)
    reset_token = Column(String(255), unique=True, nullable=False)
    token_expiry = Column(DateTime, nullable=False)
    is_used = Column(Boolean, default=False)
    used_at = Column(DateTime)


class Token(Base):
    __tablename__ = "tokens"
    
    id = Column(Integer, primary_key=True)
    token = Column(String(64), unique=True, nullable=False)
    user_id = Column(Integer, ForeignKey("user_details.id", ondelete="CASCADE"), nullable=False)


# ==================== SESSION MANAGEMENT ====================

class RefreshToken(Base):
    """7-day auto-login tokens for persistent sessions"""
    __tablename__ = "refresh_tokens"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_details.id", ondelete="CASCADE"), nullable=False)
    token = Column(String(500), unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)  # 7 days from creation
    is_valid = Column(Boolean, default=True)


class SessionToken(Base):
    """Active session tracking"""
    __tablename__ = "session_tokens"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_details.id", ondelete="CASCADE"), nullable=False)
    access_token = Column(String(500), unique=True, nullable=False)
    refresh_token_id = Column(Integer, ForeignKey("refresh_tokens.id", ondelete="CASCADE"))
    device_id = Column(String(200))  # For multi-device tracking
    is_active = Column(Boolean, default=True)
    last_activity = Column(DateTime, server_default=func.now(), onupdate=func.now())


class OfflineDataQueue(Base):
    """Queue offline sales/transactions until sync"""
    __tablename__ = "offline_data_queue"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_details.id", ondelete="CASCADE"), nullable=False)
    data_type = Column(String(50))  # "sale", "customer", "inventory"
    data_payload = Column(Text)  # JSON data
    synced = Column(Boolean, default=False)
    sync_timestamp = Column(DateTime)


class ShopSettings(Base):
    """
    Business configuration and preferences for a shop.
    Includes business hours, tax settings, payment preferences, and more.
    """
    __tablename__ = "shop_settings"
    
    id = Column(Integer, primary_key=True)
    shop_id = Column(Integer, ForeignKey("shop_profiles.id", ondelete="CASCADE"), unique=True, nullable=False)
    
    # Business Hours
    monday_open = Column(String(10), default="09:00")  # HH:MM format
    monday_close = Column(String(10), default="21:00")
    monday_closed = Column(Boolean, default=False)
    
    tuesday_open = Column(String(10), default="09:00")
    tuesday_close = Column(String(10), default="21:00")
    tuesday_closed = Column(Boolean, default=False)
    
    wednesday_open = Column(String(10), default="09:00")
    wednesday_close = Column(String(10), default="21:00")
    wednesday_closed = Column(Boolean, default=False)
    
    thursday_open = Column(String(10), default="09:00")
    thursday_close = Column(String(10), default="21:00")
    thursday_closed = Column(Boolean, default=False)
    
    friday_open = Column(String(10), default="09:00")
    friday_close = Column(String(10), default="21:00")
    friday_closed = Column(Boolean, default=False)
    
    saturday_open = Column(String(10), default="09:00")
    saturday_close = Column(String(10), default="21:00")
    saturday_closed = Column(Boolean, default=False)
    
    sunday_open = Column(String(10), default="09:00")
    sunday_close = Column(String(10), default="21:00")
    sunday_closed = Column(Boolean, default=True)
    
    timezone = Column(String(50), default="Asia/Kolkata")
    
    # Tax Configuration
    tax_type = Column(String(20), default="GST")  # "GST", "VAT", "FLAT_RATE"
    igst_percentage = Column(Float, default=18.0)
    sgst_percentage = Column(Float, default=9.0)
    utgst_percentage = Column(Float, default=9.0)
    flat_tax_percentage = Column(Float, default=0.0)
    
    # Payment Methods Configuration
    accept_cash = Column(Boolean, default=True)
    accept_card = Column(Boolean, default=True)
    accept_upi = Column(Boolean, default=True)
    accept_bank_transfer = Column(Boolean, default=True)
    accept_cheque = Column(Boolean, default=False)
    accept_wallet = Column(Boolean, default=False)
    
    card_payment_gateway = Column(String(50))  # "Razorpay", "PayU", "Stripe"
    upi_merchant_id = Column(String(100))
    
    # Preferences
    currency_code = Column(String(3), default="INR")
    language = Column(String(10), default="en")
    theme_mode = Column(String(20), default="light")  # "light", "dark", "auto"
    receipt_format = Column(String(20), default="detailed")  # "detailed", "minimal", "full"
    
    # Notifications & Alerts
    low_stock_alert_threshold = Column(Integer, default=10)
    send_email_on_sale = Column(Boolean, default=True)
    send_sms_on_sale = Column(Boolean, default=False)
    send_notification_on_order = Column(Boolean, default=True)
    
    # Advanced Settings
    enable_inventory_tracking = Column(Boolean, default=True)
    enable_customer_loyalty = Column(Boolean, default=True)
    enable_batch_tracking = Column(Boolean, default=True)
    enable_multi_branch = Column(Boolean, default=False)
    
    
    # Relationships
    shop_profile = relationship("ShopProfile", back_populates="shop_settings")


# ==================== FEATURE 7: CUSTOMER LOYALTY POINTS ====================

class LoyaltyTier(Base):
    """Loyalty tier definitions: Bronze, Silver, Gold"""
    __tablename__ = "loyalty_tiers"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_details.id", ondelete="CASCADE"), nullable=False)
    tier_name = Column(String(50), nullable=False)  # Bronze, Silver, Gold
    tier_level = Column(Integer, nullable=False)  # 1, 2, 3
    min_points = Column(Integer, default=0)  # Min points to reach this tier
    discount_percentage = Column(Float, default=0)  # Discount when redeeming


class CustomerLoyalty(Base):
    """Track loyalty points for customers"""
    __tablename__ = "customer_loyalty"
    
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    total_points = Column(Integer, default=0)
    points_redeemed = Column(Integer, default=0)
    available_points = Column(Integer, default=0)
    current_tier_id = Column(Integer, ForeignKey("loyalty_tiers.id"))
    tier_updated_at = Column(DateTime)
    last_tier_bump_notified = Column(Boolean, default=False)


class LoyaltyTransaction(Base):
    """Point transactions: earning and redemption"""
    __tablename__ = "loyalty_transactions"
    
    id = Column(Integer, primary_key=True)
    customer_loyalty_id = Column(Integer, ForeignKey("customer_loyalty.id", ondelete="CASCADE"), nullable=False)
    transaction_type = Column(Enum("EARN", "REDEEM", "ADJUST", "EXPIRE", name="loyalty_txn"), nullable=False)
    points = Column(Integer, nullable=False)
    reference_id = Column(String(100))  # invoice_id, sale_id
    notes = Column(Text)


# ==================== FEATURE 8: UPI COLLECTIONS DASHBOARD ====================

class UpiLedger(Base):
    """Track all UPI payments separately for reconciliation"""
    __tablename__ = "upi_ledger"
    
    id = Column(Integer, primary_key=True)
    shop_id = Column(Integer, ForeignKey("shop_profiles.id", ondelete="CASCADE"))
    invoice_id = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"))
    upi_id = Column(String(100))  # Which UPI ID received this
    amount = Column(Numeric(10, 2), nullable=False)
    upi_reference = Column(String(100), unique=True)  # Transaction ref
    customer_upi = Column(String(100))  # Payer UPI
    status = Column(Enum("PENDING", "CONFIRM", "FAILED", "REFUND", name="upi_status"), default="PENDING")
    payment_date = Column(DateTime, server_default=func.now())


# ==================== FEATURE 10: HOME DELIVERY TRACKING ====================

class Delivery(Base):
    """Home delivery orders"""
    __tablename__ = "deliveries"
    
    id = Column(Integer, primary_key=True)
    shop_id = Column(Integer, ForeignKey("shop_profiles.id", ondelete="CASCADE"))
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"))
    invoice_id = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"))
    delivery_address = Column(Text, nullable=False)
    delivery_date = Column(Date)
    delivery_time = Column(String(20))  # HH:MM format
    assigned_to = Column(String(100))  # Delivery staff name
    special_instructions = Column(Text)


class DeliveryTracking(Base):
    """Track delivery status updates"""
    __tablename__ = "delivery_tracking"
    
    id = Column(Integer, primary_key=True)
    delivery_id = Column(Integer, ForeignKey("deliveries.id", ondelete="CASCADE"), nullable=False)
    status = Column(Enum("PENDING", "OUT", "DELIVERED", "FAILED", "RETURNED", name="delivery_status"), nullable=False)
    status_timestamp = Column(DateTime, server_default=func.now())
    staff_name = Column(String(100))
    notes = Column(Text)
    location_lat = Column(Float)  # GPS coordinates
    location_lng = Column(Float)


# ==================== FEATURE 9: SAVED BILL TEMPLATES ====================

class BillingTemplate(Base):
    """Save frequently used bill structures"""
    __tablename__ = "billing_templates"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_details.id", ondelete="CASCADE"), nullable=False)
    template_name = Column(String(100), nullable=False)
    template_data = Column(Text)  # JSON: [{product_id, qty, price}, ...]
    last_used = Column(DateTime)


# ==================== FEATURE 11: MULTI-STAFF BILLING COUNTERS ====================

class BillingCounter(Base):
    """Track which staff member + counter processed the sale"""
    __tablename__ = "billing_counters"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_details.id", ondelete="CASCADE"), nullable=False)
    staff_name = Column(String(100), nullable=False)
    counter_number = Column(Integer, nullable=False)
    billing_pin = Column(String(4), nullable=False)  # 4-digit PIN
    is_active = Column(Boolean, default=True)


class SalesByCounter(Base):
    """Link sales to staff + counter"""
    __tablename__ = "sales_by_counter"
    
    id = Column(Integer, primary_key=True)
    shop_id = Column(Integer, ForeignKey("shop_profiles.id", ondelete="CASCADE"))
    counter_id = Column(Integer, ForeignKey("billing_counters.id"))
    invoice_id = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"))
    staff_name = Column(String(100))
    counter_number = Column(Integer)
    sale_date = Column(Date)
    sale_amount = Column(Numeric(10, 2))


# ==================== FEATURE 13: CUSTOMER CREDIT SCORING ====================

class CustomerCreditScore(Base):
    """Credit scoring for customers"""
    __tablename__ = "customer_credit_scores"
    
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    credit_score = Column(Integer, default=50)  # 0-100
    score_badge = Column(Enum("CAUTION", "REGULAR", "TRUSTED", name="credit_badge"), default="REGULAR")
    suggested_credit_limit = Column(Numeric(10, 2), default=0)
    
    # Scoring factors
    total_purchases = Column(Integer, default=0)
    on_time_payments = Column(Integer, default=0)
    late_payments = Column(Integer, default=0)
    days_since_last_purchase = Column(Integer, default=999)
    avg_days_to_pay = Column(Float, default=0)
    
    last_calculated = Column(DateTime)


# ==================== FEATURE 14: BIRTHDAY AUTO-DISCOUNTS ====================

class CustomerOccasion(Base):
    """Track customer birthdays and other occasions"""
    __tablename__ = "customer_occasions"
    
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    occasion_type = Column(Enum("BIRTHDAY", "ANNIVERSARY", "WEDDING", "CUSTOM", name="occasion_type"), nullable=False)
    occasion_date = Column(Date, nullable=False)  # MM-DD format for annual
    discount_percentage = Column(Float, default=10)
    last_notification_sent = Column(DateTime)


# ==================== FEATURE 16: DAILY WHATSAPP REPORT ====================

class DailyReport(Base):
    """Daily aggregated report for WhatsApp"""
    __tablename__ = "daily_reports"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_details.id", ondelete="CASCADE"), nullable=False)
    report_date = Column(Date, nullable=False)
    
    total_revenue = Column(Numeric(12, 2), default=0)
    total_expenses = Column(Numeric(12, 2), default=0)
    total_profit = Column(Numeric(12, 2), default=0)
    bill_count = Column(Integer, default=0)
    
    top_product_id = Column(Integer, ForeignKey("products.id"))
    top_product_name = Column(String(100))
    top_product_qty = Column(Integer, default=0)
    
    cash_collected = Column(Numeric(10, 2), default=0)
    upi_collected = Column(Numeric(10, 2), default=0)
    card_collected = Column(Numeric(10, 2), default=0)
    
    whatsapp_sent = Column(Boolean, default=False)
    whatsapp_sent_at = Column(DateTime)


# ==================== FEATURE 3: FESTIVAL STOCK PREDICTOR ====================

class FestivalEvent(Base):
    """Indian festival calendar with last year comparison"""
    __tablename__ = "festival_events"
    
    id = Column(Integer, primary_key=True)
    festival_name = Column(String(100), nullable=False)  # Diwali, Holi, Eid, Pongal
    festival_date = Column(Date, nullable=False)
    festival_year = Column(Integer, nullable=False)
    days_until = Column(Integer)  # Calculated
    top_products_last_year = Column(Text)  # JSON: [{product_id, name, qty_sold}, ...]


# ==================== FEATURE 4: CHATBOT CONTEXT ====================

class ChatbotContext(Base):
    """Store shop context for chatbot API calls"""
    __tablename__ = "chatbot_context"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_details.id", ondelete="CASCADE"), unique=True, nullable=False)
    shop_name = Column(String(100))
    shop_type = Column(String(100))
    location = Column(String(300))
    top_5_products = Column(Text)  # JSON: [{id, name, revenue}, ...]
    last_10_sales = Column(Text)  # JSON: [{product, qty, amount, date}, ...]
    total_customers = Column(Integer, default=0)
    avg_sale_value = Column(Numeric(10, 2), default=0)
    last_updated = Column(DateTime, server_default=func.now(), onupdate=func.now())

# ==================== WORKER / STAFF MANAGEMENT ====================

class Worker(Base):
    """
    Staff / Worker details as managed in the application.
    Includes salary, position, and access PIN for attendance tracking.
    """
    __tablename__ = "workers"
    
    id = Column(Integer, primary_key=True)
    shopkeeper_id = Column(Integer, ForeignKey("user_details.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    phone = Column(String(20))
    address = Column(Text)
    salary = Column(Numeric(10, 2), default=0)
    assigned_work = Column(String(200))
    position = Column(String(100), default="Staff")
    join_date = Column(Date, server_default=func.now())
    status = Column(String(20), default="active")  # active, inactive, suspended
    pin = Column(String(10))  # Attendance access PIN
    
    # Relationship to shopkeeper (User)
    shopkeeper = relationship("User", foreign_keys=[shopkeeper_id])
    


# ==================== KHATA / LEDGER MANAGEMENT ====================

class KhataBalance(Base):
    """Customer credit ledger (Khata) - tracks outstanding balance"""
    __tablename__ = "khata_balances"
    
    id = Column(Integer, primary_key=True)
    shop_id = Column(Integer, ForeignKey("user_details.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_phone = Column(String(20), nullable=False, index=True)
    customer_name = Column(String(100))
    khata_balance = Column(Numeric(12, 2), default=0)  # Outstanding amount
    last_transaction = Column(DateTime, server_default=func.now())
    
    __table_args__ = (
        UniqueConstraint('shop_id', 'customer_phone', name='uix_shop_customer_khata'),
    )


class KhataHistory(Base):
    """Transaction history for khata (invoices created, payments received)"""
    __tablename__ = "khata_history"
    
    id = Column(Integer, primary_key=True)
    khata_id = Column(Integer, ForeignKey("khata_balances.id", ondelete="CASCADE"), nullable=False)
    transaction_type = Column(Enum("INVOICE", "PAYMENT", "ADJUSTMENT", name="khata_transaction_type"), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    reference_id = Column(String(100))  # invoice_number or payment_id
    description = Column(String(200))
    transaction_date = Column(DateTime, server_default=func.now())


# ==================== EXPENSE TRACKING ====================

class ShopExpense(Base):
    """Track shop daily expenses (rent, staff, utilities, supplies)"""
    __tablename__ = "shop_expenses"
    
    id = Column(Integer, primary_key=True)
    shop_id = Column(Integer, ForeignKey("user_details.id", ondelete="CASCADE"), nullable=False)
    category = Column(String(50), nullable=False)  # rent, utilities, salary, supplies, etc
    amount = Column(Numeric(12, 2), nullable=False)
    description = Column(String(200))
    expense_date = Column(Date, nullable=False)
    payment_method = Column(String(50))  # cash, bank_transfer, etc

# ==================== ONLINE STORE & SHOP PROFILE ====================

class ShopProfile(Base):
    """
    Streamlined ShopProfile containing ONLY the fields the flutter app and backend actively use.
    """
    __tablename__ = "shop_profiles"
    
    id = Column(Integer, primary_key=True)
    shop_id = Column(Integer, ForeignKey("user_details.id", ondelete="CASCADE"), nullable=False, unique=True)
    
    # Basic Shop Information
    shop_name = Column(String(200), nullable=False)
    shop_tagline = Column(String(500))
    shop_description = Column(Text)
    shop_type = Column(String(100), default="General")  
    
    # Contact Information
    phone = Column(String(20))
    email = Column(String(100))
    website = Column(String(200))
    
    # Location Information
    address = Column(Text)
    location = Column(String(300))
    latitude = Column(Float)
    longitude = Column(Float)
    city = Column(String(100))
    state = Column(String(100))
    postal_code = Column(String(10))
    
    # Essential Payment & Config
    upi_id = Column(String(100))
    is_online_store_enabled = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    # Relationships
    user = relationship("User", foreign_keys=[shop_id])
    shop_settings = relationship("ShopSettings", back_populates="shop_profile", uselist=False, cascade="all, delete-orphan")

class OnlineOrder(Base):
    """Customer orders placed via the separate customer login"""
    __tablename__ = "online_orders"
    
    id = Column(Integer, primary_key=True)
    shop_id = Column(Integer, ForeignKey("user_details.id", ondelete="CASCADE"), nullable=False)
    customer_id = Column(Integer, nullable=False) # In future, link to a CustomerUser table
    order_status = Column(Enum("PENDING", "ACCEPTED", "DISPATCHED", "DELIVERED", "REJECTED", name="online_order_status"), default="PENDING")
    total_amount = Column(Numeric(10, 2), nullable=False)
    delivery_address = Column(Text)
    items_json = Column(Text, nullable=False) # JSON: [{product_id, name, qty, price}, ...]

# ==================== PURCHASE ORDERS & INVENTORY ====================

class PurchaseOrder(Base):
    """Orders placed to wholesalers for restocking"""
    __tablename__ = "purchase_orders"
    
    id = Column(Integer, primary_key=True)
    shop_id = Column(Integer, ForeignKey("user_details.id", ondelete="CASCADE"), nullable=False)
    supplier_name = Column(String(100), nullable=False)
    status = Column(Enum("DRAFT", "SENT", "DELIVERED", "CANCELLED", name="po_status"), default="DRAFT")
    total_cost = Column(Numeric(12, 2), default=0)
    items_json = Column(Text, nullable=False)
    expected_delivery = Column(Date)

# ==================== BANK RECONCILIATION & TRANSACTIONS ====================

class BankReconciliation(Base):
    """Daily checks to ensure UPI/Card collections hit the bank account"""
    __tablename__ = "bank_reconciliations"
    
    id = Column(Integer, primary_key=True)
    shop_id = Column(Integer, ForeignKey("user_details.id", ondelete="CASCADE"), nullable=False)
    recon_date = Column(Date, nullable=False)
    expected_upi_amount = Column(Numeric(12, 2), default=0)
    actual_bank_deposit = Column(Numeric(12, 2), default=0)
    status = Column(Enum("MATCHED", "DISCREPANCY", "PENDING", name="recon_status"), default="PENDING")
    notes = Column(Text)

class UniversalTransaction(Base):
    """Enterprise Tracker: Unified journal for ALL money in/out (Sales, Expense, Khata, PO)"""
    __tablename__ = "universal_transactions"
    
    id = Column(Integer, primary_key=True)
    shop_id = Column(Integer, ForeignKey("user_details.id", ondelete="CASCADE"), nullable=False)
    tx_type = Column(Enum("INCOME", "EXPENSE", name="tx_type"), nullable=False)
    category = Column(String(50)) # SALE, KHATA_REPAY, EXPENSE, PO_PAYMENT, SALARY
    amount = Column(Numeric(12, 2), nullable=False)
    reference_id = Column(String(100)) # ID to link back to the exact invoice/expense
    description = Column(String(200))
    tx_date = Column(DateTime, server_default=func.now())

# ==================== GIFTCARDS ====================

class GiftCard(Base):
    """Digital Gift Cards issued by the shop"""
    __tablename__ = "gift_cards"
    
    id = Column(Integer, primary_key=True)
    shop_id = Column(Integer, ForeignKey("user_details.id", ondelete="CASCADE"), nullable=False)
    card_code = Column(String(50), nullable=False, unique=True)
    initial_balance = Column(Numeric(10, 2), nullable=False)
    current_balance = Column(Numeric(10, 2), nullable=False)
    issued_to = Column(String(100))
    expiry_date = Column(Date)
    is_active = Column(Boolean, default=True)

# ==================== END OF MODELS ====================


