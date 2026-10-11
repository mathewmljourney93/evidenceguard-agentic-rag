"""``GET /v1/me``: the authenticated principal."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict

from evidenceguard_api.auth import authenticated_actor
from evidenceguard_domain.context import ActorContext, Role

router = APIRouter(prefix="/v1", tags=["identity"])

_PROBLEM: dict[str, Any] = {"application/problem+json": {}}


class Principal(BaseModel):
    """Who the presented API key authenticates as. Nothing else is returned."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tenant_id: UUID
    actor_id: UUID
    role: Role


@router.get(
    "/me",
    response_model=Principal,
    summary="Authenticated principal",
    description=(
        "Returns the tenant, user and role that the API key belongs to, read from the stored "
        "records on every request. Request headers and query parameters cannot change them."
    ),
    responses={
        401: {
            "description": "Missing, malformed, unknown or revoked credentials.",
            "content": _PROBLEM,
        },
        503: {"description": "Authentication is temporarily unavailable.", "content": _PROBLEM},
    },
)
def me(
    actor: Annotated[ActorContext, Depends(authenticated_actor)], response: Response
) -> Principal:
    response.headers["Cache-Control"] = "no-store"
    return Principal(tenant_id=actor.tenant_id, actor_id=actor.actor_id, role=actor.role)
