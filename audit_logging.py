"""
Audit Logging System for Compliance Tracking
Tracks all data changes with timestamps, user info, and action details
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session
from datetime import datetime
from enum import Enum as PythonEnum
from db import Base
import json


class AuditAction(str, PythonEnum):
    """Enum for different audit actions"""
    CREATE = "CREATE"
    READ = "READ"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    EXPORT = "EXPORT"
    IMPORT = "IMPORT"
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    BACKUP = "BACKUP"
    RESTORE = "RESTORE"


class AuditLog(Base):
    """Audit log model - tracks all changes"""
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_details.id"), nullable=True)
    action = Column(String(50), nullable=False)  # CREATE, READ, UPDATE, DELETE, etc.
    table_name = Column(String(100), nullable=False)
    record_id = Column(Integer, nullable=True)
    old_values = Column(JSON, nullable=True)  # Previous state (for updates)
    new_values = Column(JSON, nullable=True)  # New state
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(Text, nullable=True)
    status = Column(String(20), default="SUCCESS")  # SUCCESS, FAILED
    error_message = Column(Text, nullable=True)
    timestamp = Column(DateTime, server_default=func.now())
    description = Column(Text, nullable=True)
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    
    def __repr__(self):
        return f"<AuditLog {self.id}: {self.action} on {self.table_name} at {self.timestamp}>"


class AuditService:
    """Service for audit logging operations"""
    
    @staticmethod
    def log_action(
        db: Session,
        user_id: int = None,
        action: AuditAction = None,
        table_name: str = None,
        record_id: int = None,
        old_values: dict = None,
        new_values: dict = None,
        ip_address: str = None,
        user_agent: str = None,
        description: str = None
    ):
        """
        Create an audit log entry
        
        Args:
            db: Database session
            user_id: ID of user performing action
            action: Type of action (CREATE, UPDATE, DELETE, etc.)
            table_name: Name of affected table
            record_id: ID of affected record
            old_values: Previous data (for updates)
            new_values: New data (for updates/creates)
            ip_address: Client IP address
            user_agent: Browser/client info
            description: Human-readable description
        """
        try:
            audit_log = AuditLog(
                user_id=user_id,
                action=action,
                table_name=table_name,
                record_id=record_id,
                old_values=old_values,
                new_values=new_values,
                ip_address=ip_address,
                user_agent=user_agent,
                description=description,
                status="SUCCESS"
            )
            db.add(audit_log)
            db.commit()
            return audit_log
        except Exception as e:
            # Log the error
            audit_log = AuditLog(
                user_id=user_id,
                action=action,
                table_name=table_name,
                record_id=record_id,
                ip_address=ip_address,
                status="FAILED",
                error_message=str(e)
            )
            db.add(audit_log)
            db.commit()
            raise
    
    @staticmethod
    def get_user_audit_history(db: Session, user_id: int, limit: int = 100):
        """Get audit history for specific user"""
        return db.query(AuditLog).filter(
            AuditLog.user_id == user_id
        ).order_by(AuditLog.timestamp.desc()).limit(limit).all()
    
    @staticmethod
    def get_table_audit_history(db: Session, table_name: str, limit: int = 100):
        """Get audit history for specific table"""
        return db.query(AuditLog).filter(
            AuditLog.table_name == table_name
        ).order_by(AuditLog.timestamp.desc()).limit(limit).all()
    
    @staticmethod
    def get_record_audit_history(db: Session, table_name: str, record_id: int):
        """Get complete change history for a specific record"""
        return db.query(AuditLog).filter(
            AuditLog.table_name == table_name,
            AuditLog.record_id == record_id
        ).order_by(AuditLog.timestamp.asc()).all()
    
    @staticmethod
    def export_audit_logs(db: Session, start_date=None, end_date=None):
        """Export audit logs for compliance reports"""
        query = db.query(AuditLog)
        if start_date:
            query = query.filter(AuditLog.timestamp >= start_date)
        if end_date:
            query = query.filter(AuditLog.timestamp <= end_date)
        return query.order_by(AuditLog.timestamp.desc()).all()


# ======================== AUDIT MIDDLEWARE ========================

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class AuditMiddleware(BaseHTTPMiddleware):
    """Middleware that logs all requests to audit trail"""
    
    async def dispatch(self, request: Request, call_next):
        # Extract client info
        client_ip = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent", "Unknown")
        
        # Call the endpoint
        response = await call_next(request)
        
        # Log important requests (not GET requests to health checks)
        if request.method in ["POST", "PUT", "DELETE"] and "/health" not in request.url.path:
            # Note: In production, extract user_id from JWT token
            # This is a simplified version
            try:
                # Get database session
                from db import get_db
                db = next(get_db())
                
                AuditService.log_action(
                    db=db,
                    action=request.method,
                    table_name=request.url.path.split("/")[1] if "/" in request.url.path else "unknown",
                    ip_address=client_ip,
                    user_agent=user_agent,
                    description=f"{request.method} {request.url.path}",
                    status="SUCCESS" if response.status_code < 400 else "FAILED"
                )
            except Exception as e:
                print(f"Audit logging error: {e}")
        
        return response
