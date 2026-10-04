import csv
import uuid
from collections import defaultdict
from pathlib import Path

import pytest
from sqlalchemy import delete, func, select

from app.drom_import import (
    REQUIRED_COLUMNS,
    DromInputError,
    _generation_years,
    _load_batch,
    _modification_external_id,
    _plan_models,
    import_drom_csv,
)
from app.models import (
    CatalogBodyType,
    CatalogBodyVariant,
    CatalogGeneration,
    CatalogImport,
    CatalogMake,
    CatalogModel,
    CatalogModification,
)


def _row(
    make_slug: str, source_id: str, generation: str, generation_path: str, **values
) -> dict[str, str]:
    row = {column: "" for column in REQUIRED_COLUMNS}
    row.update(
        {
            "source": "drom.ru",
            "source_id": source_id,
            "source_url": f"https://www.drom.ru/catalog/{make_slug}/roadster/{source_id}/",
            "make": "Example",
            "make_slug": make_slug,
            "model": "Roadster",
            "model_slug": "roadster",
            "generation": generation,
            "generation_url": f"https://www.drom.ru/catalog/{make_slug}/roadster/{generation_path}/",
            "trim": "2.0 MT",
            "production_period": "01.2000 - 12.2005",
            "engine_code": "E20",
            "frame_code": "R1",
            "engine_l": "2.0",
            "power_hp": "150",
            "fuel": "бензин",
            "transmission": "МКПП",
            "drive": "задний привод",
            "summary": "",
        }
    )
    row.update(values)
    return row


def _write_csv(path: Path, rows: list[dict[str, str]]) -> Path:
    with path.open("w", encoding="utf-8-sig", newline="") as source_file:
        writer = csv.DictWriter(source_file, fieldnames=sorted(REQUIRED_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)
    return path


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("Китай 04.2024 - н.в. Джип/SUV 5 дв., Гибрид", (2024, None, "open")),
        ("2005 - н.в. Хэтчбек", (2005, None, "open")),
        ("04.2024 - 03.2025 Седан", (2024, 2025, "closed")),
        ("13.2024 - н.в. Кроссовер", (None, None, "unknown")),
        ("2020 - 2018 Пикап", (None, None, "unknown")),
    ],
)
def test_drom_generation_years_keep_explicit_open_start(label, expected):
    assert _generation_years(label) == expected


def test_drom_dry_run_apply_and_rerun_preserve_existing_catalog_rows(
    integration, tmp_path
):
    suffix = uuid.uuid4().hex[:8]
    make_slug = f"example-{suffix}"
    source_ids = [f"{suffix}{index:03d}" for index in range(1, 5)]
    first_generation_url = (
        f"https://www.drom.ru/catalog/{make_slug}/roadster/g_2000_2005/"
    )
    rows = [
        _row(make_slug, source_ids[0], "01.2000 - 12.2005 Седан", "g_2000_2005"),
        _row(
            make_slug,
            source_ids[1],
            "01.2000 - 12.2005 Седан",
            "g_2000_2005",
            trim="",
            production_period="12.2005 - 01.2000",
            engine_code="",
            frame_code="",
            engine_l="",
            power_hp="",
            fuel="",
            transmission="",
            drive="",
            summary="Только краткое описание",
        ),
        _row(
            make_slug,
            source_ids[2],
            "Китай 04.2005 - н.в. Хэтчбек",
            "g_2005_current",
            production_period="",
            engine_code="",
            frame_code="",
            engine_l="",
            power_hp="",
            fuel="",
            transmission="",
            drive="",
        ),
        _row(
            make_slug,
            source_ids[3],
            "2020 - 2018 Пикап",
            "g_2020_2018",
            production_period="не указан",
            engine_l="invalid",
            power_hp="150.5",
        ),
    ]
    path = _write_csv(tmp_path / "drom.csv", rows)
    session_factory = integration["SessionLocal"]

    with session_factory() as db:
        make = CatalogMake(
            slug=make_slug,
            name="Example",
            aliases=["Keep make alias"],
            external_id=f"wikidata:{suffix}",
            source_name="Wikidata",
            source_metadata={"name": "Wikidata", "qid": f"Q{suffix}"},
            manual_override=False,
        )
        prior_body_type_ids = set(db.scalars(select(CatalogBodyType.id)).all())
        db.add(make)
        db.flush()
        model = CatalogModel(
            make_id=make.id,
            slug=f"{make_slug}-roadster",
            name="Example Roadster",
            aliases=["Keep model alias"],
            external_id=f"manual:model:{suffix}",
            source_name="Manual",
            source_metadata={"url": "https://example.test/model"},
            manual_override=True,
        )
        alias_model = CatalogModel(
            make_id=make.id,
            slug=f"other-{suffix}",
            name="Different Model",
            aliases=["Roadster"],
            external_id=f"manual:alias-model:{suffix}",
            source_name="Manual",
            source_metadata={"url": "https://example.test/alias-model"},
            manual_override=True,
        )
        db.add_all([model, alias_model])
        db.flush()
        manual_generation = CatalogGeneration(
            model_id=model.id,
            slug="g_2000_2005",
            name="Curated generation",
            year_from=1999,
            year_to=2004,
            external_id=f"manual:generation:{suffix}",
            source_name="Manual",
            source_metadata={"url": "https://example.test/generation"},
            manual_override=True,
        )
        db.add(manual_generation)
        existing_sedan = db.scalar(
            select(CatalogBodyType).where(CatalogBodyType.slug == "sedan")
        )
        if existing_sedan is None:
            existing_sedan = CatalogBodyType(
                slug="sedan",
                name="Седан",
                external_id=f"wikidata:sedan-{suffix}",
                source_name="Wikidata",
                source_metadata={"name": "Wikidata"},
                manual_override=False,
            )
            db.add(existing_sedan)
        existing_hatchback = db.scalar(
            select(CatalogBodyType).where(CatalogBodyType.slug == "hatchback")
        )
        if existing_hatchback is None:
            existing_hatchback = CatalogBodyType(
                slug="hatchback",
                name="Хэтчбэк",
                external_id=f"wikidata:hatchback-{suffix}",
                source_name="Wikidata",
                source_metadata={"name": "Wikidata"},
                manual_override=False,
            )
            db.add(existing_hatchback)
        db.commit()

        before = {
            "makes": db.scalar(select(func.count(CatalogMake.id))) or 0,
            "models": db.scalar(select(func.count(CatalogModel.id))) or 0,
            "generations": db.scalar(select(func.count(CatalogGeneration.id))) or 0,
            "modifications": db.scalar(select(func.count(CatalogModification.id))) or 0,
            "imports": db.scalar(select(func.count(CatalogImport.id))) or 0,
        }
        preview = import_drom_csv(db, path, dry_run=True)
        after_preview = {
            "makes": db.scalar(select(func.count(CatalogMake.id))) or 0,
            "models": db.scalar(select(func.count(CatalogModel.id))) or 0,
            "generations": db.scalar(select(func.count(CatalogGeneration.id))) or 0,
            "modifications": db.scalar(select(func.count(CatalogModification.id))) or 0,
            "imports": db.scalar(select(func.count(CatalogImport.id))) or 0,
        }
        assert preview["status"] == "dry_run"
        assert preview["source_counts"] == {
            "rows": 4,
            "makes": 1,
            "models": 1,
            "generations": 3,
            "body_type_categories": 3,
        }
        assert preview["crosswalk"]["makes"] == {"matched": 1, "new": 0}
        assert preview["crosswalk"]["models"] == {
            "matched": 0,
            "drom_existing": 0,
            "ambiguous": 1,
            "unmatched": 0,
            "new": 1,
        }
        assert preview["exact_match_rules"]["unique"] == {
            "slug": 0,
            "make_prefixed_slug": 0,
            "normalized_name": 0,
            "normalized_alias": 0,
            "multi_rule_match": 0,
        }
        assert preview["exact_match_rules"]["ambiguous"] == {
            "slug": 0,
            "make_prefixed_slug": 1,
            "normalized_name": 1,
            "normalized_alias": 1,
        }
        assert preview["data_quality"]["summary_only_engine_specs_rows"] == 1
        assert preview["data_quality"]["missing_engine_specs_rows"] == 1
        assert preview["data_quality"]["production_period_missing_rows"] == 1
        assert preview["data_quality"]["production_period_end_before_start_rows"] == 1
        assert preview["data_quality"]["production_period_malformed_rows"] == 1
        assert preview["data_quality"]["generation_years_open_end"] == 1
        assert preview["data_quality"]["generation_years_unknown"] == 1
        assert before == after_preview

        imported = import_drom_csv(db, path, dry_run=False)
        assert imported["status"] == "imported"
        assert imported["actions"]["modifications_inserted"] == 4
        assert imported["actions"]["models_inserted"] == 1
        assert imported["actions"]["generations_inserted"] == 3
        assert imported["actions"]["body_variants_inserted"] == 3
        assert (
            imported["actions"]["body_types_reused"]
            + imported["actions"]["body_types_inserted"]
            == 3
        )

        modifications = db.scalars(
            select(CatalogModification).where(
                CatalogModification.external_id.in_(
                    [_modification_external_id(row["source_url"]) for row in rows]
                )
            )
        ).all()
        assert len(modifications) == 4
        modification_by_id = {row.external_id: row for row in modifications}
        assert modification_by_id[
            _modification_external_id(rows[1]["source_url"])
        ].name.startswith("Без названия Drom")
        assert (
            modification_by_id[
                _modification_external_id(rows[1]["source_url"])
            ].source_metadata
            == rows[1]
        )
        assert (
            modification_by_id[
                _modification_external_id(rows[1]["source_url"])
            ].source_metadata["production_period"]
            == "12.2005 - 01.2000"
        )
        assert (
            modification_by_id[
                _modification_external_id(rows[1]["source_url"])
            ].source_metadata["summary"]
            == "Только краткое описание"
        )

        drom_model = db.scalar(
            select(CatalogModel).where(
                CatalogModel.make_id == make.id,
                CatalogModel.source_name == "Drom",
            )
        )
        assert drom_model is not None
        assert drom_model.id not in {model.id, alias_model.id}
        assert drom_model.name == "Roadster"
        assert drom_model.source_metadata["model_match_status"] == "ambiguous"
        drom_generations = db.scalars(
            select(CatalogGeneration).where(
                CatalogGeneration.source_name == "Drom",
                CatalogGeneration.model_id == drom_model.id,
            )
        ).all()
        drom_generation_by_url = {
            row.source_metadata["generation_url"]: row for row in drom_generations
        }
        assert len(drom_generation_by_url) == 3
        closed_generation = drom_generation_by_url[first_generation_url]
        assert (closed_generation.year_from, closed_generation.year_to) == (2000, 2005)
        assert closed_generation.slug == manual_generation.slug
        assert closed_generation.model_id != manual_generation.model_id
        open_generation = drom_generation_by_url[rows[2]["generation_url"]]
        assert (open_generation.year_from, open_generation.year_to) == (2005, None)
        invalid_generation = drom_generation_by_url[rows[3]["generation_url"]]
        assert (invalid_generation.year_from, invalid_generation.year_to) == (
            None,
            None,
        )
        assert {
            row.slug
            for row in db.scalars(
                select(CatalogBodyVariant).where(
                    CatalogBodyVariant.generation_id.in_(
                        [row.id for row in drom_generations]
                    )
                )
            ).all()
        } == {
            "sedan",
            "hatchback",
            "pickup",
        }

        original_make = db.get(CatalogMake, make.id)
        original_model = db.get(CatalogModel, model.id)
        original_generation = db.get(CatalogGeneration, manual_generation.id)
        assert (
            original_make.name,
            original_make.aliases,
            original_make.source_name,
            original_make.source_metadata,
        ) == (
            "Example",
            ["Keep make alias"],
            "Wikidata",
            {"name": "Wikidata", "qid": f"Q{suffix}"},
        )
        assert (
            original_model.name,
            original_model.aliases,
            original_model.source_name,
            original_model.source_metadata,
        ) == (
            "Example Roadster",
            ["Keep model alias"],
            "Manual",
            {"url": "https://example.test/model"},
        )
        original_alias_model = db.get(CatalogModel, alias_model.id)
        assert (
            original_alias_model.name,
            original_alias_model.aliases,
            original_alias_model.source_name,
            original_alias_model.source_metadata,
        ) == (
            "Different Model",
            ["Roadster"],
            "Manual",
            {"url": "https://example.test/alias-model"},
        )
        assert (
            original_generation.name,
            original_generation.year_from,
            original_generation.year_to,
            original_generation.source_metadata,
        ) == (
            "Curated generation",
            1999,
            2004,
            {"url": "https://example.test/generation"},
        )

        repeat = import_drom_csv(db, path, dry_run=False)
        assert repeat["catalog_import_exists"] is True
        assert repeat["actions"].get("modifications_created", 0) == 0
        assert repeat["actions"].get("modifications_updated", 0) == 0
        assert repeat["actions"].get("generations_created", 0) == 0
        assert (
            db.scalar(
                select(func.count(CatalogModification.id)).where(
                    CatalogModification.external_id.in_(
                        [_modification_external_id(row["source_url"]) for row in rows]
                    )
                )
            )
            == 4
        )
        assert (
            db.scalar(
                select(func.count(CatalogImport.id)).where(
                    CatalogImport.source_name == "Drom",
                    CatalogImport.checksum == repeat["checksum_sha256"],
                )
            )
            == 1
        )

        response = integration["client"].get(
            "/api/v1/catalog/modifications",
            params={"generation_id": str(closed_generation.id)},
        )
        assert response.status_code == 200
        api_item = next(
            item
            for item in response.json()["items"]
            if item["source"]["id"] == source_ids[0]
        )
        first_modification = modification_by_id[
            _modification_external_id(rows[0]["source_url"])
        ]
        assert api_item == {
            "id": str(first_modification.id),
            "slug": first_modification.slug,
            "name": "2.0 MT",
            "aliases": [],
            "source": {
                "name": "Drom",
                "id": source_ids[0],
                "url": rows[0]["source_url"],
            },
            "specs": {
                "engine_code": "E20",
                "frame_code": "R1",
                "engine_l": 2.0,
                "power_hp": 150,
                "fuel": "бензин",
                "transmission": "МКПП",
                "drive": "задний привод",
                "production_period_raw": "01.2000 - 12.2005",
                "summary_raw": None,
            },
        }

        imported_body_type_ids = set(db.scalars(select(CatalogBodyType.id)).all())
        new_body_type_ids = imported_body_type_ids - prior_body_type_ids
        generation_id_values = [row.id for row in drom_generations]
        db.execute(
            delete(CatalogModification).where(
                CatalogModification.external_id.in_(
                    [_modification_external_id(row["source_url"]) for row in rows]
                )
            )
        )
        db.execute(
            delete(CatalogBodyVariant).where(
                CatalogBodyVariant.generation_id.in_(generation_id_values)
            )
        )
        db.execute(
            delete(CatalogGeneration).where(
                CatalogGeneration.model_id.in_(
                    [model.id, alias_model.id, drom_model.id]
                )
            )
        )
        db.execute(
            delete(CatalogModel).where(
                CatalogModel.id.in_([model.id, alias_model.id, drom_model.id])
            )
        )
        db.execute(delete(CatalogMake).where(CatalogMake.id == make.id))
        if new_body_type_ids:
            db.execute(
                delete(CatalogBodyType).where(CatalogBodyType.id.in_(new_body_type_ids))
            )
        db.execute(
            delete(CatalogImport).where(
                CatalogImport.checksum == imported["checksum_sha256"]
            )
        )
        db.commit()


def test_drom_duplicate_canonical_source_urls_are_rejected(tmp_path):
    make_slug = f"duplicate-{uuid.uuid4().hex[:8]}"
    row = _row(make_slug, "same-id", "2000 - 2005 Седан", "g_2000_2005")
    duplicate = dict(row)
    duplicate["source_url"] = (
        row["source_url"]
        .replace("https://www.drom.ru", "https://WWW.DROM.RU:443")
        .rstrip("/")
    )
    path = _write_csv(tmp_path / "duplicate.csv", [row, duplicate])

    with pytest.raises(DromInputError, match="duplicate source_url"):
        _load_batch(path)


def test_drom_source_url_is_canonicalized_before_hashing(tmp_path):
    make_slug = f"canonical-{uuid.uuid4().hex[:8]}"
    row = _row(make_slug, "source-id", "2000 - 2005 Седан", "g_2000_2005")
    row["source_url"] = (
        row["source_url"]
        .replace("https://www.drom.ru", "https://WWW.DROM.RU:443")
        .rstrip("/")
        + "#section"
    )
    path = _write_csv(tmp_path / "canonical.csv", [row])

    records, _, _, _, _, _ = _load_batch(path)

    canonical_url = f"https://www.drom.ru/catalog/{make_slug}/roadster/source-id/"
    assert records[0].raw["source_url"] == canonical_url
    assert len(_modification_external_id(records[0].raw["source_url"])) <= 100


def test_drom_same_source_id_can_identify_different_urls(tmp_path):
    make_slug = f"same-id-{uuid.uuid4().hex[:8]}"
    first = _row(make_slug, "same-id", "2000 - 2005 Седан", "g_2000_2005")
    second = dict(first)
    second["source_url"] = first["source_url"].replace("/same-id/", "/alternate/")
    path = _write_csv(tmp_path / "same-id-different-urls.csv", [first, second])

    records, _, _, _, _, quality = _load_batch(path)

    assert len(records) == 2
    assert (
        len({_modification_external_id(row.raw["source_url"]) for row in records}) == 2
    )
    assert quality["source_rows"] == 2


def test_drom_modification_external_id_is_url_hashed_and_within_column_limit():
    source_url = "https://www.drom.ru/catalog/toyota/roadster/12345/"
    alternate = "https://www.drom.ru/catalog/toyota/roadster/67890/"

    external_id = _modification_external_id(source_url)

    assert external_id.startswith("drom:modification-url:")
    assert len(external_id) <= 100
    assert external_id != _modification_external_id(alternate)


def test_drom_legacy_modification_migrates_only_when_source_url_matches(
    integration, tmp_path
):
    make_slug = f"legacy-{uuid.uuid4().hex[:8]}"
    original = _row(make_slug, "shared-id", "2000 - 2005 Седан", "g_2000_2005")
    alternate = dict(original)
    alternate["source_url"] = original["source_url"].replace(
        "/shared-id/", "/different-record/"
    )
    original_path = _write_csv(tmp_path / "legacy-original.csv", [original])
    alternate_path = _write_csv(tmp_path / "legacy-alternate.csv", [alternate])
    original_external_id = _modification_external_id(original["source_url"])
    alternate_external_id = _modification_external_id(alternate["source_url"])
    legacy_external_id = "drom:shared-id"

    with integration["SessionLocal"]() as db:
        import_drom_csv(db, original_path, dry_run=False)
        modification = db.scalar(
            select(CatalogModification).where(
                CatalogModification.external_id == original_external_id
            )
        )
        assert modification is not None
        original_id = modification.id
        original_generation_id = modification.generation_id
        original_slug = modification.slug
        modification.external_id = legacy_external_id
        db.commit()

        imported_alternate = import_drom_csv(db, alternate_path, dry_run=False)
        assert imported_alternate["actions"]["modifications_inserted"] == 1
        legacy_row = db.scalar(
            select(CatalogModification).where(
                CatalogModification.external_id == legacy_external_id
            )
        )
        alternate_row = db.scalar(
            select(CatalogModification).where(
                CatalogModification.external_id == alternate_external_id
            )
        )
        assert legacy_row is not None
        assert alternate_row is not None
        assert legacy_row.id == original_id
        assert legacy_row.source_metadata["source_url"] == original["source_url"]
        assert alternate_row.id != legacy_row.id
        assert alternate_row.slug != legacy_row.slug

        repeat_alternate = import_drom_csv(db, alternate_path, dry_run=False)
        assert repeat_alternate["actions"].get("modifications_created", 0) == 0
        assert repeat_alternate["actions"].get("modifications_updated", 0) == 0

        migrated = import_drom_csv(db, original_path, dry_run=False)
        assert migrated["actions"]["modifications_updated"] == 1
        original_row = db.scalar(
            select(CatalogModification).where(
                CatalogModification.external_id == original_external_id
            )
        )
        assert original_row is not None
        assert original_row.id == original_id
        assert original_row.generation_id == original_generation_id
        assert original_row.slug == original_slug
        assert (
            db.scalar(
                select(CatalogModification).where(
                    CatalogModification.external_id == legacy_external_id
                )
            )
            is None
        )
        assert (
            db.scalar(
                select(func.count(CatalogModification.id)).where(
                    CatalogModification.external_id.in_(
                        [original_external_id, alternate_external_id]
                    )
                )
            )
            == 2
        )


def test_long_drom_generation_label_is_preserved(integration, tmp_path):
    make_slug = f"long-label-{uuid.uuid4().hex[:8]}"
    generation_label = "01.2000 - 12.2005 " + "Frame code 123456789, " * 12
    assert len(generation_label) > 180
    path = _write_csv(
        tmp_path / "long-generation.csv",
        [_row(make_slug, "long-generation", generation_label, "g_2000_2005_long")],
    )

    with integration["SessionLocal"]() as db:
        import_drom_csv(db, path, dry_run=False)
        generation = db.scalar(
            select(CatalogGeneration).where(
                CatalogGeneration.source_name == "Drom",
                CatalogGeneration.slug == "g_2000_2005_long",
            )
        )

        assert generation is not None
        assert generation.name == generation_label
        assert generation.source_metadata["generation_label"] == generation_label


def test_exact_model_crosswalk_keeps_three_ambiguous_pairs_separate(integration):
    suffix = uuid.uuid4().hex[:8]
    make_slugs = {
        "bmw": f"bmw-{suffix}",
        "kia": f"kia-{suffix}",
        "hyundai": f"hyundai-{suffix}",
    }
    with integration["SessionLocal"]() as db:
        make_names = {"bmw": "BMW", "kia": "Kia", "hyundai": "Hyundai"}
        make_rows = {
            key: CatalogMake(slug=make_slugs[key], name=name, aliases=[])
            for key, name in make_names.items()
        }
        db.add_all(make_rows.values())
        db.flush()
        model_rows = [
            CatalogModel(
                make_id=make_rows["bmw"].id,
                slug=f"{make_slugs['bmw']}-1-series",
                name="BMW 1 (F20)",
                aliases=["BMW 1 Series"],
            ),
            CatalogModel(
                make_id=make_rows["bmw"].id,
                slug=f"{make_slugs['bmw']}-1-series-q28861726",
                name="BMW 1 (F52)",
                aliases=["BMW 1 Series"],
            ),
            CatalogModel(
                make_id=make_rows["bmw"].id,
                slug=f"{make_slugs['bmw']}-3-series",
                name="BMW E21",
                aliases=["BMW 3 Series"],
            ),
            CatalogModel(
                make_id=make_rows["bmw"].id,
                slug=f"{make_slugs['bmw']}-3-series-family",
                name="BMW 3 Series",
                aliases=["3 серия", "3er"],
            ),
            CatalogModel(
                make_id=make_rows["bmw"].id,
                slug=f"{make_slugs['bmw']}-3-series-gran-turismo",
                name="BMW F34",
                aliases=["BMW 3 Series Gran Turismo"],
            ),
            CatalogModel(
                make_id=make_rows["kia"].id,
                slug=f"{make_slugs['kia']}-cee-d",
                name="Kia cee’d",
                aliases=["Kia Cee'd"],
            ),
            CatalogModel(
                make_id=make_rows["kia"].id,
                slug=f"{make_slugs['kia']}-ceed",
                name="Kia cee’d (JD)",
                aliases=["Kia cee'd"],
            ),
            CatalogModel(
                make_id=make_rows["hyundai"].id,
                slug=f"{make_slugs['hyundai']}-tiburon",
                name="Hyundai Tiburon",
                aliases=["Hyundai Coupé"],
            ),
        ]
        db.add_all(model_rows)
        db.flush()

        drom_models = {
            (make_slugs["bmw"], "1-series"): {"name": "BMW 1-Series"},
            (make_slugs["bmw"], "3-series"): {"name": "BMW 3-Series"},
            (make_slugs["bmw"], "3-series_gran_turismo"): {
                "name": "3-Series Gran Turismo"
            },
            (make_slugs["kia"], "cee~d"): {"name": "Kia Ceed"},
            (make_slugs["hyundai"], "coupe-model"): {"name": "Hyundai Coupe"},
        }
        counters = defaultdict(int)
        resolved = _plan_models(
            db,
            drom_models,
            {make_slugs[key]: {"name": name} for key, name in make_names.items()},
            {make_slugs[key]: row.id for key, row in make_rows.items()},
            dry_run=True,
            counts=counters,
        )

        assert counters["models_matched"] == 2
        assert counters["models_ambiguous"] == 3
        assert counters["models_unmatched"] == 0
        assert counters["models_created"] == 3
        assert counters["models_matched_by_normalized_alias"] == 2
        assert counters["models_matched_by_make_prefixed_slug"] >= 1
        assert resolved[(make_slugs["hyundai"], "coupe-model")] == model_rows[-1].id
        assert (
            resolved[(make_slugs["bmw"], "3-series_gran_turismo")] == model_rows[4].id
        )
        ambiguous_ids = {
            resolved[(make_slugs["bmw"], "1-series")],
            resolved[(make_slugs["bmw"], "3-series")],
            resolved[(make_slugs["kia"], "cee~d")],
        }
        assert ambiguous_ids.isdisjoint({row.id for row in model_rows})
