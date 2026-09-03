.PHONY: up down build rebuild ps logs test check sample verify reset clean

up:
	docker compose up -d --build

down:
	docker compose down

build:
	docker compose build

rebuild:
	docker compose build --no-cache

ps:
	docker compose ps

logs:
	docker compose logs --tail=140

test:
	docker compose run --rm api sh -lc 'cd /workspace && PYTHONPATH=src pytest -q -p no:cacheprovider'

check:
	docker compose config
	docker compose run --rm api sh -lc 'cd /workspace && python -m compileall -q src apps/api apps/worker && PYTHONPATH=src pytest -q -p no:cacheprovider'

sample:
	@docker compose exec -T api python /workspace/scripts/reference_summary.py http://localhost:8000

verify:
	@docker compose exec -T api python /workspace/scripts/verify_stack.py http://localhost:8000 http://web:3000

reset:
	docker compose down -v --remove-orphans
	rm -rf .infrastructure-data

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
