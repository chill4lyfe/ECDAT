#!/usr/bin/env bash
set -euo pipefail
python -m compileall -q src apps/api apps/worker
pytest -q
ruff check src tests apps/api apps/worker
