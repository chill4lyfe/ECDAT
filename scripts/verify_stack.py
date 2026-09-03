from __future__ import annotations

import json
import sys
from urllib.error import URLError
from urllib.request import urlopen

api = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
web = sys.argv[2] if len(sys.argv) > 2 else "http://web:3000"
failed = False


def check_json(label: str, url: str, expected: str | None = None) -> None:
    global failed
    try:
        with urlopen(url, timeout=10) as response:
            data = json.load(response)
        value = data.get("status")
        ok = expected is None or value == expected
        print(f"  {'✓' if ok else '✗'} {label}: {value or 'ok'}")
        failed = failed or not ok
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"  ✗ {label}: {type(exc).__name__}")
        failed = True


def check_page(label: str, url: str) -> None:
    global failed
    try:
        with urlopen(url, timeout=10) as response:
            ok = 200 <= response.status < 400
        print(f"  {'✓' if ok else '✗'} {label}: HTTP {response.status}")
        failed = failed or not ok
    except URLError as exc:
        print(f"  ✗ {label}: {type(exc).__name__}")
        failed = True


print("ECDAT stack verification")
check_json("API", api + "/health", "ok")
check_json("Postgres / Redis / Neo4j readiness", api + "/health/ready", "ready")
check_page("Web command center", web + "/dashboard")
if failed:
    raise SystemExit(1)
print("  ✓ core stack ready")
