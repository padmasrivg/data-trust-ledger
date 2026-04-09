"""
main.py
-------
FastAPI application entry point.

All five REST endpoints are defined here.  Business logic lives in
ledger_service.py; this file is responsible only for HTTP routing,
request/response shaping, and error propagation.

Run with:
    uvicorn main:app --reload
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from models import (
    UploadRequest, ModifyRequest, AccessRequest,
    ActionResponse, HistoryResponse, TrustScoreResponse,
    ActionType,
)
from ledger_service import create_block, get_history, calculate_trust_score

# ── Application bootstrap ─────────────────────────────────────────────────
app = FastAPI(
    title       = "Public Sector Data Lake — Provenance Ledger",
    description = (
        "A blockchain-inspired immutable ledger that tracks every operation "
        "performed on national datasets and computes a dynamic Trust Score."
    ),
    version     = "1.0.0",
    docs_url    = "/docs",        # Swagger UI
    redoc_url   = "/redoc",       # ReDoc UI
)


# ══════════════════════════════════════════════════════════════════════════
#  POST /upload
#  Register a brand-new dataset and create its genesis block.
# ══════════════════════════════════════════════════════════════════════════

@app.post(
    "/upload",
    response_model = ActionResponse,
    status_code    = 201,
    tags           = ["Ledger"],
    summary        = "Ingest a new dataset",
)
async def upload_dataset(request: UploadRequest):
    """
    Creates the **first block** (genesis block) for a dataset.

    - `dataset_id` must be unique within the ledger (uploading the same id
      twice is allowed — it simply appends another UPLOAD block to the chain).
    - `source` should describe the data provider (e.g. "Ministry of Health").
      A recognised government source contributes to a higher trust score.
    """
    block = create_block(
        dataset_id = request.dataset_id,
        action     = ActionType.UPLOAD,
        source     = request.source,
    )
    return ActionResponse(
        message      = f"Dataset '{request.dataset_id}' uploaded successfully.",
        dataset_id   = request.dataset_id,
        current_hash = block["current_hash"],
    )


# ══════════════════════════════════════════════════════════════════════════
#  POST /modify
#  Record a transformation or update applied to an existing dataset.
# ══════════════════════════════════════════════════════════════════════════

@app.post(
    "/modify",
    response_model = ActionResponse,
    status_code    = 200,
    tags           = ["Ledger"],
    summary        = "Record a dataset modification",
)
async def modify_dataset(request: ModifyRequest):
    """
    Appends a **MODIFY block** to the chain.

    Each modification is penalised in the trust score algorithm — datasets
    with many transformations are treated as less reliable.
    """
    # Verify the dataset exists before modifying it
    existing = get_history(request.dataset_id)   # raises 404 if not found
    _ = existing  # history object not needed here; we just want the guard

    block = create_block(
        dataset_id = request.dataset_id,
        action     = ActionType.MODIFY,
    )
    return ActionResponse(
        message      = f"Modification recorded for dataset '{request.dataset_id}'.",
        dataset_id   = request.dataset_id,
        current_hash = block["current_hash"],
    )


# ══════════════════════════════════════════════════════════════════════════
#  POST /access
#  Log a consumption / read event for a dataset.
# ══════════════════════════════════════════════════════════════════════════

@app.post(
    "/access",
    response_model = ActionResponse,
    status_code    = 200,
    tags           = ["Ledger"],
    summary        = "Log a dataset access event",
)
async def access_dataset(request: AccessRequest):
    """
    Appends an **ACCESS block** to the chain.

    Moderate access patterns improve the trust score; excessive access
    (>30 events) is treated as a risk signal and reduces the bonus.
    """
    # Verify the dataset exists
    get_history(request.dataset_id)   # raises 404 if not found

    block = create_block(
        dataset_id = request.dataset_id,
        action     = ActionType.ACCESS,
    )
    return ActionResponse(
        message      = f"Access event logged for dataset '{request.dataset_id}'.",
        dataset_id   = request.dataset_id,
        current_hash = block["current_hash"],
    )


# ══════════════════════════════════════════════════════════════════════════
#  GET /history/{dataset_id}
#  Retrieve the full immutable provenance chain for a dataset.
# ══════════════════════════════════════════════════════════════════════════

@app.get(
    "/history/{dataset_id}",
    response_model = HistoryResponse,
    status_code    = 200,
    tags           = ["Ledger"],
    summary        = "Get full provenance history",
)
async def history(dataset_id: str):
    """
    Returns all blocks for `dataset_id` in chronological order.

    Use the `previous_hash` → `current_hash` chain to verify immutability:
    any tampered block will have a `current_hash` that no longer matches the
    re-computed hash of its fields.
    """
    return get_history(dataset_id)


# ══════════════════════════════════════════════════════════════════════════
#  GET /trust-score/{dataset_id}
#  Compute and return the dynamic trust score for a dataset.
# ══════════════════════════════════════════════════════════════════════════

@app.get(
    "/trust-score/{dataset_id}",
    response_model = TrustScoreResponse,
    status_code    = 200,
    tags           = ["Trust"],
    summary        = "Calculate dataset trust score",
)
async def trust_score(dataset_id: str):
    """
    Computes a **0–100 trust score** built from three weighted factors:

    | Factor                | Max Points | Notes                              |
    |-----------------------|------------|------------------------------------|
    | Source reliability    | 40         | Gov source → 40, unknown → 5       |
    | Modification history  | 40         | −5 per MODIFY block, floor 5       |
    | Access patterns       | 20         | Moderate access good, >30 penalised|

    **Risk levels:**
    - 80–100 → High Trust
    - 50–79  → Medium Trust
    - <50    → Low Trust / Risky
    """
    return calculate_trust_score(dataset_id)


# ══════════════════════════════════════════════════════════════════════════
#  Global exception handler — converts unhandled errors to clean JSON
# ══════════════════════════════════════════════════════════════════════════

@app.exception_handler(Exception)
async def generic_exception_handler(request, exc):
    return JSONResponse(
        status_code = 500,
        content     = {"detail": f"Internal server error: {str(exc)}"},
    )


# ── Health check (useful for Docker / K8s probes) ────────────────────────
@app.get("/health", tags=["Meta"], include_in_schema=False)
async def health():
    return {"status": "ok"}