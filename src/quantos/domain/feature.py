"""Feature vector domain."""

from datetime import datetime
from typing import Dict, Any, Optional
from pydantic import BaseModel

class FeatureVector(BaseModel):
    symbol: str
    timestamp: datetime
    version: str
    features: Dict[str, float]
    class Config:
        allow_mutation = False
        frozen = True