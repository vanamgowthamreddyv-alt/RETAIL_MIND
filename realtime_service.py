"""
Real-Time Features Service
WebSocket-based real-time updates for: notifications, inventory, sales, workers, customers
Perfect for multi-staff retail management
"""

from fastapi import APIRouter, WebSocket, Depends, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from datetime import datetime, timedelta
import json
import asyncio
from typing import Dict, List, Set, Optional
from collections import defaultdict
import logging

from db import get_db, engine, Base
from models import Product, Sales, Customer, Invoice, Payment, Notification, User, Attendance

logger = logging.getLogger(__name__)

# ==================== REALTIME MANAGER ====================

class ConnectionManager:
    """Manage WebSocket connections for real-time updates"""
    
    def __init__(self):
        self.active_connections: Dict[int, List[WebSocket]] = defaultdict(list)  # user_id -> [connections]
        self.user_shops: Dict[int, int] = {}  # connection_id -> shop_id
    
    async def connect(self, websocket: WebSocket, user_id: int, shop_id: int):
        await websocket.accept()
        self.active_connections[user_id].append(websocket)
        self.user_shops[id(websocket)] = shop_id
        print(f"✅ User {user_id} connected. Total: {len(self.active_connections[user_id])}")
    
    async def disconnect(self, user_id: int, websocket: WebSocket):
        self.active_connections[user_id].remove(websocket)
        self.user_shops.pop(id(websocket), None)
        print(f"❌ User {user_id} disconnected")
    
    async def broadcast_to_user(self, user_id: int, data: dict):
        """Send to all connections of a user"""
        for connection in self.active_connections[user_id]:
            try:
                await connection.send_json(data)
            except Exception as e:
                logger.error(f"Error broadcasting to user {user_id}: {e}")
    
    async def broadcast_to_shop(self, shop_id: int, data: dict):
        """Send to all users in a shop"""
        for user_id, connections in self.active_connections.items():
            for connection in connections:
                if self.user_shops.get(id(connection)) == shop_id:
                    try:
                        await connection.send_json(data)
                    except:
                        pass
    
    async def broadcast_to_all(self, data: dict):
        """Send to all connected users"""
        for connections in self.active_connections.values():
            for connection in connections:
                try:
                    await connection.send_json(data)
                except:
                    pass


manager = ConnectionManager()

# ==================== REALTIME DATA SERVICE ====================

class RealtimeDataService:
    """Service to fetch real-time data"""
    
    @staticmethod
    def get_live_sales(db: Session, shop_id: int, limit: int = 10) -> List[dict]:
        """Get latest sales in real-time"""
        sales = db.query(Sales).filter_by(user_id=shop_id).order_by(desc(Sales.id)).limit(limit).all()
        
        return [{
            "id": s.id,
            "product": s.product_name if hasattr(s, 'product_name') else "Unknown",
            "quantity": s.quantity,
            "price": float(s.price),
            "total": float(s.quantity * s.price),
            "timestamp": s.created_at.isoformat() if hasattr(s, 'created_at') else "",
            "status": "completed"
        } for s in sales]
    
    @staticmethod
    def get_low_stock_products(db: Session, shop_id: int, threshold: int = 10) -> List[dict]:
        """Get products with low stock"""
        low_stock = db.query(Product).filter(
            Product.quantity <= threshold,
            Product.user_id == shop_id
        ).order_by(Product.quantity).all()
        
        return [{
            "id": p.id,
            "name": p.name,
            "current_stock": p.quantity,
            "reorder_level": threshold,
            "price": float(p.price) if hasattr(p, 'price') else 0,
            "alert": "URGENT" if p.quantity == 0 else "WARNING"
        } for p in low_stock]
    
    @staticmethod
    def get_daily_metrics(db: Session, shop_id: int) -> dict:
        """Get today's sales metrics"""
        today = datetime.now().date()
        
        # Total sales today
        sales_today = db.query(func.sum(Sales.quantity)).filter(
            Sales.user_id == shop_id,
            func.date(Sales.created_at) == today
        ).scalar() or 0
        
        # Revenue today
        revenue = db.query(func.sum(Sales.quantity * Sales.price)).filter(
            Sales.user_id == shop_id,
            func.date(Sales.created_at) == today
        ).scalar() or 0
        
        # Transaction count
        transactions = db.query(func.count(Sales.id)).filter(
            Sales.user_id == shop_id,
            func.date(Sales.created_at) == today
        ).scalar() or 0
        
        # Active customers today
        active_customers = db.query(func.count(Customer.id)).filter(
            Customer.user_id == shop_id,
            func.date(Customer.created_at) >= today
        ).scalar() or 0
        
        return {
            "items_sold": int(sales_today),
            "revenue": float(revenue),
            "transactions": int(transactions),
            "active_customers": int(active_customers),
            "timestamp": datetime.now().isoformat()
        }
    
    @staticmethod
    def get_active_workers(db: Session, shop_id: int) -> List[dict]:
        """Get currently active workers"""
        today = datetime.now().date()
        active = db.query(Attendance).filter(
            Attendance.user_id == shop_id,
            Attendance.date == today,
            Attendance.status == "present"
        ).all()
        
        return [{
            "id": a.id,
            "name": a.employee_name if hasattr(a, 'employee_name') else "Unknown",
            "check_in": a.check_in_time.isoformat() if hasattr(a, 'check_in_time') else "",
            "status": "checked_in"
        } for a in active]
    
    @staticmethod
    def get_pending_payments(db: Session, shop_id: int) -> List[dict]:
        """Get pending/unpaid invoices"""
        pending = db.query(Invoice).filter(
            Invoice.user_id == shop_id,
            Invoice.payment_status != "paid"
        ).order_by(desc(Invoice.created_at)).limit(5).all()
        
        return [{
            "id": p.id,
            "customer": p.customer_name if hasattr(p, 'customer_name') else "Unknown",
            "amount": float(p.total_amount) if hasattr(p, 'total_amount') else 0,
            "status": p.payment_status if hasattr(p, 'payment_status') else "pending",
            "date": p.created_at.isoformat() if hasattr(p, 'created_at') else ""
        } for p in pending]


# ==================== NOTIFICATION MANAGER ====================

class NotificationManager:
    """Manage real-time notifications"""
    
    @staticmethod
    async def send_stock_alert(manager: ConnectionManager, shop_id: int, product_name: str, stock: int):
        """Alert about low stock"""
        alert = {
            "type": "stock_alert",
            "title": "Low Stock Alert",
            "message": f"{product_name} stock is {stock}",
            "severity": "high" if stock == 0 else "medium",
            "timestamp": datetime.now().isoformat()
        }
        await manager.broadcast_to_shop(shop_id, alert)
    
    @staticmethod
    async def send_sale_notification(manager: ConnectionManager, shop_id: int, product: str, quantity: int, amount: float):
        """Notify about new sale"""
        notification = {
            "type": "new_sale",
            "title": "New Sale",
            "message": f"{quantity}x {product} sold for ₹{amount:.2f}",
            "severity": "info",
            "timestamp": datetime.now().isoformat()
        }
        await manager.broadcast_to_shop(shop_id, notification)
    
    @staticmethod
    async def send_payment_received(manager: ConnectionManager, shop_id: int, amount: float, method: str):
        """Notify about payment received"""
        notification = {
            "type": "payment_received",
            "title": "Payment Received",
            "message": f"₹{amount:.2f} received via {method}",
            "severity": "success",
            "timestamp": datetime.now().isoformat()
        }
        await manager.broadcast_to_shop(shop_id, notification)
    
    @staticmethod
    async def send_inventory_update(manager: ConnectionManager, shop_id: int, product: str, action: str):
        """Notify about inventory changes"""
        notification = {
            "type": "inventory_update",
            "title": "Inventory Updated",
            "message": f"{product} {action}",
            "severity": "info",
            "timestamp": datetime.now().isoformat()
        }
        await manager.broadcast_to_shop(shop_id, notification)


# ==================== API ROUTER ====================

router = APIRouter(prefix="/api", tags=["Real-Time"])

@router.websocket("/ws/live/{user_id}/{shop_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int, shop_id: int, db: Session = Depends(get_db)):
    """
    WebSocket endpoint for real-time updates
    
    Connects to: ws://localhost:8000/api/ws/live/{user_id}/{shop_id}
    
    Receives:
    {
        "action": "subscribe",
        "channel": "sales" | "inventory" | "metrics" | "workers"
    }
    
    Sends:
    {
        "type": "new_sale" | "low_stock" | "metrics_update" | "worker_status",
        "data": {...}
    }
    """
    await manager.connect(websocket, user_id, shop_id)
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            action = data.get("action")
            
            if action == "subscribe":
                channel = data.get("channel", "all")
                
                if channel == "sales" or channel == "all":
                    sales = RealtimeDataService.get_live_sales(db, shop_id)
                    await websocket.send_json({
                        "type": "sales_update",
                        "channel": "sales",
                        "data": sales
                    })
                
                if channel == "inventory" or channel == "all":
                    low_stock = RealtimeDataService.get_low_stock_products(db, shop_id)
                    await websocket.send_json({
                        "type": "inventory_update",
                        "channel": "inventory",
                        "data": low_stock
                    })
                
                if channel == "metrics" or channel == "all":
                    metrics = RealtimeDataService.get_daily_metrics(db, shop_id)
                    await websocket.send_json({
                        "type": "metrics_update",
                        "channel": "metrics",
                        "data": metrics
                    })
                
                if channel == "workers" or channel == "all":
                    workers = RealtimeDataService.get_active_workers(db, shop_id)
                    await websocket.send_json({
                        "type": "worker_status",
                        "channel": "workers",
                        "data": workers
                    })
            
            elif action == "ping":
                await websocket.send_json({"type": "pong"})
    
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        await manager.disconnect(user_id, websocket)


@router.get("/live-sales/{shop_id}")
async def get_live_sales(shop_id: int, db: Session = Depends(get_db)):
    """Get latest sales (HTTP fallback)"""
    try:
        sales = RealtimeDataService.get_live_sales(db, shop_id)
        return {
            "status": "success",
            "data": sales,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/live-metrics/{shop_id}")
async def get_live_metrics(shop_id: int, db: Session = Depends(get_db)):
    """Get live dashboard metrics"""
    try:
        metrics = RealtimeDataService.get_daily_metrics(db, shop_id)
        low_stock = RealtimeDataService.get_low_stock_products(db, shop_id)
        workers = RealtimeDataService.get_active_workers(db, shop_id)
        pending = RealtimeDataService.get_pending_payments(db, shop_id)
        
        return {
            "status": "success",
            "metrics": metrics,
            "alerts": {
                "low_stock_count": len(low_stock),
                "low_stock_items": low_stock[:5],
                "pending_payments": len(pending),
                "active_workers": len(workers)
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/live-inventory/{shop_id}")
async def get_live_inventory(shop_id: int, db: Session = Depends(get_db)):
    """Get live inventory status"""
    try:
        low_stock = RealtimeDataService.get_low_stock_products(db, shop_id, threshold=10)
        
        return {
            "status": "success",
            "low_stock_count": len(low_stock),
            "products": low_stock,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/live-workers/{shop_id}")
async def get_live_workers(shop_id: int, db: Session = Depends(get_db)):
    """Get active workers"""
    try:
        workers = RealtimeDataService.get_active_workers(db, shop_id)
        
        return {
            "status": "success",
            "active_count": len(workers),
            "workers": workers,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==================== NOTIFICATION ENDPOINTS ====================

@router.post("/notify-sale/{shop_id}")
async def notify_sale(shop_id: int, data: dict, background_tasks: BackgroundTasks):
    """
    Trigger sale notification
    
    Request:
    {
        "product": "Product Name",
        "quantity": 2,
        "amount": 500.00
    }
    """
    try:
        product = data.get("product", "Unknown")
        quantity = data.get("quantity", 1)
        amount = data.get("amount", 0)
        
        background_tasks.add_task(
            NotificationManager.send_sale_notification,
            manager, shop_id, product, quantity, amount
        )
        
        return {"status": "success", "message": "Sale notification sent"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/notify-stock/{shop_id}")
async def notify_stock(shop_id: int, data: dict, background_tasks: BackgroundTasks):
    """
    Trigger low stock alert
    
    Request:
    {
        "product": "Product Name",
        "stock": 5
    }
    """
    try:
        product = data.get("product", "Unknown")
        stock = data.get("stock", 0)
        
        background_tasks.add_task(
            NotificationManager.send_stock_alert,
            manager, shop_id, product, stock
        )
        
        return {"status": "success", "message": "Stock alert sent"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/notify-payment/{shop_id}")
async def notify_payment(shop_id: int, data: dict, background_tasks: BackgroundTasks):
    """
    Trigger payment received notification
    
    Request:
    {
        "amount": 500.00,
        "method": "UPI"
    }
    """
    try:
        amount = data.get("amount", 0)
        method = data.get("method", "Unknown")
        
        background_tasks.add_task(
            NotificationManager.send_payment_received,
            manager, shop_id, amount, method
        )
        
        return {"status": "success", "message": "Payment notification sent"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==================== DEMO ENDPOINTS ====================

@router.get("/live-dashboard-demo/{shop_id}", response_class=HTMLResponse)
async def live_dashboard_demo(shop_id: int):
    """
    Live dashboard demo page
    Visit: http://localhost:8000/api/live-dashboard-demo/1
    
    Shows real-time updates in browser
    """
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Live Dashboard</title>
        <style>
            body {{ font-family: Arial; margin: 20px; background: #f5f5f5; }}
            .container {{ max-width: 1200px; margin: 0 auto; }}
            .card {{ background: white; padding: 20px; margin: 10px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
            .metric {{ display: inline-block; width: 23%; margin: 1%; background: #f9f9f9; padding: 15px; border-radius: 5px; text-align: center; border-left: 4px solid #1976D2; }}
            .metric h3 {{ margin: 0; color: #333; }}
            .metric .value {{ font-size: 28px; color: #1976D2; margin: 10px 0; }}
            .metric .label {{ color: #666; font-size: 12px; }}
            .alert {{ padding: 10px; margin: 5px 0; border-radius: 4px; }}
            .alert.high {{ background: #ffebee; color: #c62828; border-left: 4px solid #c62828; }}
            .alert.info {{ background: #e3f2fd; color: #1565c0; border-left: 4px solid #1565c0; }}
            .alert.success {{ background: #e8f5e9; color: #2e7d32; border-left: 4px solid #2e7d32; }}
            h1 {{ color: #333; }}
            h2 {{ margin-top: 30px; color: #555; border-bottom: 2px solid #1976D2; padding-bottom: 10px; }}
            .timestamp {{ color: #999; font-size: 12px; }}
            table {{ width: 100%; border-collapse: collapse; }}
            th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
            th {{ background: #f5f5f5; font-weight: bold; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🚀 Live Dashboard - Shop #{shop_id}</h1>
            
            <div style="margin-bottom: 20px;">
                <button onclick="connectWebSocket()">🔗 Connect WebSocket</button>
                <button onclick="fetchLiveData()">📊 Fetch Live Data</button>
                <button onclick="sendTestNotification()">🔔 Test Notification</button>
                <span class="timestamp">Status: <span id="status">Disconnected</span></span>
            </div>
            
            <div class="card">
                <h2>📈 Today's Metrics</h2>
                <div id="metrics" style="margin: 20px 0;">
                    <div class="metric">
                        <div class="label">Sales</div>
                        <div class="value" id="sales">-</div>
                    </div>
                    <div class="metric">
                        <div class="label">Revenue</div>
                        <div class="value" id="revenue">₹-</div>
                    </div>
                    <div class="metric">
                        <div class="label">Transactions</div>
                        <div class="value" id="transactions">-</div>
                    </div>
                    <div class="metric">
                        <div class="label">Active Customers</div>
                        <div class="value" id="customers">-</div>
                    </div>
                </div>
            </div>
            
            <div class="card">
                <h2>⚠️ Low Stock Alerts</h2>
                <div id="alerts" style="max-height: 300px; overflow-y: auto;">
                    <p style="color: #999;">No alerts</p>
                </div>
            </div>
            
            <div class="card">
                <h2>💰 Recent Sales</h2>
                <table id="salesTable">
                    <thead>
                        <tr>
                            <th>Product</th>
                            <th>Qty</th>
                            <th>Amount</th>
                            <th>Time</th>
                        </tr>
                    </thead>
                    <tbody id="salesBody">
                        <tr><td colspan="4" style="text-align: center; color: #999;">No sales yet</td></tr>
                    </tbody>
                </table>
            </div>
            
            <div class="card">
                <h2>👥 Active Workers</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Worker</th>
                            <th>Check-In</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody id="workersBody">
                        <tr><td colspan="3" style="text-align: center; color: #999;">No workers checked in</td></tr>
                    </tbody>
                </table>
            </div>
        </div>

        <script>
            let ws = null;
            const shopId = {shop_id};
            const userId = 1; // Mock user ID
            
            function connectWebSocket() {{
                ws = new WebSocket(`ws://${{window.location.host}}/api/ws/live/${{userId}}/${{shopId}}`);
                
                ws.onopen = () => {{
                    document.getElementById('status').textContent = '✅ Connected';
                    document.getElementById('status').style.color = '#4caf50';
                    
                    // Subscribe to all channels
                    ws.send(JSON.stringify({{ action: 'subscribe', channel: 'all' }}));
                    console.log('Connected to WebSocket');
                }};
                
                ws.onmessage = (event) => {{
                    const data = JSON.parse(event.data);
                    console.log('Received:', data);
                    
                    if (data.type === 'metrics_update') {{
                        updateMetrics(data.data);
                    }} else if (data.type === 'inventory_update') {{
                        updateAlerts(data.data);
                    }} else if (data.type === 'sales_update') {{
                        updateSales(data.data);
                    }} else if (data.type === 'worker_status') {{
                        updateWorkers(data.data);
                    }} else if (data.type === 'new_sale') {{
                        showNotification(data.message, 'success');
                    }} else if (data.type === 'stock_alert') {{
                        showNotification(data.message, 'high');
                    }}
                }};
                
                ws.onerror = () => {{
                    document.getElementById('status').textContent = '❌ Error';
                    document.getElementById('status').style.color = '#f44336';
                }};
                
                ws.onclose = () => {{
                    document.getElementById('status').textContent = '❌ Disconnected';
                    document.getElementById('status').style.color = '#f44336';
                }};
            }}
            
            function fetchLiveData() {{
                fetch(`/api/live-metrics/${{shopId}}`)
                    .then(r => r.json())
                    .then(d => {{
                        updateMetrics(d.metrics);
                        updateAlerts(d.alerts.low_stock_items);
                        console.log('Live data fetched');
                    }});
            }}
            
            function updateMetrics(data) {{
                document.getElementById('sales').textContent = data.items_sold || '-';
                document.getElementById('revenue').textContent = '₹' + (data.revenue || 0).toFixed(0);
                document.getElementById('transactions').textContent = data.transactions || '-';
                document.getElementById('customers').textContent = data.active_customers || '-';
            }}
            
            function updateAlerts(alerts) {{
                const html = alerts.length > 0
                    ? alerts.map(a => `
                        <div class="alert {{{{ a.alert === 'URGENT' ? 'high' : 'info' }}}}">
                            <strong>${{a.name}}</strong> - Stock: ${{a.current_stock}} (Reorder: ${{a.reorder_level}})
                        </div>
                    `).join('')
                    : '<p style="color: #999;">✅ All items in stock</p>';
                
                document.getElementById('alerts').innerHTML = html;
            }}
            
            function updateSales(sales) {{
                const html = sales.slice(0, 5).map(s => `
                    <tr>
                        <td>${{s.product}}</td>
                        <td>${{s.quantity}}</td>
                        <td>₹${{s.total.toFixed(0)}}</td>
                        <td>${{new Date(s.timestamp).toLocaleTimeString()}}</td>
                    </tr>
                `).join('');
                
                document.getElementById('salesBody').innerHTML = html || 
                    '<tr><td colspan="4" style="text-align: center; color: #999;">No sales</td></tr>';
            }}
            
            function updateWorkers(workers) {{
                const html = workers.map(w => `
                    <tr>
                        <td>${{w.name}}</td>
                        <td>${{new Date(w.check_in).toLocaleTimeString()}}</td>
                        <td>✅ Present</td>
                    </tr>
                `).join('');
                
                document.getElementById('workersBody').innerHTML = html ||
                    '<tr><td colspan="3" style="text-align: center; color: #999;">No workers</td></tr>';
            }}
            
            function sendTestNotification() {{
                fetch(`/api/notify-sale/${{shopId}}`, {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{
                        product: 'Test Product',
                        quantity: 2,
                        amount: 500
                    }})
                }}).then(() => alert('Test notification sent!'));
            }}
            
            function showNotification(message, type) {{
                const div = document.createElement('div');
                div.className = `alert ${{type}}`;
                div.textContent = '🔔 ' + message;
                document.getElementById('alerts').insertBefore(div, document.getElementById('alerts').firstChild);
                setTimeout(() => div.remove(), 5000);
            }}
            
            // Auto-connect on load
            window.onload = () => {{
                fetchLiveData();
                connectWebSocket();
            }};
        </script>
    </body>
    </html>
    """
