import hashlib
import json
from typing import Any


def evidence_fingerprint(*, detector: str, locator: str, payload: dict[str, Any]) -> str:
    """Create a deterministic fingerprint without persisting raw sensitive material."""
    canonical = json.dumps(
        {"detector": detector, "locator": locator, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
