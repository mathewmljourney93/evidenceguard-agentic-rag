"""Tenant-scoped vendor endpoints (ADR-0006).

- ``POST /v1/vendors`` creates a vendor in the caller's tenant (201).
- ``GET /v1/vendors`` lists the caller's vendors, one bounded page at a time.
- ``GET /v1/vendors/{vendor_id}`` returns one of the caller's vendors, or a generic 404.

The tenant always comes from the authenticated API key. The request body accepts only ``slug``
and ``name``; any other field, including ``tenant_id``, ``actor_id`` or ``role``, is a 422, and
tenant headers or query parameters are ignored. Reviewers and approvers may use these routes;
administrators get a generic 403. A vendor in another tenant is indistinguishable from one that
does not exist (404). A duplicate slug in the same tenant is a generic 409; the same slug in
another tenant is allowed.

Routes are synchronous, so FastAPI runs them, and their database work, in a worker thread. Each
operation is one ``transaction``: it commits before the response is built and rolls back on any
error. Database or configuration failures return a generic 503.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, Any, Protocol
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.exc import SQLAlchemyError

from evidenceguard_api.auth import authenticated_actor
from evidenceguard_api.database import AppDatabase
from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_persistence.db import transaction
from evidenceguard_persistence.settings import DatabaseConfigurationError
from evidenceguard_persistence.vendors import (
    DuplicateVendorSlugError,
    VendorPage,
    VendorRecord,
    create_vendor,
    get_vendor,
    list_vendors,
)

# Lowercase letters and digits, single hyphens between them, 1 to 64 characters (the column
# length). Values that do not match are rejected, never rewritten or truncated.
SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
SLUG_MAX_LENGTH = 64
NAME_MAX_LENGTH = 200
DEFAULT_LIMIT = 20
MAX_LIMIT = 100
MAX_OFFSET = 10_000
VENDOR_ROLES = frozenset({Role.REVIEWER, Role.APPROVER})

_PROBLEM: dict[str, Any] = {"application/problem+json": {}}


class VendorCreate(BaseModel):
    """A new vendor. Only these two fields are accepted."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    slug: str = Field(
        min_length=1,
        max_length=SLUG_MAX_LENGTH,
        pattern=SLUG_PATTERN,
        description="Lowercase letters and digits, separated by single hyphens; unique per tenant.",
    )
    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH, description="Display name.")

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be blank")
        if "\x00" in value:  # PostgreSQL text cannot store U+0000
            raise ValueError("name must not contain a null character")
        return value


class VendorOut(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    slug: str
    name: str


class VendorPageOut(BaseModel):
    """One page, ordered by ``slug`` then ``id``.

    Offset pagination is not a snapshot: vendors created or removed between requests can shift
    later pages, so an item may repeat or be skipped.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    items: list[VendorOut]
    total: int = Field(description="Vendors in the caller's tenant when this page was read.")
    limit: int
    offset: int


class VendorStore(Protocol):
    def create(self, actor: ActorContext, *, slug: str, name: str) -> VendorRecord: ...

    def list(self, actor: ActorContext, *, limit: int, offset: int) -> VendorPage: ...

    def get(self, actor: ActorContext, vendor_id: UUID) -> VendorRecord | None: ...


class DatabaseVendorStore:
    """Vendor operations on the app's shared database, one transaction each."""

    def __init__(self, database: AppDatabase) -> None:
        self._database = database

    def create(self, actor: ActorContext, *, slug: str, name: str) -> VendorRecord:
        with transaction(self._database.session_factory()) as session:
            return create_vendor(session, actor, slug=slug, name=name)

    def list(self, actor: ActorContext, *, limit: int, offset: int) -> VendorPage:
        with transaction(self._database.session_factory()) as session:
            return list_vendors(session, actor, limit=limit, offset=offset)

    def get(self, actor: ActorContext, vendor_id: UUID) -> VendorRecord | None:
        with transaction(self._database.session_factory()) as session:
            return get_vendor(session, actor, vendor_id)


def vendor_actor(
    actor: Annotated[ActorContext, Depends(authenticated_actor)],
) -> ActorContext:
    """Authenticated (401 otherwise) and allowed to use vendors (generic 403 otherwise)."""
    if actor.role not in VENDOR_ROLES:
        raise HTTPException(status_code=403)
    return actor


def _store(request: Request) -> VendorStore:
    store: VendorStore = request.app.state.vendor_store
    return store


@contextmanager
def _database_errors_as_503() -> Iterator[None]:
    try:
        yield
    except (DatabaseConfigurationError, SQLAlchemyError):
        raise HTTPException(status_code=503) from None


def _out(record: VendorRecord) -> VendorOut:
    return VendorOut(id=record.id, slug=record.slug, name=record.name)


router = APIRouter(
    prefix="/v1/vendors",
    tags=["vendors"],
    responses={
        401: {
            "description": "Missing, malformed, unknown or revoked credentials.",
            "content": _PROBLEM,
        },
        403: {"description": "The caller's role may not use vendors.", "content": _PROBLEM},
        503: {"description": "The database is unavailable.", "content": _PROBLEM},
    },
)


@router.post(
    "",
    status_code=201,
    response_model=VendorOut,
    summary="Create a vendor",
    description="Creates a vendor in the caller's tenant. The tenant cannot be supplied.",
    responses={
        409: {
            "description": "The tenant already has a vendor with this slug.",
            "content": _PROBLEM,
        },
        422: {"description": "Invalid or unexpected fields.", "content": _PROBLEM},
    },
)
def create(
    body: VendorCreate,
    request: Request,
    actor: Annotated[ActorContext, Depends(vendor_actor)],
) -> VendorOut:
    try:
        with _database_errors_as_503():
            record = _store(request).create(actor, slug=body.slug, name=body.name)
    except DuplicateVendorSlugError:
        raise HTTPException(status_code=409) from None
    return _out(record)


@router.get(
    "",
    response_model=VendorPageOut,
    summary="List vendors",
    description=(
        "Lists the caller's vendors ordered by slug, then ID. Offset pagination is not a "
        "snapshot: concurrent changes can shift later pages."
    ),
    responses={422: {"description": "Invalid paging parameters.", "content": _PROBLEM}},
)
def list_page(
    request: Request,
    actor: Annotated[ActorContext, Depends(vendor_actor)],
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0,
) -> VendorPageOut:
    with _database_errors_as_503():
        page = _store(request).list(actor, limit=limit, offset=offset)
    return VendorPageOut(
        items=[_out(item) for item in page.items], total=page.total, limit=limit, offset=offset
    )


@router.get(
    "/{vendor_id}",
    response_model=VendorOut,
    summary="Get a vendor",
    description="Returns one of the caller's vendors. Other tenants' vendors are not found.",
    responses={
        404: {"description": "No such vendor in the caller's tenant.", "content": _PROBLEM},
        422: {"description": "The ID is not a UUID.", "content": _PROBLEM},
    },
)
def get_one(
    vendor_id: UUID,
    request: Request,
    actor: Annotated[ActorContext, Depends(vendor_actor)],
) -> VendorOut:
    with _database_errors_as_503():
        record = _store(request).get(actor, vendor_id)
    if record is None:
        raise HTTPException(status_code=404)
    return _out(record)
