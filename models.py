from sqlalchemy import Column, Integer, String, Float, Boolean, Text, DateTime, Date
from sqlalchemy.sql import func
from database import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    buyer = Column(String(255), nullable=False)
    seller = Column(String(255), nullable=False)
    price_sek = Column(Float, nullable=True)
    price_text = Column(String(255), nullable=True)
    property_type = Column(String(100), nullable=False)
    property_designation = Column(String(255), nullable=True)
    address = Column(String(255), nullable=True)
    municipality = Column(String(100), nullable=True)
    county = Column(String(100), nullable=True)
    transaction_date = Column(Date, nullable=True)
    access_date = Column(Date, nullable=True)
    source_name = Column(String(255), nullable=True)
    source_url = Column(String(500), nullable=True)
    summary = Column(Text, nullable=True)
    market_comment = Column(Text, nullable=True)
    area_sqm = Column(Float, nullable=True)
    residential_units = Column(Integer, nullable=True)
    tenants = Column(Text, nullable=True)
    yield_percent = Column(Float, nullable=True)
    portfolio_flag = Column(Boolean, default=False)
    confidence_score = Column(Float, nullable=True)
    raw_text = Column(Text, nullable=True)
