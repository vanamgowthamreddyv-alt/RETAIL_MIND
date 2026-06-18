import os
import hashlib
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from jose import jwt

# ===== ENV =====
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30)
)

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)

# =========================
# TOKEN
# =========================
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# =========================
# PASSWORD (FIXED)
# =========================
def hash_password(password: str) -> str:
    # 🔒 FIX happens HERE
    # Convert any-length password → fixed-length string
    sha256_hash = hashlib.sha256(
        password.encode("utf-8")
    ).hexdigest()

    # bcrypt now receives SAFE input (<72 bytes)
    return pwd_context.hash(sha256_hash)


def verify_password(password: str, hashed_password: str) -> bool:
    sha256_hash = hashlib.sha256(
        password.encode("utf-8")
    ).hexdigest()
    return pwd_context.verify(sha256_hash, hashed_password)

