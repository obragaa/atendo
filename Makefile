# Alvos de desenvolvimento do Atendo.
# `test` e `lint` rodam sem banco, sem Redis e sem chave de API.

.PHONY: up down logs seed ingest evals test lint fmt

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f api

seed:
	docker compose exec api python -m scripts.seed

# Uso: make ingest TENANT=clinica-sorriso SRC=./docs
# SRC em vez de PATH: sobrescrever PATH pela linha de comando do make
# quebraria a resolução de executáveis dentro da própria receita.
ingest:
	docker compose exec api python -m scripts.ingest --tenant "$(TENANT)" --path "$(SRC)"

evals:
	python -m evals.runner --min-pass-rate 0.85

test:
	python -m pytest

lint:
	ruff check .

fmt:
	ruff format .
