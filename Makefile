.PHONY: secrets config-check build release-amd64 up down ps logs catalog-dry-run catalog-refresh catalog-import-dry-run catalog-import backup

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
