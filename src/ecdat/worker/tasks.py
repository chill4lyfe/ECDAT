"""Background task entry points.

The current synchronous API path remains the primary interactive workflow. This module keeps
Dramatiq operational for long-running scan orchestration without embedding a test-only fixture
or bypassing the normal discovery pipeline.
"""

import dramatiq

from ecdat.worker.broker import broker  # noqa: F401


@dramatiq.actor(queue_name="maintenance")
def worker_heartbeat() -> str:
    """Minimal liveness task used by operations checks."""
    return "ready"
