# models.py
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, create_engine, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
import os
from datetime import datetime

Base = declarative_base()

class Bucket(Base):
    __tablename__ = 'buckets'
    
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Many-to-many relationship with instruments
    instruments = relationship(
        "Instrument", 
        secondary="bucket_instruments",
        back_populates="buckets"
    )
    
    def __repr__(self):
        return f"<Bucket(name='{self.name}')>"

# Association table for the many-to-many relationship
bucket_instruments = Table(
    'bucket_instruments',
    Base.metadata,
    Column('bucket_id', Integer, ForeignKey('buckets.id'), primary_key=True),
    Column('instrument_id', Integer, ForeignKey('instruments.id'), primary_key=True)
)

class Instrument(Base):
    __tablename__ = 'instruments'
    
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    trades = relationship("Trade", back_populates="instrument", cascade="all, delete-orphan")
     # Add this new relationship
    buckets = relationship(
        "Bucket",
        secondary="bucket_instruments",
        back_populates="instruments"
    )
    
    def __repr__(self):
        return f"<Instrument(name='{self.name}')>"

class Trade(Base):
    __tablename__ = 'trades'
    
    id = Column(Integer, primary_key=True)
    trade_number = Column(Integer, nullable=False)
    instrument_id = Column(Integer, ForeignKey('instruments.id'), nullable=False)
    
    # Common to both entry and exit
    contracts = Column(Integer, nullable=False)
    profit_inr = Column(Float, nullable=True)
    profit_percentage = Column(Float, nullable=True)
    cumulative_profit_inr = Column(Float, nullable=True)
    cumulative_profit_percentage = Column(Float, nullable=True)
    run_up_inr = Column(Float, nullable=True)
    run_up_percentage = Column(Float, nullable=True)
    drawdown_inr = Column(Float, nullable=True)
    drawdown_percentage = Column(Float, nullable=True)
    
    # Entry details
    entry_type = Column(String, nullable=False)  # Long or Short
    entry_signal = Column(String, nullable=False)
    entry_datetime = Column(DateTime, nullable=False)
    entry_price = Column(Float, nullable=False)
    
    # Exit details
    exit_type = Column(String, nullable=True)
    exit_signal = Column(String, nullable=True)
    exit_datetime = Column(DateTime, nullable=True)
    exit_price = Column(Float, nullable=True)
    
    # Calculated fields
    holding_time_hours = Column(Float, nullable=True)
    
    instrument = relationship("Instrument", back_populates="trades")
    
    def __repr__(self):
        return f"<Trade(number={self.trade_number}, instrument='{self.instrument.name}')>"