"""Admin analytics endpoint."""

from __future__ import annotations

from typing import Annotated, Literal, cast

from fastapi import APIRouter, Query

from app.admin.exceptions import AdminValidationError
from app.admin.schemas import AdminAnalyticsResponse
from app.api.deps import AdminServiceDep, CurrentAdminUser, DbSessionDep

router = APIRouter()

_ALLOWED_ANALYTICS_DAYS = frozenset({7, 30, 90})


@router.get("/analytics", response_model=AdminAnalyticsResponse)
async def analytics(
    _admin: CurrentAdminUser,
    session: DbSessionDep,
    admin: AdminServiceDep,
    days: Annotated[int, Query(ge=7, le=90)] = 30,
) -> AdminAnalyticsResponse:
    # Query strings arrive as text; Annotated[int, Query()] coerces them.
    # Restrict to the supported windows after coercion.
    if days not in _ALLOWED_ANALYTICS_DAYS:
        raise AdminValidationError("days must be one of: 7, 30, 90")
    bounded = cast(Literal[7, 30, 90], days)
    return await admin.get_analytics(session, days=bounded)
