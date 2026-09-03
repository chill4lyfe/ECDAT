from __future__ import annotations

import json
import sys
from urllib.request import Request, urlopen

base = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")


def call(path: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(base + path, data=data, headers={"Content-Type": "application/json"} if data else {}, method="POST" if data is not None else "GET")
    with urlopen(request, timeout=180) as response:
        return json.load(response)


scan = call("/v1/scans/reference?quantum_horizon_years=15", {})
plan = call("/v1/migration/plans", {"scan_id": scan["scan_id"], "quantum_horizon_years": 15, "constraints": {"mode": "balanced", "prefer_hybrid": True, "max_parallel_actions": 3, "change_window_weeks": 12}})
coverage = scan.get("coverage") or {}
q = scan.get("quantum_summary") or {}
print("ECDAT reference estate")
print(f"  ✓ {len(scan.get('findings', []))} normalized cryptographic assets")
print(f"  ✓ {coverage.get('evidence_records', 0)} retained evidence records across {coverage.get('files_observed', 0)} observed files")
print(f"  ✓ {q.get('vulnerable_assets', 0)} quantum-vulnerable assets")
print(f"  ✓ {q.get('hndl_exposed_assets', 0)} HNDL-exposed assets")
print(f"  ✓ {q.get('migration_blockers', 0)} migration blockers")
print(f"  ✓ {len(plan.get('waves', []))} migration waves / {plan.get('summary', {}).get('total_actions', 0)} actions")
print(f"  ✓ assessment persisted as {scan['scan_id']}")
