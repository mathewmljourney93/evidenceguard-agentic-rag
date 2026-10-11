"""Who is acting, for which tenant, in which role."""

from enum import StrEnum
from uuid import UUID

from evidenceguard_domain._base import DomainModel


class Role(StrEnum):
    """Roles that domain transitions recognise.

    ``ADMIN`` administers accounts and keys. It is deliberately in neither the editing nor the
    approval role sets, so it cannot draft, revise, approve, reject or finalize a report. There
    is no admin bypass.
    """

    REVIEWER = "reviewer"
    APPROVER = "approver"
    ADMIN = "admin"


class ActorContext(DomainModel):
    """The acting principal.

    How one is constructed matters:

    - **At the API boundary** it is built only from an authenticated API key, from the stored
      key, user, tenant and role records. Request headers, query parameters and bodies never
      supply or override any of its fields.
    - **Direct domain callers** (tests, and later the worker) construct it themselves and are
      trusted to pass a principal that was established some other way. The domain does not
      authenticate.
    """

    tenant_id: UUID
    actor_id: UUID
    role: Role
