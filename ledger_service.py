"""
ledger_service.py
-----------------
Core business logic for the blockchain-inspired ledger.

Responsibilities:
  1. generate_hash        – SHA-256 fingerprint of a block's contents
  2. get_last_hash        – retrieve the tail hash of a dataset's chain
  3. create_block         – append a new immutable block to the chain
  4. get_history          – return the full ordered chain for a dataset
  5. calculate_trust_score – dynamic 0-100 scoring of dataset reliability
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from database import db
from models import ActionType, RiskLevel, TrustScoreResponse, LedgerBlock, HistoryResponse

# MongoDB collection alias for convenience
ledger_col = db["ledger"]


# ══════════════════════════════════════════════════════════════════════════
#  1.  HASHING
# ══════════════════════════════════════════════════════════════════════════

def generate_hash(data: dict) -> str:
    """
    Produce a deterministic SHA-256 hex digest from a dictionary.

    The dict is serialised with sorted keys so that identical logical data
    always produces the same hash regardless of insertion order.
    """
    raw = json.dumps(data, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


# ══════════════════════════════════════════════════════════════════════════
#  2.  CHAIN TAIL LOOKUP
# ══════════════════════════════════════════════════════════════════════════

def get_last_hash(dataset_id: str) -> str:
    """
    Fetch the `current_hash` of the most-recently inserted block for a
    given dataset.  Returns the genesis sentinel ("0" * 64) when no blocks
    exist yet — this is the conventional "nothing before me" value used in
    many blockchain implementations.
    """
    last_block = ledger_col.find_one(
        {"dataset_id": dataset_id},
        sort=[("timestamp", -1)]          # most recent first
    )
    if last_block is None:
        return "0" * 64                   # genesis / origin hash
    return last_block["current_hash"]


# ══════════════════════════════════════════════════════════════════════════
#  3.  BLOCK CREATION
# ══════════════════════════════════════════════════════════════════════════

def create_block(dataset_id: str, action: ActionType, source: Optional[str] = None) -> dict:
    """
    Build and persist a new ledger block, chained to the previous one.

    Block anatomy
    -------------
    dataset_id    – which dataset this event belongs to
    action        – UPLOAD | MODIFY | ACCESS
    source        – data origin (meaningful only for UPLOAD blocks)
    timestamp     – UTC ISO-8601 string; used as part of the hash input
    previous_hash – hash of the immediately preceding block (chain link)
    current_hash  – SHA-256 of all the above fields together

    Immutability guarantee
    ----------------------
    Because `current_hash` incorporates `previous_hash`, altering any
    historical block invalidates every subsequent hash — the chain "breaks"
    and tampering becomes immediately detectable.
    """
    previous_hash = get_last_hash(dataset_id)
    timestamp     = datetime.now(timezone.utc).isoformat()

    # The payload that gets hashed (order doesn't matter — sort_keys handles it)
    block_data = {
        "dataset_id":    dataset_id,
        "action":        action.value,
        "source":        source or "",
        "timestamp":     timestamp,
        "previous_hash": previous_hash,
    }

    current_hash = generate_hash(block_data)

    # Full MongoDB document
    block = {
        **block_data,
        "current_hash": current_hash,
    }

    ledger_col.insert_one(block)

    # Remove the internal MongoDB `_id` before returning
    block.pop("_id", None)
    return block


# ══════════════════════════════════════════════════════════════════════════
#  4.  HISTORY RETRIEVAL
# ══════════════════════════════════════════════════════════════════════════

def get_history(dataset_id: str) -> HistoryResponse:
    """
    Return every block for `dataset_id`, ordered chronologically
    (oldest → newest).  Raises 404 if the dataset has never been seen.
    """
    raw_blocks = list(
        ledger_col.find(
            {"dataset_id": dataset_id},
            {"_id": 0}                    # exclude MongoDB internal id
        ).sort("timestamp", 1)            # ascending → chronological order
    )

    if not raw_blocks:
        raise HTTPException(
            status_code=404,
            detail=f"Dataset '{dataset_id}' not found in ledger."
        )

    chain = [LedgerBlock(**b) for b in raw_blocks]

    return HistoryResponse(
        dataset_id   = dataset_id,
        total_blocks = len(chain),
        chain        = chain,
    )


# ══════════════════════════════════════════════════════════════════════════
#  5.  TRUST SCORE CALCULATION
# ══════════════════════════════════════════════════════════════════════════

# Keywords that signal a trustworthy, authoritative data source
TRUSTED_SOURCE_KEYWORDS = [
    "government", "ministry", "department", "agency",
    "national", "federal", "state", "official",
    "census", "statistics", "treasury", "defence", "health",
]

def _source_reliability_score(blocks: list) -> float:
    """
    Score the dataset's declared source (taken from its UPLOAD block).

    Logic
    -----
    - Locate the first UPLOAD block and inspect its `source` field.
    - If the source matches any trusted keyword → full 40 points.
    - If the source is non-empty but unrecognised              → 20 points.
    - If the source is missing / empty                         →  5 points.

    40 points is the maximum contribution from this factor.
    """
    upload_block = next(
        (b for b in blocks if b["action"] == ActionType.UPLOAD.value), None
    )
    if upload_block is None:
        return 5.0                        # no upload record at all

    source = (upload_block.get("source") or "").lower()

    if not source:
        return 5.0

    # Check whether any trusted keyword appears anywhere in the source string
    if any(keyword in source for keyword in TRUSTED_SOURCE_KEYWORDS):
        return 40.0

    return 20.0                           # non-empty but unrecognised source


def _modification_penalty(blocks: list) -> float:
    """
    Penalise datasets with a noisy transformation history.

    Logic
    -----
    - Count MODIFY blocks.
    - Each modification subtracts 5 points from the base 40-point allocation.
    - Floor at 5 so the score never goes negative from this factor alone.

    A dataset touched many times raises questions about data integrity.
    """
    modify_count = sum(1 for b in blocks if b["action"] == ActionType.MODIFY.value)
    penalty      = min(modify_count * 5, 35)   # cap so floor = 40 - 35 = 5
    return max(40.0 - penalty, 5.0)


def _access_pattern_bonus(blocks: list) -> float:
    """
    Reward healthy, moderate access patterns; penalise suspicious spikes.

    Logic
    -----
    - Count ACCESS blocks.
    - 1–10 accesses  →  bonus of up to 20 points (2 per access).
    - 11–30 accesses →  flat 20 points (popular but not alarming).
    - >30 accesses   →  taper by 1 point per extra access over 30;
                        floor at 5 (excessive access is a risk signal).

    Maximum contribution from this factor: 20 points.
    """
    access_count = sum(1 for b in blocks if b["action"] == ActionType.ACCESS.value)

    if access_count == 0:
        return 0.0
    if access_count <= 10:
        return access_count * 2.0          # 2–20 points
    if access_count <= 30:
        return 20.0
    # Suspicious / excessive access: taper down
    over = access_count - 30
    return max(20.0 - over, 5.0)


def calculate_trust_score(dataset_id: str) -> TrustScoreResponse:
    """
    Compute a holistic 0–100 trust score for a dataset.

    Score breakdown (max 100)
    -------------------------
      Source reliability   →  up to 40 pts
      Modification history →  up to 40 pts
      Access patterns      →  up to 20 pts

    Risk labels
    -----------
      80–100 → High Trust
      50–79  → Medium Trust
       0–49  → Low Trust / Risky
    """
    blocks = list(
        ledger_col.find({"dataset_id": dataset_id}, {"_id": 0})
    )

    if not blocks:
        raise HTTPException(
            status_code=404,
            detail=f"Dataset '{dataset_id}' not found in ledger."
        )

    source_score   = _source_reliability_score(blocks)
    mod_score      = _modification_penalty(blocks)
    access_bonus   = _access_pattern_bonus(blocks)

    # Penalty from modifications is expressed as "what remains after deduction"
    modification_penalty = 40.0 - mod_score   # how many points were lost

    raw_score   = source_score + mod_score + access_bonus
    trust_score = round(min(max(raw_score, 0), 100), 2)

    # Determine risk level label
    if trust_score >= 80:
        risk_level = RiskLevel.HIGH_TRUST
    elif trust_score >= 50:
        risk_level = RiskLevel.MEDIUM_TRUST
    else:
        risk_level = RiskLevel.LOW_RISK

    return TrustScoreResponse(
        dataset_id           = dataset_id,
        trust_score          = trust_score,
        risk_level           = risk_level,
        source_score         = source_score,
        modification_penalty = modification_penalty,
        access_bonus         = access_bonus,
        total_blocks         = len(blocks),
    )