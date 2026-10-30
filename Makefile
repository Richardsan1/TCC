PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
export PYTHONPATH := src

.PHONY: db-up db-down db-reset db-logs db-psql seed check test test-unit run demo bench

db-up:
	docker compose up -d
	@docker compose ps

db-down:
	docker compose down

db-reset:
	docker compose down -v
	docker compose up -d

db-logs:
	docker compose logs -f db

db-psql:
	docker compose exec db psql -U tcc -d tcc

seed:
	docker compose exec -T db psql -U tcc -d tcc < db/init/002_seed.sql
	$(PYTHON) -m trilha.check

check:
	$(PYTHON) -m trilha.check

test:
	$(PYTHON) -m pytest

test-unit:
	$(PYTHON) -m pytest tests/test_graph.py tests/test_bkt.py tests/test_planner.py tests/test_check.py

run:
	$(PYTHON) -m uvicorn trilha.api:app --reload --port 8000

demo:
	$(PYTHON) -m trilha.cli --auto

bench:
	$(PYTHON) bench/bench.py
