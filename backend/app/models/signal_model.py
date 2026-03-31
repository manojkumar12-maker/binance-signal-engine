from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class SignalResponse(BaseModel):
    pair: str
    signal: str
    entry: float
    sl: float
    tp1: float
    tp2: float
    tp3: float
    confidence: int
    trend: str
    liquidity: Optional[str]
    volume: bool
    timestamp: datetime


class HealthResponse(BaseModel):
    status: str
    app: str
