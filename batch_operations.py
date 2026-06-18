"""
Batch Operations System
Bulk import, export, and update functionality with progress tracking
"""

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, Float, DateTime, JSON
from sqlalchemy.sql import func
from db import Base, get_db
from pydantic import BaseModel
from datetime import datetime
import csv
import json
from typing import List, Optional, Any
import logging

logger = logging.getLogger(__name__)


class BatchOperation(Base):
    """Track batch operations"""
    __tablename__ = "batch_operations"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    operation_type = Column(String(50), nullable=False)  # IMPORT, EXPORT, UPDATE, DELETE
    entity_type = Column(String(50), nullable=False)     # PRODUCT, CUSTOMER, SALE, etc.
    status = Column(String(50), default="PROCESSING")    # PROCESSING, COMPLETED, FAILED
    total_records = Column(Integer, default=0)
    processed_records = Column(Integer, default=0)
    failed_records = Column(Integer, default=0)
    errors = Column(JSON, nullable=True)
    started_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime, nullable=True)
    metadata = Column(JSON, nullable=True)
    
    def to_dict(self):
        return {
            "id": self.id,
            "operation_type": self.operation_type,
            "entity_type": self.entity_type,
            "status": self.status,
            "total_records": self.total_records,
            "processed_records": self.processed_records,
            "failed_records": self.failed_records,
            "progress_percent": round((self.processed_records / max(self.total_records, 1)) * 100),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


# ====================== REQUEST/RESPONSE MODELS ======================

class BulkProductImportRequest(BaseModel):
    """Bulk product import request"""
    products: List[dict]
    overwrite: bool = False


class BulkProductExportResponse(BaseModel):
    """Bulk product export response"""
    operation_id: int
    status: str
    total_records: int
    download_url: str


class BatchOperationStatus(BaseModel):
    """Batch operation status response"""
    operation_id: int
    status: str
    progress_percent: int
    processed: int
    total: int
    errors: List[str] = []


# ====================== BATCH OPERATIONS ROUTER ======================

router = APIRouter(prefix="/api/batch", tags=["Batch Operations"])


@router.post("/products/import")
async def bulk_import_products(
    user_id: int,
    file: UploadFile = File(...),
    overwrite: bool = False,
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = None
):
    """
    Bulk import products from CSV file
    
    CSV Format:
        product_name, sku, description, current_stock, unit_price, category
    """
    try:
        # Create batch operation record
        batch_op = BatchOperation(
            user_id=user_id,
            operation_type="IMPORT",
            entity_type="PRODUCT",
            status="PROCESSING"
        )
        db.add(batch_op)
        db.commit()
        
        # Parse CSV
        content = await file.read()
        lines = content.decode('utf-8').split('\n')
        reader = csv.DictReader(lines)
        
        batch_op.total_records = len(lines) - 1  # Exclude header
        
        # Process in background
        if background_tasks:
            background_tasks.add_task(
                _process_product_import,
                db,
                batch_op.id,
                user_id,
                reader,
                overwrite
            )
        
        db.commit()
        
        return {
            "operation_id": batch_op.id,
            "status": "PROCESSING",
            "total_records": batch_op.total_records,
            "message": "Import started, check status with /batch/status/{operation_id}"
        }
    
    except Exception as e:
        logger.error(f"Import failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/products/export")
async def bulk_export_products(
    user_id: int,
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = None
):
    """Export all products to CSV"""
    try:
        from models import Product
        
        # Create batch operation record
        batch_op = BatchOperation(
            user_id=user_id,
            operation_type="EXPORT",
            entity_type="PRODUCT",
            status="PROCESSING"
        )
        db.add(batch_op)
        db.commit()
        
        # Get total count
        total = db.query(Product).filter(Product.user_id == user_id).count()
        batch_op.total_records = total
        
        # Process in background
        if background_tasks:
            background_tasks.add_task(
                _process_product_export,
                db,
                batch_op.id,
                user_id
            )
        
        db.commit()
        
        return {
            "operation_id": batch_op.id,
            "status": "PROCESSING",
            "total_records": total,
            "message": "Export started, check status with /batch/status/{operation_id}"
        }
    
    except Exception as e:
        logger.error(f"Export failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/customers/import")
async def bulk_import_customers(
    user_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = None
):
    """
    Bulk import customers from CSV file
    
    CSV Format:
        customer_name, email, phone, address, city
    """
    try:
        batch_op = BatchOperation(
            user_id=user_id,
            operation_type="IMPORT",
            entity_type="CUSTOMER",
            status="PROCESSING"
        )
        db.add(batch_op)
        db.commit()
        
        content = await file.read()
        lines = content.decode('utf-8').split('\n')
        reader = csv.DictReader(lines)
        
        batch_op.total_records = len(lines) - 1
        db.commit()
        
        if background_tasks:
            background_tasks.add_task(
                _process_customer_import,
                db,
                batch_op.id,
                user_id,
                reader
            )
        
        return {
            "operation_id": batch_op.id,
            "status": "PROCESSING",
            "total_records": batch_op.total_records
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/status/{operation_id}")
async def get_batch_status(
    operation_id: int,
    db: Session = Depends(get_db)
):
    """Get status of batch operation"""
    batch_op = db.query(BatchOperation).filter(
        BatchOperation.id == operation_id
    ).first()
    
    if not batch_op:
        raise HTTPException(status_code=404, detail="Operation not found")
    
    return batch_op.to_dict()


@router.get("/history")
async def get_batch_history(
    user_id: int,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get batch operation history for user"""
    operations = db.query(BatchOperation).filter(
        BatchOperation.user_id == user_id
    ).order_by(
        BatchOperation.started_at.desc()
    ).limit(limit).all()
    
    return [op.to_dict() for op in operations]


# ====================== BACKGROUND PROCESSORS ======================

def _process_product_import(
    db: Session,
    operation_id: int,
    user_id: int,
    reader,
    overwrite: bool
):
    """Process product import in background"""
    from models import Product
    
    try:
        batch_op = db.query(BatchOperation).filter(
            BatchOperation.id == operation_id
        ).first()
        
        failed_items = []
        
        for idx, row in enumerate(reader):
            try:
                # Skip empty rows
                if not row.get('product_name'):
                    continue
                
                # Check if product exists
                existing = db.query(Product).filter(
                    Product.sku == row.get('sku'),
                    Product.user_id == user_id
                ).first()
                
                if existing and not overwrite:
                    failed_items.append({
                        "row": idx,
                        "error": f"Product {row.get('sku')} already exists"
                    })
                    batch_op.failed_records += 1
                    continue
                
                # Create or update product
                if existing and overwrite:
                    existing.product_name = row.get('product_name')
                    existing.description = row.get('description')
                    existing.current_stock = int(row.get('current_stock', 0))
                    existing.unit_price = float(row.get('unit_price', 0))
                    existing.category = row.get('category')
                else:
                    product = Product(
                        user_id=user_id,
                        product_name=row.get('product_name'),
                        sku=row.get('sku'),
                        description=row.get('description'),
                        current_stock=int(row.get('current_stock', 0)),
                        unit_price=float(row.get('unit_price', 0)),
                        category=row.get('category')
                    )
                    db.add(product)
                
                batch_op.processed_records += 1
            
            except Exception as e:
                failed_items.append({
                    "row": idx,
                    "error": str(e)
                })
                batch_op.failed_records += 1
        
        db.commit()
        
        batch_op.status = "COMPLETED"
        batch_op.completed_at = datetime.now()
        batch_op.errors = failed_items[:10]  # Store first 10 errors
        
    except Exception as e:
        batch_op.status = "FAILED"
        batch_op.errors = [{"error": str(e)}]
        logger.error(f"Product import failed: {e}")
    
    finally:
        db.commit()


def _process_product_export(
    db: Session,
    operation_id: int,
    user_id: int
):
    """Process product export in background"""
    from models import Product
    
    try:
        batch_op = db.query(BatchOperation).filter(
            BatchOperation.id == operation_id
        ).first()
        
        products = db.query(Product).filter(
            Product.user_id == user_id
        ).all()
        
        # Create CSV
        import csv
        from io import StringIO
        
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            'product_name', 'sku', 'description', 'current_stock',
            'min_stock', 'unit_price', 'category'
        ])
        
        # Write products
        for product in products:
            writer.writerow([
                product.product_name,
                product.sku,
                product.description or '',
                product.current_stock,
                product.min_stock,
                float(product.unit_price),
                product.category or ''
            ])
            batch_op.processed_records += 1
        
        batch_op.status = "COMPLETED"
        batch_op.completed_at = datetime.now()
        batch_op.metadata = {
            "file_size": len(output.getvalue()),
            "export_timestamp": datetime.now().isoformat()
        }
    
    except Exception as e:
        batch_op.status = "FAILED"
        batch_op.errors = [{"error": str(e)}]
        logger.error(f"Product export failed: {e}")
    
    finally:
        db.commit()


def _process_customer_import(
    db: Session,
    operation_id: int,
    user_id: int,
    reader
):
    """Process customer import in background"""
    from models import Customer
    
    try:
        batch_op = db.query(BatchOperation).filter(
            BatchOperation.id == operation_id
        ).first()
        
        failed_items = []
        
        for idx, row in enumerate(reader):
            try:
                customer = Customer(
                    user_id=user_id,
                    customer_name=row.get('customer_name'),
                    email=row.get('email'),
                    phone=row.get('phone'),
                    address=row.get('address'),
                    city=row.get('city')
                )
                db.add(customer)
                batch_op.processed_records += 1
            
            except Exception as e:
                failed_items.append({"row": idx, "error": str(e)})
                batch_op.failed_records += 1
        
        db.commit()
        
        batch_op.status = "COMPLETED"
        batch_op.completed_at = datetime.now()
        batch_op.errors = failed_items[:10]
    
    except Exception as e:
        batch_op.status = "FAILED"
        logger.error(f"Customer import failed: {e}")
    
    finally:
        db.commit()
