"""Health check endpoint.

A trivial route used to confirm the backend is running and reachable.
It carries no Handoff feature logic.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def get_health() -> dict[str, str]:
    """Return a simple liveness status."""
    return {"status": "ok"}
