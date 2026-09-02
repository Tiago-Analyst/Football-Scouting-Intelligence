"""API route aggregation."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    auth,
    health,
    internal,
    players,
    quality,
    recruitment,
    reference,
    shortlists,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(internal.router)
api_router.include_router(auth.router)
api_router.include_router(reference.router)
api_router.include_router(quality.router)
api_router.include_router(players.router)
api_router.include_router(recruitment.router)
api_router.include_router(shortlists.router)
