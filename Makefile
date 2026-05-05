.PHONY: dev test lint shell

dev:
	docker compose up --build

test:
	pytest -q

lint:
	ruff check app tests

shell:
	docker compose exec web bash
