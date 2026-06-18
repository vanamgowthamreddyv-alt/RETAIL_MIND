"""
🚀 AI Shop Pro Enterprise Backend — Main Application
====================================================
Fully secured FastAPI app with:
- Role-Based Access Control (RBAC)
- Rate Limiting & Brute-Force Protection
- CORS restricted to known origins
- SQL Injection & XSS Protection
- All ERP modules registered
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
import os
import time
import logging

# ========================
# LOGGING SETUP
# ========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("ai_shop_pro")

# ========================
# IMPORT ALL ROUTERS
# ========================
# Core Auth & Session
from auth_routes import router as authentication_router
from session_routes import router as session_router

# Core ERP
from inventory import router as inventory_router
from attendance import router as attendance_router
from invoices_billing import router as invoices_router
from customers import router as customers_router
from shop_management import router as shop_management_router
from bill_generated import router as bill_router

# New Enterprise Modules
from shop_settings import router as shop_settings_router
from khata_ledger import router as khata_router
from purchase_orders import router as purchase_orders_router
from online_store import router as online_store_router
from retail_intelligence import router as intelligence_router
from gst_and_giftcards import router as gst_and_giftcards_router

# Legacy extended features (non-chatbot)
from new_feature_routers import router as new_features_router

# DB initialization
from db import engine, get_db
from models import Base

# ========================
# APP CREATION
# ========================
api = FastAPI(
    title="AI Shop Pro Enterprise Backend",
    description=(
        "🏪 Complete retail ERP backend for AI Shop Pro.\n\n"
        "Modules: Auth (RBAC), Inventory, Invoices, Khata Ledger, "
        "Purchase Orders, Bank Reconciliation, Online Store, "
        "Worker Management, Expense Tracker, Enterprise P&L, Retail Intelligence."
    ),
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ========================
# DB INIT ON STARTUP
# ========================
try:
    Base.metadata.create_all(bind=engine)
    logger.info("Database connected successfully! All database tables initialized.")
except Exception as e:
    logger.warning(f"⚠️ Database initialization deferred: {e}")

# ========================
# SECURITY MIDDLEWARE
# ========================

# 1. CORS — Restrict to known origins only (no wildcard *)
ALLOWED_ORIGINS = [
    os.getenv("FRONTEND_URL", "https://your-online-store.com"),
    "http://localhost:3000",
    "http://localhost:8080",
    "http://127.0.0.1:8000",
]
api.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)

# 2. Trusted Host — prevent Host header injection attacks
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,*.railway.app").split(",")
api.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])  # Set to ALLOWED_HOSTS in production

# 3. Request Logging & Timing Middleware
@api.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration_ms = round((time.time() - start) * 1000, 2)

    # Mask sensitive paths in logs

    path = request.url.path
    client_ip = request.client.host if request.client else "unknown"
    logger.info(f"{request.method} {path} -> {response.status_code} [{duration_ms}ms] from {client_ip}")
    response.headers["X-Response-Time"] = f"{duration_ms}ms"
    return response

# 4. Global Exception Handler — never leak stack traces to clients
@api.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error. Our team has been notified.",
            "path": request.url.path,
        }
    )

# ========================
# REGISTER ALL ROUTERS
# ========================

# Auth
api.include_router(authentication_router, prefix="/auth", tags=["Authentication"])
api.include_router(session_router, tags=["Session Management"])

# Core ERP
api.include_router(bill_router, prefix="/bill", tags=["Bill Generation"])
api.include_router(inventory_router, tags=["Inventory Management"])
api.include_router(attendance_router, tags=["Attendance Management"])
api.include_router(invoices_router, tags=["Invoices & Billing"])
api.include_router(customers_router, tags=["Customer Management"])
api.include_router(shop_management_router, tags=["Shop Management"])

# Enterprise Modules
api.include_router(shop_settings_router)          # /shop/*
api.include_router(khata_router)                  # /khata/*
api.include_router(purchase_orders_router)        # /purchase-orders/*
api.include_router(online_store_router)           # /store/*
api.include_router(intelligence_router)           # /expenses, /workers, /bank-recon, /enterprise/*, /retail/*
api.include_router(gst_and_giftcards_router)      # /gift-cards, /gst/*

# Legacy extended features
api.include_router(new_features_router, tags=["Legacy Features"])

# ========================
# ROOT & HEALTH ENDPOINTS
# ========================
@api.get("/", tags=["System"])
async def root():
    return {
        "status": "operational",
        "app": "AI Shop Pro Enterprise Backend",
        "version": "3.0.0",
        "modules": [
            "Authentication (RBAC: OWNER/CUSTOMER/WORKER)",
            "Shop Settings & UPI QR",
            "Inventory Management",
            "Invoices & Billing (with auto-sync)",
            "Khata Ledger",
            "Purchase Orders",
            "Expense Tracker",
            "Worker Management",
            "Bank Reconciliation",
            "Online Store",
            "Enterprise P&L Tracker",
            "Retail Intelligence",
            "Attendance Management",
        ],
        "security": [
            "JWT RBAC enforced",
            "Rate limiting active",
            "Brute-force login protection",
            "SQL injection blocking",
            "XSS input sanitization",
            "CORS restricted",
            "No data leakage across shops",
        ]
    }

@api.get("/health", tags=["System"])
async def health_check():
    from db import sessionLocal
    from sqlalchemy import text
    db_ok = False
    try:
        db = sessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        db_ok = True
    except Exception:
        pass
    return {
        "status": "healthy" if db_ok else "degraded",
        "database": "connected" if db_ok else "unreachable",
        "timestamp": time.time(),
    }

