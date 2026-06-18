"""
🔒 SECURITY MODULE — AI Shop Pro Enterprise Backend
Covers:
  - Role-Based Access Control (RBAC): OWNER, CUSTOMER, WORKER
  - Secure JWT decoding and validation
  - Input sanitization (SQL injection / XSS prevention)
  - Rate limiter (in-memory, per IP)
  - Brute-force login protection
  - Sensitive data field masking utilities
"""

import os
import re
import time
import hashlib
from typing import Optional
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from passlib.context import CryptContext

# =====================
# CONSTANTS
# =====================
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE-ME-IN-PRODUCTION-SECRET-KEY-MIN-32-CHARS")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 7))

# Roles
ROLE_OWNER = "OWNER"
ROLE_CUSTOMER = "CUSTOMER"
ROLE_WORKER = "WORKER"
VALID_ROLES = {ROLE_OWNER, ROLE_CUSTOMER, ROLE_WORKER}

# =====================
# PASSWORD HASHING
# =====================
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    """Hash password with SHA-256 pre-processing then bcrypt"""
    sha256_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return pwd_context.hash(sha256_hash)

def verify_password(password: str, hashed_password: str) -> bool:
    """Verify a password against its bcrypt+sha256 hash"""
    sha256_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return pwd_context.verify(sha256_hash, hashed_password)

# =====================
# TOKEN CREATION
# =====================
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a signed JWT access token with role embedded"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(user_id: int, role: str) -> str:
    """Create a long-lived refresh token"""
    data = {"sub": str(user_id), "role": role, "type": "refresh"}
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    data.update({"exp": expire})
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)

# =====================
# JWT BEARER EXTRACTOR
# =====================
security_scheme = HTTPBearer()

def decode_token(token: str) -> dict:
    """Decode and validate a JWT token, raise 401 on failure"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token. Please login again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
) -> dict:
    """Extract and validate the current user from the Bearer token"""
    payload = decode_token(credentials.credentials)
    user_id = payload.get("sub")
    role = payload.get("role", ROLE_OWNER)
    if not user_id:
        raise HTTPException(status_code=401, detail="Token payload missing user ID")
    return {"user_id": int(user_id), "role": role, "payload": payload}

# =====================
# RBAC GUARDS
# =====================
def require_role(*allowed_roles: str):
    """Factory: creates a dependency that blocks any role NOT in allowed_roles"""
    def _check(current_user: dict = Depends(get_current_user)):
        if current_user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {allowed_roles}. Your role: {current_user['role']}"
            )
        return current_user
    return _check

# Convenience guards
def owner_only(current_user: dict = Depends(require_role(ROLE_OWNER))):
    return current_user

def customer_only(current_user: dict = Depends(require_role(ROLE_CUSTOMER))):
    return current_user

def worker_or_owner(current_user: dict = Depends(require_role(ROLE_OWNER, ROLE_WORKER))):
    return current_user

# =====================
# RATE LIMITER (In-Memory)
# =====================
_rate_limit_store: dict = defaultdict(list)  # {ip: [timestamp, ...]}
_login_fail_store: dict = defaultdict(int)   # {ip: fail_count}
_login_lockout: dict = defaultdict(float)    # {ip: unlock_timestamp}

RATE_LIMIT_CALLS = int(os.getenv("RATE_LIMIT_CALLS", 100))
RATE_LIMIT_WINDOW_SECS = int(os.getenv("RATE_LIMIT_WINDOW_SECS", 60))
LOGIN_MAX_FAILS = int(os.getenv("LOGIN_MAX_FAILS", 5))
LOGIN_LOCKOUT_SECS = int(os.getenv("LOGIN_LOCKOUT_SECS", 300))  # 5 minutes

def check_rate_limit(request: Request):
    """Dependency: block IP addresses making too many requests"""
    ip = request.client.host
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW_SECS

    # Clean old timestamps
    _rate_limit_store[ip] = [t for t in _rate_limit_store[ip] if t > window_start]

    if len(_rate_limit_store[ip]) >= RATE_LIMIT_CALLS:
        raise HTTPException(
            status_code=429,
            detail=f"Too many requests. Limit: {RATE_LIMIT_CALLS} per {RATE_LIMIT_WINDOW_SECS}s. Slow down!"
        )
    _rate_limit_store[ip].append(now)

def check_login_lockout(ip: str):
    """Raise 429 if this IP is in brute-force lockout"""
    if _login_lockout[ip] > time.time():
        secs_remaining = int(_login_lockout[ip] - time.time())
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed login attempts. Try again in {secs_remaining} seconds."
        )

def record_login_failure(ip: str):
    """Track a failed login. Lock IP after LOGIN_MAX_FAILS attempts."""
    _login_fail_store[ip] += 1
    if _login_fail_store[ip] >= LOGIN_MAX_FAILS:
        _login_lockout[ip] = time.time() + LOGIN_LOCKOUT_SECS
        _login_fail_store[ip] = 0  # reset counter after lockout

def record_login_success(ip: str):
    """Clear failed attempts on successful login"""
    _login_fail_store[ip] = 0
    _login_lockout[ip] = 0

# =====================
# INPUT SANITIZATION
# =====================
_SQL_INJECTION_PATTERN = re.compile(
    r"(--|;|/\*|\*/|xp_|EXEC|DROP|INSERT|UPDATE|DELETE|SELECT|UNION|ALTER|CREATE|TRUNCATE)",
    re.IGNORECASE,
)
_XSS_PATTERN = re.compile(r"(<script|</script|javascript:|on\w+=)", re.IGNORECASE)

def sanitize_input(value: str, field_name: str = "input") -> str:
    """Block SQL injection and XSS in string inputs"""
    if not isinstance(value, str):
        return value
    if _SQL_INJECTION_PATTERN.search(value):
        raise HTTPException(
            status_code=400,
            detail=f"Malicious SQL pattern detected in field '{field_name}'. Request blocked."
        )
    if _XSS_PATTERN.search(value):
        raise HTTPException(
            status_code=400,
            detail=f"Malicious script pattern detected in field '{field_name}'. Request blocked."
        )
    return value.strip()

# =====================
# DATA MASKING UTILITIES
# =====================
def mask_phone(phone: str) -> str:
    """Mask phone number for logs: 9876543210 → 98****3210"""
    if not phone or len(phone) < 6:
        return "****"
    return phone[:2] + "*" * (len(phone) - 4) + phone[-4:]

def mask_upi(upi_id: str) -> str:
    """Mask UPI ID for logs: user@bank → us**@bank"""
    if not upi_id or "@" not in upi_id:
        return "****"
    parts = upi_id.split("@")
    return parts[0][:2] + "**@" + parts[1]

def mask_email(email: str) -> str:
    """Mask email for logs: user@example.com → us**@example.com"""
    if not email or "@" not in email:
        return "****"
    local, domain = email.split("@", 1)
    return local[:2] + "**@" + domain
