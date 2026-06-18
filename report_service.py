"""
Daily Report Service (Feature 16)
Generate daily WhatsApp reports with revenue, expenses, profit, top product
"""

from sqlalchemy.orm import Session
from models import DailyReport, Invoice, Payment, Product, StockMovement
from sqlalchemy import func
from datetime import date, datetime, timedelta
from decimal import Decimal


class ReportService:
    
    @staticmethod
    def generate_daily_report(db: Session, user_id: int, report_date: date = None) -> dict:
        """Generate daily report for WhatsApp"""
        if report_date is None:
            report_date = date.today()
        
        # Check if report already exists
        existing_report = db.query(DailyReport).filter_by(
            user_id=user_id,
            report_date=report_date
        ).first()
        
        if existing_report:
            return {"status": "exists", "report_id": existing_report.id}
        
        # Calculate metrics
        
        # 1. Revenue (total paid invoices for the day)
        invoices = db.query(Invoice).filter(
            Invoice.user_id == user_id,
            Invoice.invoice_date == report_date
        ).all()
        
        total_revenue = Decimal("0")
        bill_count = 0
        cash_collected = Decimal("0")
        upi_collected = Decimal("0")
        card_collected = Decimal("0")
        
        for inv in invoices:
            bill_count += 1
            payments = db.query(Payment).filter_by(invoice_id=inv.id).all()
            
            for payment in payments:
                if payment.payment_method == "CASH":
                    cash_collected += payment.amount
                elif payment.payment_method == "ONLINE":  # UPI
                    upi_collected += payment.amount
                elif payment.payment_method == "CARD":
                    card_collected += payment.amount
                
                total_revenue += payment.amount
        
        # 2. Expenses (simplified: assume cost = 40% of revenue for now)
        # In real system, would query actual purchases
        total_expenses = total_revenue * Decimal("0.4")
        total_profit = total_revenue - total_expenses
        
        # 3. Top product (by quantity sold)
        top_products = db.query(
            Product.product_name,
            func.sum(StockMovement.quantity).label("qty")
        ).join(StockMovement).filter(
            StockMovement.product_id == Product.id,
            Product.user_id == user_id,
            StockMovement.movement_type == "OUT",
            StockMovement.created_at >= datetime.combine(report_date, datetime.min.time()),
            StockMovement.created_at < datetime.combine(report_date + timedelta(days=1), datetime.min.time())
        ).group_by(Product.product_name).order_by(
            func.sum(StockMovement.quantity).desc()
        ).first()
        
        top_product_name = top_products[0] if top_products else "N/A"
        top_product_qty = int(top_products[1]) if top_products and top_products[1] else 0
        
        # Create report
        report = DailyReport(
            user_id=user_id,
            report_date=report_date,
            total_revenue=total_revenue,
            total_expenses=total_expenses,
            total_profit=total_profit,
            bill_count=bill_count,
            top_product_name=top_product_name,
            top_product_qty=top_product_qty,
            cash_collected=cash_collected,
            upi_collected=upi_collected,
            card_collected=card_collected
        )
        db.add(report)
        db.commit()
        
        return {
            "report_id": report.id,
            "report_date": report.report_date.isoformat(),
            "total_revenue": float(total_revenue),
            "total_expenses": float(total_expenses),
            "total_profit": float(total_profit),
            "bill_count": bill_count,
            "top_product": top_product_name,
            "cash": float(cash_collected),
            "upi": float(upi_collected),
            "card": float(card_collected)
        }
    
    @staticmethod
    def get_report(db: Session, report_id: int) -> dict:
        """Get specific daily report"""
        report = db.query(DailyReport).filter_by(id=report_id).first()
        
        if not report:
            return {"error": "Report not found"}
        
        return {
            "report_id": report.id,
            "report_date": report.report_date.isoformat(),
            "total_revenue": float(report.total_revenue),
            "total_expenses": float(report.total_expenses),
            "total_profit": float(report.total_profit),
            "bill_count": report.bill_count,
            "top_product": report.top_product_name,
            "top_product_qty": report.top_product_qty,
            "cash": float(report.cash_collected),
            "upi": float(report.upi_collected),
            "card": float(report.card_collected),
            "whatsapp_sent": report.whatsapp_sent
        }
    
    @staticmethod
    def format_whatsapp_message(report: dict, shop_name: str) -> str:
        """Format report as WhatsApp message"""
        message = f"""📊 Daily Report - {report['report_date']}
{shop_name}

💰 Revenue: ₹{report['total_revenue']:.2f}
📦 Expenses: ₹{report['total_expenses']:.2f}
✅ Profit: ₹{report['total_profit']:.2f}

📈 Bills: {report['bill_count']}
⭐ Top Product: {report['top_product']} ({report['top_product_qty']} sold)

💵 Cash: ₹{report['cash']:.2f}
📱 UPI: ₹{report['upi']:.2f}
🏧 Card: ₹{report['card']:.2f}

Generated: {datetime.now().strftime('%I:%M %p')}"""
        
        return message
    
    @staticmethod
    def send_daily_report_whatsapp(db: Session, user_id: int, owner_phone: str) -> dict:
        """Send daily report to owner's WhatsApp"""
        report_data = ReportService.generate_daily_report(db, user_id)
        
        if "error" in report_data:
            return report_data
        
        report = db.query(DailyReport).filter_by(id=report_data["report_id"]).first()
        
        # Get shop name from user (would need to join ShopProfile)
        shop_name = "Your Shop"  # Placeholder
        
        message = ReportService.format_whatsapp_message(report_data, shop_name)
        
        # Mark as sent
        report.whatsapp_sent = True
        report.whatsapp_sent_at = datetime.now()
        db.commit()
        
        return {
            "status": "ready_to_send",
            "recipient": owner_phone,
            "message": message,
            "action": "Send this WhatsApp message to owner"
        }
    
    @staticmethod
    def get_weekly_reports(db: Session, user_id: int) -> list:
        """Get last 7 days of reports"""
        from datetime import timedelta
        start_date = date.today() - timedelta(days=7)
        
        reports = db.query(DailyReport).filter(
            DailyReport.user_id == user_id,
            DailyReport.report_date >= start_date
        ).order_by(DailyReport.report_date.desc()).all()
        
        return [{
            "date": r.report_date.isoformat(),
            "revenue": float(r.total_revenue),
            "profit": float(r.total_profit),
            "bills": r.bill_count,
            "top_product": r.top_product_name
        } for r in reports]
    
    @staticmethod
    def get_monthly_summary(db: Session, user_id: int, year: int, month: int) -> dict:
        """Get monthly summary report"""
        from datetime import datetime as dt
        start_date = date(year, month, 1)
        if month == 12:
            end_date = date(year + 1, 1, 1)
        else:
            end_date = date(year, month + 1, 1)
        
        reports = db.query(DailyReport).filter(
            DailyReport.user_id == user_id,
            DailyReport.report_date >= start_date,
            DailyReport.report_date < end_date
        ).all()
        
        if not reports:
            return {"error": "No reports for this period"}
        
        total_revenue = sum(float(r.total_revenue) for r in reports)
        total_profit = sum(float(r.total_profit) for r in reports)
        total_bills = sum(r.bill_count for r in reports)
        avg_daily_revenue = total_revenue / len(reports) if reports else 0
        
        return {
            "period": f"{month}/{year}",
            "total_revenue": total_revenue,
            "total_profit": total_profit,
            "total_bills": total_bills,
            "avg_daily_revenue": avg_daily_revenue,
            "days_with_sales": len(reports),
            "profit_margin": (total_profit / total_revenue * 100) if total_revenue > 0 else 0
        }
    
    @staticmethod
    def schedule_daily_report(db: Session, user_id: int, owner_phone: str, 
                             scheduled_time: str = "18:00") -> dict:
        """
        Schedule daily report at specific time (e.g., 6 PM)
        Returns info for Flutter notification scheduling
        """
        return {
            "status": "scheduled",
            "scheduled_time": scheduled_time,
            "message": f"Daily report will be sent to {owner_phone} every day at {scheduled_time}",
            "action": "Use Flutter's flutter_local_notifications to schedule this"
        }
