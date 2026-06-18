"""
Backup & Recovery System
Automatic daily backups, restore functionality, point-in-time recovery
"""

import os
import json
import gzip
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, DateTime, Float, Boolean, Text
from sqlalchemy.sql import func
from db import Base, engine
import subprocess
import logging

logger = logging.getLogger(__name__)


class BackupRecord(Base):
    """Model to track backups"""
    __tablename__ = "backup_records"
    
    id = Column(Integer, primary_key=True)
    backup_name = Column(String(255), nullable=False, unique=True)
    backup_type = Column(String(50), default="FULL")  # FULL, INCREMENTAL
    backup_path = Column(String(500), nullable=False)
    backup_size_mb = Column(Float)
    total_records = Column(Integer)
    is_compressed = Column(Boolean, default=True)
    status = Column(String(50), default="COMPLETED")  # COMPLETED, FAILED, PENDING
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    expires_at = Column(DateTime)
    
    def to_dict(self):
        return {
            "id": self.id,
            "name": self.backup_name,
            "type": self.backup_type,
            "size_mb": self.backup_size_mb,
            "records": self.total_records,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


class BackupService:
    """Service for managing backups"""
    
    BACKUP_DIR = Path(os.getenv("BACKUP_DIR", "./backups"))
    RETENTION_DAYS = int(os.getenv("BACKUP_RETENTION_DAYS", "30"))
    ENABLE_COMPRESSION = os.getenv("ENABLE_BACKUP_COMPRESSION", "true").lower() == "true"
    
    @classmethod
    def ensure_backup_dir(cls):
        """Create backup directory if it doesn't exist"""
        cls.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    
    @classmethod
    def create_backup(
        cls,
        db: Session,
        backup_name: str = None,
        backup_type: str = "FULL"
    ) -> BackupRecord:
        """
        Create a database backup
        
        Args:
            db: Database session
            backup_name: Custom name for backup
            backup_type: FULL or INCREMENTAL
            
        Returns:
            BackupRecord with backup details
        """
        cls.ensure_backup_dir()
        
        try:
            # Generate backup name if not provided
            if not backup_name:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_name = f"backup_{backup_type.lower()}_{timestamp}"
            
            backup_path = cls.BACKUP_DIR / f"{backup_name}.sql"
            
            # Get database connection string from engine
            db_url = str(engine.url)
            
            # Backup using pg_dump (for PostgreSQL)
            if "postgresql" in db_url:
                backup_path = cls._backup_postgresql(db_url, backup_path)
            else:
                # SQLite fallback
                backup_path = cls._backup_sqlite(db, backup_path)
            
            # Compress if enabled
            if cls.ENABLE_COMPRESSION:
                compressed_path = cls._compress_backup(backup_path)
                backup_path.unlink()  # Remove original
                backup_path = compressed_path
            
            # Get backup file size
            backup_size_mb = backup_path.stat().st_size / (1024 * 1024)
            
            # Count records (rough estimate)
            total_records = cls._estimate_record_count(db)
            
            # Create backup record
            backup_record = BackupRecord(
                backup_name=backup_name,
                backup_type=backup_type,
                backup_path=str(backup_path),
                backup_size_mb=round(backup_size_mb, 2),
                total_records=total_records,
                is_compressed=cls.ENABLE_COMPRESSION,
                status="COMPLETED",
                expires_at=datetime.now() + timedelta(days=cls.RETENTION_DAYS)
            )
            
            db.add(backup_record)
            db.commit()
            
            logger.info(f"Backup created: {backup_name} ({backup_size_mb:.2f} MB)")
            return backup_record
        
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            
            # Record failed backup attempt
            backup_record = BackupRecord(
                backup_name=backup_name or "failed_backup",
                backup_type=backup_type,
                backup_path="",
                status="FAILED",
                error_message=str(e)
            )
            db.add(backup_record)
            db.commit()
            
            raise
    
    @classmethod
    def _backup_postgresql(cls, db_url: str, output_path: Path) -> Path:
        """Backup PostgreSQL database"""
        # Parse connection string
        import urllib.parse
        url = urllib.parse.urlparse(db_url)
        
        cmd = [
            "pg_dump",
            f"--host={url.hostname}",
            f"--port={url.port or 5432}",
            f"--username={url.username}",
            f"--dbname={url.path.lstrip('/')}",
            f"--file={output_path}",
            "--verbose"
        ]
        
        env = os.environ.copy()
        if url.password:
            env["PGPASSWORD"] = url.password
        
        subprocess.run(cmd, env=env, check=True)
        return output_path
    
    @classmethod
    def _backup_sqlite(cls, db: Session, output_path: Path) -> Path:
        """Backup SQLite database"""
        db_file = "./grocery_analytics.db"
        if os.path.exists(db_file):
            shutil.copy2(db_file, output_path)
        return output_path
    
    @classmethod
    def _compress_backup(cls, backup_path: Path) -> Path:
        """Compress backup file"""
        compressed_path = backup_path.with_suffix(backup_path.suffix + ".gz")
        
        with open(backup_path, 'rb') as f_in:
            with gzip.open(compressed_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        
        return compressed_path
    
    @classmethod
    def restore_backup(
        cls,
        db: Session,
        backup_id: int
    ) -> bool:
        """
        Restore from backup
        
        Args:
            db: Database session
            backup_id: ID of backup to restore
            
        Returns:
            True if successful
        """
        try:
            backup = db.query(BackupRecord).filter(
                BackupRecord.id == backup_id
            ).first()
            
            if not backup:
                raise ValueError(f"Backup {backup_id} not found")
            
            backup_path = Path(backup.backup_path)
            
            if not backup_path.exists():
                raise FileNotFoundError(f"Backup file not found: {backup_path}")
            
            # Decompress if needed
            if backup_path.suffix == ".gz":
                decomp_path = backup_path.with_suffix("")
                with gzip.open(backup_path, 'rb') as f_in:
                    with open(decomp_path, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                backup_path = decomp_path
            
            # Restore based on database type
            db_url = str(engine.url)
            if "postgresql" in db_url:
                cls._restore_postgresql(db_url, backup_path)
            else:
                cls._restore_sqlite(backup_path)
            
            logger.info(f"Backup restored: {backup.backup_name}")
            return True
        
        except Exception as e:
            logger.error(f"Restore failed: {e}")
            raise
    
    @classmethod
    def _restore_postgresql(cls, db_url: str, backup_path: Path):
        """Restore PostgreSQL database"""
        import urllib.parse
        url = urllib.parse.urlparse(db_url)
        
        cmd = [
            "psql",
            f"--host={url.hostname}",
            f"--port={url.port or 5432}",
            f"--username={url.username}",
            f"--dbname={url.path.lstrip('/')}",
            f"--file={backup_path}",
        ]
        
        env = os.environ.copy()
        if url.password:
            env["PGPASSWORD"] = url.password
        
        subprocess.run(cmd, env=env, check=True)
    
    @classmethod
    def _restore_sqlite(cls, backup_path: Path):
        """Restore SQLite database"""
        db_file = "./grocery_analytics.db"
        shutil.copy2(backup_path, db_file)
    
    @classmethod
    def _estimate_record_count(cls, db: Session) -> int:
        """Estimate total records in database"""
        try:
            from models import User, Product, sales, Invoice
            
            count = 0
            count += db.query(User).count()
            count += db.query(Product).count()
            count += db.query(sales).count()
            count += db.query(Invoice).count()
            
            return count
        except:
            return 0
    
    @classmethod
    def cleanup_old_backups(cls, db: Session):
        """Remove backups older than retention period"""
        try:
            expired_backups = db.query(BackupRecord).filter(
                BackupRecord.expires_at < datetime.now()
            ).all()
            
            for backup in expired_backups:
                # Delete file
                if Path(backup.backup_path).exists():
                    Path(backup.backup_path).unlink()
                
                # Delete record
                db.delete(backup)
            
            db.commit()
            logger.info(f"Cleaned up {len(expired_backups)} old backups")
        
        except Exception as e:
            logger.error(f"Backup cleanup failed: {e}")
    
    @classmethod
    def get_all_backups(cls, db: Session) -> list:
        """Get list of all backups"""
        return db.query(BackupRecord).order_by(
            BackupRecord.created_at.desc()
        ).all()
    
    @classmethod
    def get_backup_status(cls, db: Session) -> dict:
        """Get backup system status"""
        backups = cls.get_all_backups(db)
        
        total_size = sum(b.backup_size_mb for b in backups if b.backup_size_mb)
        
        return {
            "total_backups": len(backups),
            "total_size_mb": round(total_size, 2),
            "latest_backup": backups[0].created_at.isoformat() if backups else None,
            "retention_days": cls.RETENTION_DAYS,
            "compression_enabled": cls.ENABLE_COMPRESSION
        }


# ====================== BACKUP SCHEDULER ======================

from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()

def scheduled_backup():
    """Run scheduled backup"""
    from main import sessionLocal
    db = sessionLocal()
    try:
        BackupService.create_backup(db, backup_type="FULL")
        BackupService.cleanup_old_backups(db)
    except Exception as e:
        logger.error(f"Scheduled backup failed: {e}")
    finally:
        db.close()

def start_backup_scheduler():
    """Start background backup scheduler"""
    try:
        scheduler.add_job(
            scheduled_backup,
            'cron',
            hour=2,  # 2 AM daily
            id='daily_backup'
        )
        scheduler.start()
        logger.info("Backup scheduler started (daily at 2 AM)")
    except Exception as e:
        logger.warning(f"Backup scheduler start failed: {e}")
