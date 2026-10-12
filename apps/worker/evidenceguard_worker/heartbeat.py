"""The heartbeat loop: one thread per running job attempt (ADR-0008).

Every ``interval`` seconds it records the monotonic time and then renews the lease through M3a's
``heartbeat``, which is its own fenced transaction on its own session. Results:

- success: the local deadline moves to the **pre-call** time plus the lease, and only after the
  renewal is confirmed (``AttemptState.renewed``);
- ``LeaseLostError``: a refusal is recorded and the loop ends. Whether it means lease loss is
  decided against the finish state (``AttemptState.record_refusal``);
- ``JobLockTimeoutError`` or a SQLAlchemy error: reported, and retried at the next interval;
- any other exception: reported, recorded as a refusal, and the loop ends. When unsure, stop.

Setting the stop event prevents *future* heartbeats only. A call already in flight is not
cancelled and may still complete, extend the lease or fail later.
"""

import threading
from collections.abc import Callable

from sqlalchemy.exc import SQLAlchemyError

from evidenceguard_domain.jobs import JobLeaseToken, LeaseLostError
from evidenceguard_persistence.jobs import JobLockTimeoutError
from evidenceguard_worker.context import AttemptState


def run_heartbeats(
    *,
    renew: Callable[[JobLeaseToken], object],
    token: JobLeaseToken,
    state: AttemptState,
    stop: threading.Event,
    interval: float,
    clock: Callable[[], float],
    on_failure: Callable[[BaseException], None],
) -> None:
    while not stop.wait(interval):
        called_at = clock()
        try:
            renew(token)
        except LeaseLostError:
            state.record_refusal()
            return
        except (JobLockTimeoutError, SQLAlchemyError) as error:
            on_failure(error)
            continue
        except Exception as error:
            on_failure(error)
            state.record_refusal()
            return
        state.renewed(called_at)
