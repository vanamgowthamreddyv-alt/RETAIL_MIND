from urllib.parse import quote_plus
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os
from dotenv import load_dotenv
from sqlalchemy.engine import URL

load_dotenv()

# Get database configuration from environment variables
# Render/Railway typically provides 'DATABASE_URL' automatically
database_url = os.getenv("DATABASE_URL")

if database_url:
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    
    print(f" Using provided DATABASE_URL for PostgreSQL connection.")
    engine = create_engine(
        database_url,
        future=True,
        pool_pre_ping=True,  # Test connection before using
        echo=False
    )
else:
    # Fallback to Render Database if DATABASE_URL is not provided
    # Fallback to Render Database if DATABASE_URL is not provided
        db_host = os.getenv("DB_HOST", "localhost")
    db_port = int(os.getenv("DB_PORT", "5432"))
    db_user = os.getenv("DB_USER", "postgres")
    db_password = os.getenv("DB_PASSWORD", "")
    db_name = os.getenv("DB_NAME", "postgres")

    print(f" PostgreSQL Configuration fallback:\n  Host: {db_host}:{db_port}")

    # Build connection URL
    url = URL.create(
        drivername="postgresql",
        username=db_user,
        password=db_password,
        host=db_host,
        port=db_port,
        database=db_name
    )

    engine = create_engine(
        url,
        future=True,
        pool_pre_ping=True,
        echo=False
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
sessionLocal = SessionLocal # Alias for legacy imports
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()



