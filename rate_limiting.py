"""
Rate Limiting & API Protection
Prevents abuse, protects backend from overload
Uses Redis for distributed rate limiting (Railway compatible)
"""

import redis
import os
from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from datetime import datetime, timedelta
from typing import Optional
import json


class RateLimiter:
    """Rate limiter using Redis"""
    
    def __init__(self):
        # Connect to Redis
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        self.redis_client = redis.from_url(redis_url, decode_responses=True)
    
    def is_rate_limited(
        self,
        key: str,
        max_requests: int = 100,
        window_seconds: int = 60
    ) -> bool:
        """
        Check if request exceeds rate limit
        
        Args:
            key: Unique identifier (IP, user_id, etc.)
            max_requests: Max requests allowed in window
            window_seconds: Time window in seconds
            
        Returns:
            True if rate limited, False otherwise
        """
        try:
            # Get current count
            current = self.redis_client.get(key)
            
            if current is None:
                # First request in window
                self.redis_client.setex(key, window_seconds, 1)
                return False
            
            current_count = int(current)
            
            if current_count >= max_requests:
                return True
            
            # Increment counter
            self.redis_client.incr(key)
            return False
        
        except Exception as e:
            print(f"Rate limiter error: {e}")
            # On Redis error, allow request (fail open)
            return False
    
    def get_remaining_requests(
        self,
        key: str,
        max_requests: int = 100
    ) -> int:
        """Get remaining requests for a key"""
        try:
            current = self.redis_client.get(key)
            if current is None:
                return max_requests
            return max(0, max_requests - int(current))
        except:
            return max_requests
    
    def get_reset_time(self, key: str) -> Optional[int]:
        """Get time until rate limit resets (in seconds)"""
        try:
            ttl = self.redis_client.ttl(key)
            return ttl if ttl > 0 else None
        except:
            return None


# ====================== RATE LIMIT MIDDLEWARE ======================

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware that enforces rate limits"""
    
    # Rate limit configs by endpoint
    LIMITS = {
        # Auth endpoints - strict limits
        "register": {"max": 5, "window": 3600},  # 5 per hour
        "login": {"max": 10, "window": 300},     # 10 per 5 min
        "password": {"max": 5, "window": 3600}, # 5 per hour
        
        # API endpoints - moderate limits
        "inventory": {"max": 300, "window": 60},   # 300 per minute
        "sales": {"max": 300, "window": 60},       # 300 per minute
        "customers": {"max": 200, "window": 60},   # 200 per minute
        
        # Bulk operations - stricter
        "import": {"max": 10, "window": 3600},     # 10 per hour
        "export": {"max": 20, "window": 3600},     # 20 per hour
        "backup": {"max": 5, "window": 3600},      # 5 per hour
    }
    
    def __init__(self, app):
        super().__init__(app)
        self.limiter = RateLimiter()
    
    async def dispatch(self, request: Request, call_next):
        # Extract client identifier
        client_ip = request.client.host if request.client else "unknown"
        
        # Try to get user ID from request (if authenticated)
        user_id = request.headers.get("x-user-id", client_ip)
        
        # Check if endpoint should be rate limited
        endpoint = request.url.path.split("/")[-1].lower()
        
        limit_config = self._get_limit_config(request.url.path)
        
        if limit_config:
            # Create rate limit key
            limit_key = f"rate_limit:{user_id}:{endpoint}"
            
            # Check rate limit
            if self.limiter.is_rate_limited(
                limit_key,
                max_requests=limit_config["max"],
                window_seconds=limit_config["window"]
            ):
                # Get reset time
                reset_time = self.limiter.get_reset_time(limit_key)
                
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded. Try again in {reset_time} seconds.",
                    headers={
                        "Retry-After": str(reset_time) if reset_time else "60",
                        "X-RateLimit-Limit": str(limit_config["max"]),
                        "X-RateLimit-Remaining": str(self.limiter.get_remaining_requests(limit_key)),
                    }
                )
        
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers
        if limit_config:
            remaining = self.limiter.get_remaining_requests(
                f"rate_limit:{user_id}:{endpoint}"
            )
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            response.headers["X-RateLimit-Limit"] = str(limit_config["max"])
        
        return response
    
    def _get_limit_config(self, path: str):
        """Get rate limit config for a path"""
        path_lower = path.lower()
        
        for endpoint, config in self.LIMITS.items():
            if endpoint in path_lower:
                return config
        
        # Default limit for other endpoints
        return {"max": 1000, "window": 60}


# ===================== RATE LIMIT ENDPOINTS =====================

from fastapi import APIRouter, Depends
from db import get_db
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/rate-limit", tags=["Rate Limiting"])


@router.get("/status/{endpoint}")
async def get_rate_limit_status(
    endpoint: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Get current rate limit status for user"""
    client_ip = request.client.host if request.client else "unknown"
    user_id = request.headers.get("x-user-id", client_ip)
    
    limiter = RateLimiter()
    limit_key = f"rate_limit:{user_id}:{endpoint}"
    
    config = RateLimitMiddleware.LIMITS.get(endpoint, {"max": 1000, "window": 60})
    remaining = limiter.get_remaining_requests(limit_key, config["max"])
    reset_time = limiter.get_reset_time(limit_key)
    
    return {
        "endpoint": endpoint,
        "limit": config["max"],
        "window_seconds": config["window"],
        "remaining": remaining,
        "reset_in_seconds": reset_time,
        "user_id": user_id
    }
