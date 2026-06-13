from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime


class TransactionBase(BaseModel):
    buyer: str
    seller: str
    price_sek: Optional[float] = None
    price_text: Optional[str] = None
    property_type: str
    property_designation: Optional[str] = None
    address: Optional[str] = None
    municipality: Optional[str] = None
    county: Optional[str] = None
    transaction_date: Optional[date] = None
    access_date: Optional[date] = None
    source_name: Optional[str] = None
    source_url: Optional[str] = None
    summary: Optional[str] = None
    market_comment: Optional[str] = None
    area_sqm: Optional[float] = None
    residential_units: Optional[int] = None
    tenants: Optional[str] = None
    yield_percent: Optional[float] = None
    portfolio_flag: bool = False
    confidence_score: Optional[float] = None
    raw_text: Optional[str] = None


class TransactionCreate(TransactionBase):
    pass


class Transaction(TransactionBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
