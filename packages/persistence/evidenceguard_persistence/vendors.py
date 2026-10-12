"""Tenant-scoped vendor queries (ADR-0006).

Every function takes the authenticated ``ActorContext`` and uses only its ``tenant_id``: there
is no way to pass a tenant separately. Each query filters by that tenant in SQL. A vendor is
fetched by ``(tenant_id, id)`` together, never fetched globally and checked afterwards, and the
list and its total count use the same tenant filter.

These functions run inside a caller-owned session and never commit or roll back; the caller's
``transaction`` does. Creating a vendor flushes, so a duplicate slug is detected while the
caller can still roll back. Only a violation of the vendors ``(tenant_id, slug)`` unique
constraint becomes ``DuplicateVendorSlugError``; every other integrity error propagates
unchanged.
"""

from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from evidenceguard_domain.context import ActorContext
from evidenceguard_persistence.models import Vendor

# Name given by the models' naming convention to UniqueConstraint("tenant_id", "slug").
VENDOR_SLUG_CONSTRAINT = "uq_vendors_tenant_id_slug"


class DuplicateVendorSlugError(Exception):
    """The tenant already has a vendor with this slug. The message names no value."""

    def __init__(self) -> None:
        super().__init__("a vendor with this slug already exists in the tenant")


@dataclass(frozen=True)
class VendorRecord:
    id: UUID
    slug: str
    name: str


@dataclass(frozen=True)
class VendorPage:
    items: tuple[VendorRecord, ...]
    total: int


def _violated_constraint(error: IntegrityError) -> str | None:
    diag = getattr(error.orig, "diag", None)
    name = getattr(diag, "constraint_name", None)
    return name if isinstance(name, str) else None


def create_vendor(session: Session, actor: ActorContext, *, slug: str, name: str) -> VendorRecord:
    vendor = Vendor(id=uuid4(), tenant_id=actor.tenant_id, slug=slug, name=name)
    session.add(vendor)
    try:
        session.flush()
    except IntegrityError as error:
        if _violated_constraint(error) == VENDOR_SLUG_CONSTRAINT:
            raise DuplicateVendorSlugError() from None
        raise
    return VendorRecord(id=vendor.id, slug=vendor.slug, name=vendor.name)


def get_vendor(session: Session, actor: ActorContext, vendor_id: UUID) -> VendorRecord | None:
    row = session.execute(
        select(Vendor.id, Vendor.slug, Vendor.name).where(
            Vendor.tenant_id == actor.tenant_id, Vendor.id == vendor_id
        )
    ).one_or_none()
    return None if row is None else VendorRecord(id=row.id, slug=row.slug, name=row.name)


def list_vendors(session: Session, actor: ActorContext, *, limit: int, offset: int) -> VendorPage:
    """One page ordered by ``(slug, id)``; ``id`` is a unique tie-breaker.

    The count and the page are two statements in the caller's transaction. Under PostgreSQL's
    default READ COMMITTED isolation, a concurrent insert or delete between them, or between
    page requests, can make pages overlap or skip rows: offset pagination is not a snapshot.
    """
    total = session.execute(
        select(func.count()).select_from(Vendor).where(Vendor.tenant_id == actor.tenant_id)
    ).scalar_one()
    rows = session.execute(
        select(Vendor.id, Vendor.slug, Vendor.name)
        .where(Vendor.tenant_id == actor.tenant_id)
        .order_by(Vendor.slug, Vendor.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return VendorPage(
        items=tuple(VendorRecord(id=r.id, slug=r.slug, name=r.name) for r in rows), total=total
    )
