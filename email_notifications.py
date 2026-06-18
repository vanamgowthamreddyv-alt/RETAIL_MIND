"""
Email Notification Service
Handles sending emails for alerts, notifications, and business events
Integrates with SendGrid (production) and SMTP fallback
"""

import os
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship, Session
from sqlalchemy.sql import func
from db import Base
from typing import List, Optional
import asyncio
from enum import Enum as PythonEnum


class NotificationType(str, PythonEnum):
    """Types of notifications"""
    STOCK_ALERT = "STOCK_ALERT"
    PAYMENT_RECEIVED = "PAYMENT_RECEIVED"
    INVOICE_GENERATED = "INVOICE_GENERATED"
    LOW_INVENTORY = "LOW_INVENTORY"
    DELIVERY_REMINDER = "DELIVERY_REMINDER"
    CUSTOMER_REGISTRATION = "CUSTOMER_REGISTRATION"
    BULK_IMPORT = "BULK_IMPORT"
    BACKUP_COMPLETE = "BACKUP_COMPLETE"
    SYSTEM_ALERT = "SYSTEM_ALERT"
    DAILY_REPORT = "DAILY_REPORT"


class EmailNotification(Base):
    """Model to store email notifications"""
    __tablename__ = "email_notifications"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_details.id"), nullable=False)
    recipient_email = Column(String(100), nullable=False)
    notification_type = Column(String(50), nullable=False)
    subject = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    html_body = Column(Text, nullable=True)
    is_sent = Column(Boolean, default=False)
    send_attempts = Column(Integer, default=0)
    last_attempt = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id])


class EmailNotificationService:
    """Service for sending email notifications"""
    
    # Email configuration from environment
    SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SENDER_EMAIL = os.getenv("SENDER_EMAIL", "")
    SENDER_PASSWORD = os.getenv("SENDER_PASSWORD", "")
    
    @classmethod
    def send_email(
        cls,
        recipient_email: str,
        subject: str,
        body: str,
        html_body: str = None
    ) -> bool:
        """
        Send email using SMTP
        
        Args:
            recipient_email: Recipient email address
            subject: Email subject
            body: Plain text body
            html_body: HTML body (optional)
            
        Returns:
            True if sent successfully, False otherwise
        """
        try:
            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = cls.SENDER_EMAIL
            msg["To"] = recipient_email
            
            # Attach plain text
            msg.attach(MIMEText(body, "plain"))
            
            # Attach HTML if provided
            if html_body:
                msg.attach(MIMEText(html_body, "html"))
            
            # Send email
            with smtplib.SMTP(cls.SMTP_SERVER, cls.SMTP_PORT) as server:
                server.starttls()
                server.login(cls.SENDER_EMAIL, cls.SENDER_PASSWORD)
                server.send_message(msg)
            
            return True
        except Exception as e:
            print(f"Email send error: {e}")
            return False
    
    @classmethod
    def create_notification(
        cls,
        db: Session,
        user_id: int,
        recipient_email: str,
        notification_type: NotificationType,
        subject: str,
        body: str,
        html_body: str = None,
        send_immediately: bool = True
    ) -> EmailNotification:
        """Create and optionally send a notification"""
        
        notification = EmailNotification(
            user_id=user_id,
            recipient_email=recipient_email,
            notification_type=notification_type,
            subject=subject,
            body=body,
            html_body=html_body
        )
        
        db.add(notification)
        db.commit()
        
        if send_immediately:
            success = cls.send_email(
                recipient_email=recipient_email,
                subject=subject,
                body=body,
                html_body=html_body
            )
            
            if success:
                notification.is_sent = True
                notification.sent_at = datetime.utcnow()
            else:
                notification.send_attempts += 1
                notification.last_attempt = datetime.utcnow()
            
            db.commit()
        
        return notification
    
    # ===== TEMPLATE GENERATORS =====
    
    @staticmethod
    def stock_alert_template(product_name: str, current_stock: int, min_stock: int) -> tuple:
        """Generate stock alert email"""
        subject = f"⚠️ Low Stock Alert: {product_name}"
        body = f"""
Stock Alert Notification

Product: {product_name}
Current Stock: {current_stock}
Minimum Stock: {min_stock}

Please reorder this product to maintain inventory levels.
        """
        
        html = f"""
<html>
<body style="font-family: Arial, sans-serif;">
    <h2 style="color: #ff6b6b;">⚠️ Low Stock Alert</h2>
    <p><strong>Product:</strong> {product_name}</p>
    <p><strong>Current Stock:</strong> {current_stock}</p>
    <p><strong>Minimum Stock:</strong> {min_stock}</p>
    <p>Please reorder this product to maintain inventory levels.</p>
</body>
</html>
        """
        return subject, body, html
    
    @staticmethod
    def payment_received_template(amount: float, invoice_id: str, customer_name: str) -> tuple:
        """Generate payment received email"""
        subject = f"✅ Payment Received - Invoice {invoice_id}"
        body = f"""
Payment Confirmation

Amount: ₹{amount:,.2f}
Invoice ID: {invoice_id}
Customer: {customer_name}
Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Thank you for the payment.
        """
        
        html = f"""
<html>
<body style="font-family: Arial, sans-serif;">
    <h2 style="color: #10b981;">✅ Payment Received</h2>
    <p><strong>Amount:</strong> ₹{amount:,.2f}</p>
    <p><strong>Invoice ID:</strong> {invoice_id}</p>
    <p><strong>Customer:</strong> {customer_name}</p>
    <p><strong>Date:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    <p>Thank you for the payment.</p>
</body>
</html>
        """
        return subject, body, html
    
    @classmethod
    def welcome_credentials_template(cls, username: str, password: str, role: str) -> tuple:
        """Generate welcome email with credentials"""
        subject = f"Welcome to AI Shop Enterprise! Here are your credentials"
        body = f"""
        Hello {username},
        
        Your {role} account has been successfully created.
        Please keep these credentials safe.
        
        Username: {username}
        Password: {password}
        
        You can now log into your mobile or web app using these credentials.
        
        Best Regards,
        The AI Shop Enterprise Team
        """
        return subject, body

    @classmethod
    def send_otp_template(cls, otp: str, purpose: str = "Verification") -> tuple:
        """Generate OTP email"""
        subject = f"{otp} is your AI Shop {purpose} OTP"
        body = f"""
        Your One-Time Password (OTP) for {purpose} is:
        
        {otp}
        
        This OTP is valid for the next 10 minutes. 
        Do not share this code with anyone.
        
        Best Regards,
        The AI Shop Enterprise Team
        """
        return subject, body

    @classmethod
    def backup_complete_template(timestamp: str, records_backed_up: int) -> tuple:
        """Generate backup complete email"""
        subject = "✅ Database Backup Complete"
        body = f"""
Backup Notification

Backup Time: {timestamp}
Records Backed Up: {records_backed_up}
Status: SUCCESS

Your data is safely backed up.
        """
        
        html = f"""
<html>
<body style="font-family: Arial, sans-serif;">
    <h2 style="color: #10b981;">✅ Backup Complete</h2>
    <p><strong>Backup Time:</strong> {timestamp}</p>
    <p><strong>Records Backed Up:</strong> {records_backed_up:,}</p>
    <p><strong>Status:</strong> SUCCESS</p>
    <p>Your data is safely backed up.</p>
</body>
</html>
        """
        return subject, body, html

