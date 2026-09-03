#!/usr/bin/env bash
set -euo pipefail
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -e '.[dev]'
corepack enable
pnpm install
echo "ECDAT Phase 0 dependencies installed. Copy .env.example to .env before starting infra."
