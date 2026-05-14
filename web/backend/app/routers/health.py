"""Liveness probe — for load balancers and the frontend boot check."""

from __future__ import annotations

from fastapi import APIRouter
from web.backend.app.schemas import HealthResponse

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness probe",
    description='Returns `{ "status": "ok" }` whenever the service is reachable.',
)
def health() -> HealthResponse:
    return HealthResponse()
