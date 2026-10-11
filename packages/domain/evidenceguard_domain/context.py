"""Who is acting, for which tenant, in which role."""

from enum import StrEnum
from uuid import UUID

from evidenceguard_domain._base import DomainModel


class Role(StrEnum):
    """Roles that domain transitions recognise. There is no admin bypass."""

    REVIEWER = "reviewer"
    APPROVER = "approver"


class ActorContext(DomainModel):
    """The acting principal.

    In later milestones this is built from an authenticated credential, never from request
    input. This milestone performs no authentication: callers are trusted to pass a real one.
    """

    tenant_id: UUID
    actor_id: UUID
    role: Role
