"""
models.py
---------
Pydantic models used for:
  - Request body validation  (what the API accepts)
  - Response serialization   (what the API returns)

Pydantic v2 is bundled with FastAPI; all models inherit from BaseModel.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


# ── Enum for the three supported dataset actions ───────────────────────────
class ActionType(str, Enum):
    UPLOAD = "UPLOAD"
    MODIFY = "MODIFY"
    ACCESS = "ACCESS"


# ── Risk level labels derived from the trust score ────────────────────────
class RiskLevel(str, Enum):
    HIGH_TRUST   = "High Trust"
    MEDIUM_TRUST = "Medium Trust"
    LOW_RISK     = "Low Trust / Risky"


# ══════════════════════════════════════════════════════════════════════════
#  REQUEST BODIES
# ══════════════════════════════════════════════════════════════════════════

class UploadRequest(BaseModel):
    """Body for POST /upload — registers a new dataset in the ledger."""
    dataset_id: str = Field(..., example="DS-GOV-2024-001",
                            description="Unique identifier for the dataset")
    source: Optional[str] = Field(None, example="Ministry of Finance",
                                  description="Origin / provider of the dataset")


class ModifyRequest(BaseModel):
    """Body for POST /modify — records a transformation on an existing dataset."""
    dataset_id: str = Field(..., example="DS-GOV-2024-001")


class AccessRequest(BaseModel):
    """Body for POST /access — logs a read/consumption event."""
    dataset_id: str = Field(..., example="DS-GOV-2024-001")


# ══════════════════════════════════════════════════════════════════════════
#  RESPONSE SHAPES
# ══════════════════════════════════════════════════════════════════════════

class LedgerBlock(BaseModel):
    """
    Represents a single immutable block in the chain.
    Returned inside history responses.
    """
    dataset_id:    str
    action:        ActionType
    source:        Optional[str] = None
    timestamp:     str
    previous_hash: str
    current_hash:  str


class HistoryResponse(BaseModel):
    """Full provenance chain for one dataset."""
    dataset_id: str
    total_blocks: int
    chain: List[LedgerBlock]


class TrustScoreResponse(BaseModel):
    """Trust score + breakdown for one dataset."""
    dataset_id:       str
    trust_score:      float = Field(..., ge=0, le=100)
    risk_level:       RiskLevel
    source_score:     float
    modification_penalty: float
    access_bonus:     float
    total_blocks:     int


class ActionResponse(BaseModel):
    """Generic success response returned after UPLOAD / MODIFY / ACCESS."""
    message:      str
    dataset_id:   str
    current_hash: str