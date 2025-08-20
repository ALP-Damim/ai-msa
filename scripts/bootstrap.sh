#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

if [ ! -f .env ]; then
	cp .env.example .env
	echo "Created .env from .env.example. Please review secrets before continuing."
fi

python3 -m venv .venv
. .venv/bin/activate
pip install -U pip
pip install -r requirements.txt

if [ "${INDEX_MATERIALS:-false}" = "true" ]; then
	python scripts/index_materials.py data/materials.json
fi

echo "Run: . .venv/bin/activate && make dev"


