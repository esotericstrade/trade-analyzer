# database.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool
from dotenv import load_dotenv
from models import Base

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://username:password@localhost/trade_analyzer")

# Configure engine with connection pooling parameters similar to your Java example
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=2,                 # Minimum idle connections (equivalent to minimumIdle=2)
    max_overflow=3,              # Additional connections allowed, making total max=5
    pool_timeout=30,             # Connection timeout after 30 seconds (equivalent to connectionTimeout)
    pool_recycle=1800,           # Recycle connections after 30 minutes (equivalent to maxLifetime)
    pool_pre_ping=True           # Test connections before using (similar to connection validation)
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    Base.metadata.create_all(bind=engine)