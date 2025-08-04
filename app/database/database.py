from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from pathlib import Path

# Create database directory if it doesn't exist
db_dir = Path("database")
db_dir.mkdir(exist_ok=True)

# Database URL - use environment variable for production
raw_database_url = os.getenv(
    "DATABASE_URL", 
    "sqlite:///./database/finance_assistant.db"
)

# Clean the DATABASE_URL by removing any surrounding quotes
SQLALCHEMY_DATABASE_URL = raw_database_url.strip().strip('"').strip("'")

# Convert postgres:// to postgresql:// for SQLAlchemy compatibility
if SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Determine if we're using PostgreSQL or SQLite
is_postgres = SQLALCHEMY_DATABASE_URL.startswith("postgresql")

# Configure connection arguments based on database type
if is_postgres:
    # PostgreSQL configuration
    connect_args = {}
    # Add database name if not specified
    if "/finance_assistant" not in SQLALCHEMY_DATABASE_URL and "?" not in SQLALCHEMY_DATABASE_URL:
        SQLALCHEMY_DATABASE_URL += "/finance_assistant"
    elif "/finance_assistant" not in SQLALCHEMY_DATABASE_URL and "?" in SQLALCHEMY_DATABASE_URL:
        # Insert database name before query parameters
        base_url, query = SQLALCHEMY_DATABASE_URL.split("?", 1)
        SQLALCHEMY_DATABASE_URL = f"{base_url}/finance_assistant?{query}"
    
    # Configure SSL based on host
    if "127.0.0.1" in SQLALCHEMY_DATABASE_URL or "localhost" in SQLALCHEMY_DATABASE_URL:
        # Local development through proxy - disable SSL
        if "sslmode=" not in SQLALCHEMY_DATABASE_URL:
            if "?" in SQLALCHEMY_DATABASE_URL:
                SQLALCHEMY_DATABASE_URL += "&sslmode=disable"
            else:
                SQLALCHEMY_DATABASE_URL += "?sslmode=disable"
    else:
        # Direct Fly.io connection - require SSL
        if "sslmode=" not in SQLALCHEMY_DATABASE_URL:
            if "?" in SQLALCHEMY_DATABASE_URL:
                SQLALCHEMY_DATABASE_URL += "&sslmode=require"
            else:
                SQLALCHEMY_DATABASE_URL += "?sslmode=require"
else:
    # SQLite configuration
    connect_args = {"check_same_thread": False}

# Create engine
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args=connect_args,
    echo=True  # Set to False in production
)

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Base class
Base = declarative_base()


def get_db():
    """Dependency to get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database tables"""
    from .models import Base
    Base.metadata.create_all(bind=engine)
