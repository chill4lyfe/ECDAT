from __future__ import annotations

import json
import sys
from urllib.request import Request, urlopen

base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"


def post(path: str, payload: dict) -> dict:
    req = Request(
        base + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=90) as response:
        return json.load(response)


scan = post(
    "/v1/scans/directory",
    {
        "path": "/workspace/demo/phase3-enterprise",
        "display_name": "ECDAT Controlled Enterprise Demo",
        "risk_context": {
            "data_lifetime_years": 12,
            "migration_time_years": 4,
            "quantum_horizon_years": 15,
            "data_sensitivity": "high",
            "business_criticality": "high",
            "public_exposure": True,
            "confidentiality_required": True,
        },
    },
)
plan = post(
    "/v1/migration/plans",
    {
        "scan_id": scan["scan_id"],
        "constraints": {
            "mode": "balanced",
            "prefer_hybrid": True,
            "max_parallel_actions": 3,
            "change_window_weeks": 12,
            "allow_prestandard_targets": False,
        },
    },
)
q = scan.get("quantum_summary") or {}
print("ECDAT controlled demo")
print(f"  ✓ {len(scan.get('findings', []))} normalized crypto assets")
print(f"  ✓ {q.get('vulnerable_assets', 0)} quantum-vulnerable")
print(f"  ✓ {q.get('hndl_exposed_assets', 0)} HNDL-exposed")
print(f"  ✓ {q.get('migration_blockers', 0)} migration blockers")
print(f"  ✓ {len(plan.get('waves', []))} migration waves / {plan.get('summary', {}).get('total_actions', 0)} actions")
print(f"  ✓ scan persisted as {scan['scan_id']}")
