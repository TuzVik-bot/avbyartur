.PHONY: secrets config-check build release-amd64 up down ps logs catalog-dry-run catalog-refresh catalog-import-dry-run catalog-import backup test-backend test-scripts test-web lint typecheck

export AVTORINOK_IMAGE_TAG

secrets:
	./scripts/init-secrets.sh

config-check:
	AVTORINOK_IMAGE_TAG=local docker compose config --quiet
	python3 -m json.tool data/catalog.json >/dev/null

build:
	AVTORINOK_IMAGE_TAG=local docker compose build

release-amd64:
	test -n "$$AVTORINOK_IMAGE_TAG" || { printf '%s\n' 'Set AVTORINOK_IMAGE_TAG to a release tag.' >&2; exit 2; }
	./scripts/build-amd64-images.sh

up:
	AVTORINOK_IMAGE_TAG=local docker compose build
	AVTORINOK_IMAGE_TAG=local docker compose up -d db
	AVTORINOK_IMAGE_TAG=local docker compose stop api worker web
	AVTORINOK_IMAGE_TAG=local docker compose run --rm api alembic upgrade head
	AVTORINOK_IMAGE_TAG=local docker compose up -d api worker web

down:
	AVTORINOK_IMAGE_TAG=local docker compose down

ps:
	AVTORINOK_IMAGE_TAG=local docker compose ps

logs:
	AVTORINOK_IMAGE_TAG=local docker compose logs --tail=100 -f

catalog-dry-run:
	python3 scripts/refresh_wikidata_catalog.py

catalog-refresh:
	python3 scripts/refresh_wikidata_catalog.py --write

catalog-import-dry-run:
	AVTORINOK_IMAGE_TAG=local ./scripts/import-catalog.sh --dry-run

catalog-import:
	AVTORINOK_IMAGE_TAG=local ./scripts/import-catalog.sh --apply

backup:
	./scripts/backup.sh

# Backend tests drop every table in the target database. They need a dedicated,
# disposable PostgreSQL database whose name ends in _test:
#   TEST_DATABASE_URL=postgresql+psycopg://user:pass@host:port/<name>_test
#   TEST_DATABASE_DISPOSABLE_CONFIRMATION=<name>_test   (exact database name)
# Never point it at the runtime or preview database.
test-backend:
	@test -n "$$TEST_DATABASE_URL" || { printf '%s\n' 'Set TEST_DATABASE_URL to a disposable *_test PostgreSQL database.' >&2; exit 2; }
	@test -n "$$TEST_DATABASE_DISPOSABLE_CONFIRMATION" || { printf '%s\n' 'Set TEST_DATABASE_DISPOSABLE_CONFIRMATION to the exact test database name.' >&2; exit 2; }
	cd backend && TZ=UTC uv run pytest -q -p no:cacheprovider

test-scripts:
	python3 -m unittest discover -s scripts -p 'test_*.py'

test-web:
	cd web && corepack pnpm test

lint:
	cd backend && uv run ruff check app tests
	cd web && corepack pnpm lint

typecheck:
	cd web && corepack pnpm typecheck
