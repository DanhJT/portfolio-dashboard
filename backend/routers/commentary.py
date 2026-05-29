"""Module-aware commentary endpoint."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from models.schemas import CommentaryRequest, CommentaryResponse
from services import claude_client

router = APIRouter(prefix="/api/commentary", tags=["commentary"])


@router.post("/generate", response_model=CommentaryResponse)
async def generate(payload: CommentaryRequest) -> CommentaryResponse:
    """Generate commentary for the supplied module + metrics payload."""
    try:
        text, ts = await claude_client.generate_commentary(
            payload.metrics, module=payload.module
        )
    except claude_client.CommentaryError as exc:
        raise HTTPException(502, str(exc)) from exc
    return CommentaryResponse(commentary=text, generated_at=ts, model=claude_client.MODEL)
