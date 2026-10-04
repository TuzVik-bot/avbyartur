#!/usr/bin/env python3
"""Fetch the CC0 Wikidata make/model subset and validate it before writing."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "https://query.wikidata.org/sparql"
LICENSE_URL = "https://www.wikidata.org/wiki/Wikidata:Reuse"
CAR_MODEL_QID = "Q3231690"
QUERY_LIMIT = 25000
MAX_MODELS_PER_MAKE = 12

# Priority marques from the pilot plan. BMW uses its car-brand item rather
# than BMW AG; BelGee remains an unverified source entity.
MAKES = [
    ("Q124983953", "Audi"),
    ("Q796364", "BMW"),
    ("Q36008", "Mercedes-Benz"),
    ("Q246", "Volkswagen"),
    ("Q135700024", "Škoda"),
    ("Q125544573", "Renault"),
    ("Q6742", "Peugeot"),
    ("Q6746", "Citroën"),
    ("Q40966", "Opel"),
    ("Q20827633", "Ford"),
    ("Q53268", "Toyota"),
    ("Q35919", "Lexus"),
    ("Q20165", "Nissan"),
    ("Q35996", "Mazda"),
    ("Q125054811", "Hyundai"),
    ("Q35349", "Kia"),
    ("Q20827600", "Volvo"),
    ("Q739000", "Geely"),
    ("Q17324842", "Belgee"),
    ("Q98172997", "Chery"),
    ("Q98142348", "Changan"),
    ("Q28223947", "Haval"),
    ("Q27423", "BYD"),
    ("Q106621124", "Zeekr"),
    ("Q35676", "Lada"),
]

CONTROL_MODELS = {
    "BMW 3 Series": ("BMW", ("bmw 3 series",)),
    "Volkswagen Passat": ("Volkswagen", ("volkswagen passat", "passat")),
    "Belgee X50": ("Belgee", ("belgee x50",)),
    "Belgee X70": ("Belgee", ("belgee x70",)),
    "Geely Coolray": ("Geely", ("geely coolray", "geely binyue", "coolray")),
    "BYD Atto 3": ("BYD", ("byd atto 3", "yuan plus", "atto 3")),
    "Zeekr 001": ("Zeekr", ("zeekr 001",)),
}

# The alias follows the Russian search example in plan section 2.2.
MANUAL_MAKE_ALIASES = {"Q796364": ("БМВ",)}

CONTROL_GENERATION_EVIDENCE = {
    "Belgee X50": {
        "status": "insufficient",
        "summary": "Official reporting dates Belgee production and the X50 launch, and later names X50 and X50+ releases; it does not establish generation boundaries or end years.",
        "source_urls": [
            "https://belgee.ru/about-belgee/news/zavod-v-belarusi-proizvel-bolee-50-000-avtomobilei-belgee/",
            "https://belgee.ru/about-belgee/news/belgee-announces-start-production-and-exterior-of-new-x50/",
            "https://belgee.ru/about-belgee/news/belgee-accepting-orders-for-new-compact-crossover-the-x50plus/",
        ],
    },
    "Belgee X70": {
        "status": "insufficient",
        "summary": "Official reporting dates X70 assembly from summer 2024 but does not identify a generation or its end year.",
        "source_urls": [
            "https://belgee.ru/about-belgee/news/zavod-v-belarusi-proizvel-bolee-90-000-avtomobilei-belgee/",
        ],
    },
    "Geely Coolray": {
        "status": "insufficient",
        "summary": "Geely dates Binyue/Coolray's debut to 2018 and New Coolray launches to 2023, but does not define a generation transition or end year.",
        "source_urls": [
            "https://global.geely.com/en/news/2025/geely-coolray-one-million-global",
        ],
    },
    "BYD Atto 3": {
        "status": "insufficient",
        "summary": "BYD documents the Yuan Plus/ATTO 3 launch and a 2026 ATTO 3 EVO comprehensive update, but does not designate generation boundaries or an end year.",
        "source_urls": [
            "https://en.byd.com/news/byd-hits-the-australian-passenger-vehicle-market-with-atto-3/",
            "https://media.byd.com/new-byd-atto-3-evo-redefines-electric-family-suvs-with-awd-510km-of-range-and-220kw-charging/?lang=eng",
        ],
    },
    "Zeekr 001": {
        "status": "insufficient",
        "summary": "ZEEKR dates the first 001 to 2021 and calls the 2024 update all-new, but does not define generation boundaries or an end year.",
        "source_urls": [
            "https://zgh.com/media-center/news/2021-10-19/?lang=en",
            "https://www.zeekrlife.com/global/posts/the-all-new-zeekr-001-is-now-coming",
        ],
    },
}

# Labels and QIDs come from Wikidata items under the dataset's CC0 terms.
WIKIDATA_BODY_TYPES = (
    ("Q190578", "Седан", "sedan", ("sedan", "saloon", "седан (кузов)")),
    ("Q188886", "Универсал", "station-wagon", ("station wagon", "estate wagon", "wagon", "estate", "estate car")),
    ("Q216762", "Хэтчбэк", "hatchback", ("hatchback", "хетчбэк", "хетчбек", "хэчбек")),
    ("Q213853", "Купе", "coupe", ("coupe", "coupé", "купе (автомобиль)", "купе (кузов)")),
    ("Q55989", "Кабриолет", "convertible", ("convertible", "cabriolet", "drophead coupé")),
    ("Q192152", "SUV", "sport-utility-vehicle", ("sport utility vehicle", "Sports Utility Vehicles", "Паркетник")),
    ("Q223189", "Минивэн", "minivan", ("minivan", "people-carrier", "multi-purpose vehicle", "MPV", "MUV", "мини-вэн", "минивен")),
    ("Q1580019", "Лифтбэк", "liftback", ("liftback",)),
)


def make_query() -> str:
    qids = " ".join(f"wd:{qid}" for qid, _ in MAKES)
    return f"""SELECT DISTINCT ?make ?makeLabel ?makeBrand ?model ?brand ?modelLabel WHERE {{
  VALUES ?make {{ {qids} }}
  ?make rdfs:label ?makeLabel .
  FILTER (LANG(?makeLabel) IN ("ru", "en", "mul"))
  OPTIONAL {{
    ?make wdt:P31/wdt:P279* wd:Q431289 .
    BIND(?make AS ?makeBrand)
  }}
  OPTIONAL {{
    ?model wdt:P1716 ?brand ;
           wdt:P31/wdt:P279* wd:{CAR_MODEL_QID} ;
           rdfs:label ?modelLabel .
    FILTER (?brand = ?make)
    FILTER (LANG(?modelLabel) IN ("ru", "en"))
  }}
}} ORDER BY ?make ?model ?makeLabel ?modelLabel
LIMIT {QUERY_LIMIT}"""


QUERY = make_query()


def qid_from_uri(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]


def normalize(text: str) -> str:
    return " ".join(text.casefold().split())


def matches_candidate(label: str, candidate: str) -> bool:
    normalized_label = normalize(label)
    normalized_candidate = normalize(candidate)
    return normalized_label == normalized_candidate or normalized_label.startswith(normalized_candidate + " ")


def slugify(text: str, qid: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.casefold()).strip("-")
    return slug or qid.casefold()


def fetch_bindings() -> list[dict]:
    payload = urllib.parse.urlencode({"query": QUERY}).encode()
    request = urllib.request.Request(
        ENDPOINT,
        data=payload,
        headers={
            "Accept": "application/sparql-results+json",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "User-Agent": "AvtorinokCatalog/0.1 (Wikidata CC0 seed refresh)",
        },
        method="POST",
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                document = json.load(response)
            bindings = document["results"]["bindings"]
            if len(bindings) >= QUERY_LIMIT:
                raise RuntimeError("Wikidata response reached the query limit; refusing a possibly truncated seed")
            return bindings
        except urllib.error.HTTPError as error:
            if error.code not in {429, 500, 502, 503, 504} or attempt == 3:
                raise RuntimeError(f"Wikidata Query Service returned HTTP {error.code}") from error
        except urllib.error.URLError as error:
            if attempt == 3:
                raise RuntimeError(f"Could not reach Wikidata Query Service: {error.reason}") from error
        time.sleep(2**attempt)
    raise RuntimeError("Wikidata request failed")


def collect(bindings: list[dict]) -> tuple[list[dict], dict[str, set[str]]]:
    entities: dict[str, dict] = {
        qid: {
            "qid": qid,
            "make_labels": {},
            "models": {},
            "brand_class_verified": False,
            "brand_relation_verified": False,
        }
        for qid, _ in MAKES
    }
    for row in bindings:
        make_uri = row.get("make", {}).get("value")
        if not make_uri:
            continue
        make_qid = qid_from_uri(make_uri)
        if make_qid not in entities:
            raise RuntimeError(f"Wikidata returned unexpected make {make_qid}")
        make_label = row.get("makeLabel")
        if make_label:
            entities[make_qid]["make_labels"][make_label.get("xml:lang", "en")] = make_label["value"]
        if row.get("makeBrand", {}).get("value") == make_uri:
            entities[make_qid]["brand_class_verified"] = True
        model_uri = row.get("model", {}).get("value")
        model_label = row.get("modelLabel")
        brand_uri = row.get("brand", {}).get("value")
        if model_uri and model_label and brand_uri == make_uri:
            entities[make_qid]["brand_relation_verified"] = True
            model_qid = qid_from_uri(model_uri)
            labels = entities[make_qid]["models"].setdefault(model_qid, {})
            labels[model_label.get("xml:lang", "en")] = model_label["value"]

    records = []
    for make_qid, display_hint in MAKES:
        entity = entities[make_qid]
        labels = entity["make_labels"]
        if not labels:
            raise RuntimeError(f"No Russian or English label found for make {make_qid} ({display_hint})")
        record = {
            "qid": make_qid,
            "labels": labels,
            "models": entity["models"],
            "brand_class_verified": entity["brand_class_verified"],
            "brand_relation_verified": entity["brand_relation_verified"],
        }
        records.append(record)
    return records, {row["qid"]: set(row["models"]) for row in records}


def preferred_name(labels: dict[str, str]) -> str:
    return labels.get("ru") or labels.get("en") or next(iter(labels.values()))


def priority_rank(make_name: str, model_labels: dict[str, str]) -> int:
    normalized_labels = {normalize(label) for label in model_labels.values()}
    best = 100
    for index, (control, (control_make, candidates)) in enumerate(CONTROL_MODELS.items()):
        if normalize(make_name) != normalize(control_make):
            continue
        if any(matches_candidate(label, candidate) for label in normalized_labels for candidate in candidates):
            best = min(best, index)
    return best


def build_catalog(records: list[dict], retrieved_at: str, max_models: int) -> tuple[dict, dict]:
    make_records = []
    qid_to_name = {qid: label for qid, label in MAKES}
    source_by_qid = {
        qid: {"name": "Wikidata", "qid": qid, "url": f"https://www.wikidata.org/wiki/{qid}"}
        for qid, _ in MAKES
    }
    total_available_models = 0
    seeded_models = 0
    make_coverage = []
    for item in records:
        qid = item["qid"]
        labels = item["labels"]
        name = preferred_name(labels)
        models = []
        for model_qid, model_labels in item["models"].items():
            if not model_labels:
                continue
            models.append((model_qid, model_labels))
        total_available_models += len(models)
        models.sort(key=lambda row: (priority_rank(qid_to_name[qid], row[1]), normalize(preferred_name(row[1])), row[0]))
        selected = models[:max_models]
        seen_model_slugs: set[str] = set()
        nested_models = []
        for model_qid, model_labels in selected:
            model_name = preferred_name(model_labels)
            model_english_name = model_labels.get("en", model_name)
            model_slug = slugify(model_english_name, model_qid)
            if model_slug in seen_model_slugs:
                model_slug = f"{model_slug}-{model_qid.casefold()}"
            seen_model_slugs.add(model_slug)
            aliases = sorted(
                {label for label in model_labels.values() if label != model_name},
                key=normalize,
            )
            model_source = {
                "name": "Wikidata",
                "qid": model_qid,
                "url": f"https://www.wikidata.org/wiki/{model_qid}",
            }
            nested_models.append(
                {
                    "qid": model_qid,
                    "name": model_name,
                    "slug": model_slug,
                    "aliases": aliases,
                    "generations": [],
                    "source": {
                        **model_source,
                        "brand_property": "P1716",
                        "brand_qid": qid,
                        "model_class": CAR_MODEL_QID,
                    },
                }
            )
        seeded_models += len(nested_models)
        make_records.append(
            {
                "qid": qid,
                "name": name,
                "slug": slugify(qid_to_name[qid], qid),
                "aliases": sorted(
                    {label for label in labels.values() if label != name}
                    | set(MANUAL_MAKE_ALIASES.get(qid, ())),
                    key=normalize,
                ),
                "models": nested_models,
                "source": {
                    **source_by_qid[qid],
                    "label_property": "rdfs:label",
                    "brand_class": "Q431289" if item["brand_class_verified"] else None,
                    "vehicle_brand_relation_property": "P1716" if item["brand_relation_verified"] else None,
                },
            }
        )
        make_coverage.append(
            {
                "qid": qid,
                "name": name,
                "brand_class_verified": item["brand_class_verified"],
                "brand_relation_verified": item["brand_relation_verified"],
                "labeled_models_available": len(models),
                "models_in_seed": len(nested_models),
            }
        )

    make_by_name = {normalize(qid_to_name[make["qid"]]): make for make in make_records}
    selected_controls = []
    for control, (expected_make, candidates) in CONTROL_MODELS.items():
        make = make_by_name.get(normalize(expected_make))
        candidate_names = {normalize(candidate) for candidate in candidates}
        matched = next(
            (
                model for model in (make or {}).get("models", [])
                if any(
                    matches_candidate(label, candidate)
                    for label in {model["name"], *model.get("aliases", [])}
                    for candidate in candidate_names
                )
            ),
            None,
        )
        generation_count = len((matched or {}).get("generations", []))
        selected_controls.append(
            {
                "requested": control,
                "model_present_in_seed": matched is not None,
                "matching_model_qid": (matched or {}).get("qid"),
                "matching_model_slug": (matched or {}).get("slug"),
                "generation_count": generation_count,
                "body_variant_count": sum(
                    len(generation.get("body_variants", []))
                    for generation in (matched or {}).get("generations", [])
                ),
                "generation_depth_verified": False,
                **({"generation_evidence": CONTROL_GENERATION_EVIDENCE[control]}
                   if control in CONTROL_GENERATION_EVIDENCE else {}),
            }
        )

    catalog = {
        "schema_version": 1,
        "source": {
            "name": "Wikidata",
            "license": "CC0 1.0",
            "license_url": LICENSE_URL,
            "retrieved_at": retrieved_at,
            "query_url": ENDPOINT,
            "query_sha256": hashlib.sha256(QUERY.encode("utf-8")).hexdigest(),
        },
        "makes": make_records,
        "body_types": [
            {
                "qid": qid,
                "name": name,
                "slug": slug,
                "aliases": list(aliases),
                "source": {
                    "name": "Wikidata",
                    "qid": qid,
                    "url": f"https://www.wikidata.org/wiki/{qid}",
                    "retrieved_at": retrieved_at,
                },
            }
            for qid, name, slug, aliases in WIKIDATA_BODY_TYPES
        ],
        "regions": [],
    }
    coverage = {
        "generated_at": retrieved_at,
        "source": "data/catalog.json",
        "counts": {
            "makes": len(make_records),
            "makes_with_labeled_models": sum(1 for item in make_coverage if item["labeled_models_available"]),
            "labeled_models_available_before_cap": total_available_models,
            "models_in_seed": seeded_models,
            "generations": 0,
            "makes_verified_as_brand_entities": sum(
                item["brand_class_verified"] or item["brand_relation_verified"] for item in make_coverage
            ),
            "body_types": len(WIKIDATA_BODY_TYPES),
            "body_variants": 0,
            "regions": 0,
            "manual_models_added": 0,
            "manual_generation_rows_added": 0,
            "manual_body_variant_rows_added": 0,
        },
        "row_count_threshold": {"makes": 25, "models": 50},
        "row_count_threshold_met": len(make_records) >= 25 and seeded_models >= 50,
        "plan_acceptance": {
            "status": "unverified",
            "generation_depth_verified": False,
            "reason": "BMW generation 7 and Passat B9 have sourced starts but no supported end years; five other controls have launch/update evidence without verified generation boundaries.",
        },
        "model_cap_per_make": max_models,
        "makes": make_coverage,
        "control_models": selected_controls,
        "limitations": [
            "Models are included only when the model links directly to the selected make QID through brand property P1716 and car-model class Q3231690 or a subclass. A make entity is verified as a brand only when Wikidata classifies it as Q431289 or a labeled vehicle model links directly to it through P1716.",
            "A Wikidata QID and statement are provenance, not independent validation by the manufacturer; source statements may be incomplete or disputed.",
            "Only up to the configured model cap per make is included; this is a starter subset, not market coverage.",
            "The Wikidata make/model query does not infer generations, generation years, or generation-specific body variants; separately sourced additions remain visible in the merged catalog.",
            "BelGee is retained as a sourced entity, but its vehicle-brand class and direct linked labeled models are unverified in this snapshot.",
        ],
    }
    validate_catalog(catalog)
    return catalog, coverage


def validate_catalog(catalog: dict) -> None:
    if catalog.get("schema_version") != 1:
        raise ValueError("catalog schema_version must be 1")
    make_qids: set[str] = set()
    make_slugs: set[str] = set()
    for make in catalog.get("makes", []):
        qid = make.get("qid")
        slug = make.get("slug")
        if not qid or qid in make_qids:
            raise ValueError(f"missing or duplicate make qid: {qid}")
        if not slug or slug in make_slugs:
            raise ValueError(f"missing or duplicate make slug: {slug}")
        if not make.get("name"):
            raise ValueError(f"make {qid} has no display name")
        make_qids.add(qid)
        make_slugs.add(slug)
        model_qids: set[str] = set()
        model_slugs: set[str] = set()
        for model in make.get("models", []):
            model_qid = record_key(model)
            model_slug = model.get("slug")
            if not model_qid or model_qid in model_qids:
                raise ValueError(f"missing or duplicate model qid under {qid}: {model_qid}")
            if not model_slug or model_slug in model_slugs:
                raise ValueError(f"missing or duplicate model slug under {qid}: {model_slug}")
            if not model.get("name"):
                raise ValueError(f"model {model_qid} has no display name")
            if not is_non_wikidata_record(model):
                source = model.get("source", {})
                if source.get("brand_property") != "P1716" or source.get("brand_qid") != qid:
                    raise ValueError(f"model {model_qid} has no direct Wikidata brand provenance for make {qid}")
            model_qids.add(model_qid)
            model_slugs.add(model_slug)


def is_non_wikidata_record(record: dict) -> bool:
    source = record.get("source")
    return not isinstance(source, dict) or source.get("name") != "Wikidata"


def record_key(record: dict) -> str | None:
    value = record.get("qid") or record.get("external_id") or record.get("id") or record.get("slug")
    return str(value) if value is not None else None


def merge_catalog_records(previous_rows: list[dict], generated_rows: list[dict]) -> list[dict]:
    previous_by_key = {record_key(row): row for row in previous_rows if record_key(row)}
    merged = []
    seen = set()
    for row in generated_rows:
        key = record_key(row)
        previous_row = previous_by_key.get(key)
        merged.append(
            previous_row if previous_row and is_non_wikidata_record(previous_row) else row
        )
        if key:
            seen.add(key)
    merged.extend(row for key, row in previous_by_key.items() if key not in seen)
    merged.extend(
        row for row in previous_rows
        if not record_key(row) and is_non_wikidata_record(row)
    )
    return merged


def merge_existing_generations(previous_model: dict, generated_model: dict) -> None:
    previous_generations = previous_model.get("generations", [])
    generated_generations = generated_model.get("generations", [])
    previous_by_key = {
        record_key(row): row for row in previous_generations if record_key(row)
    }
    merged_generations = []
    seen_generations = set()
    for generation in generated_generations:
        generation_key = record_key(generation)
        previous_generation = previous_by_key.get(generation_key)
        if previous_generation and is_non_wikidata_record(previous_generation):
            merged_generations.append(previous_generation)
        else:
            if previous_generation:
                generation["body_variants"] = merge_catalog_records(
                    previous_generation.get("body_variants", []),
                    generation.get("body_variants", []),
                )
            merged_generations.append(generation)
        if generation_key:
            seen_generations.add(generation_key)
    merged_generations.extend(
        row for key, row in previous_by_key.items() if key not in seen_generations
    )
    merged_generations.extend(
        row for row in previous_generations
        if not record_key(row) and is_non_wikidata_record(row)
    )
    generated_model["generations"] = merged_generations


def merge_existing_catalog(path: Path, generated: dict) -> dict:
    if not path.exists():
        return generated
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"existing catalog cannot be read safely: {error}") from error
    if previous.get("schema_version") != 1:
        raise ValueError("existing catalog is not schema version 1; refusing to replace it")

    previous_makes = {record_key(row): row for row in previous.get("makes", []) if record_key(row)}
    generated_qids = {row["qid"] for row in generated["makes"]}
    merged_makes = []
    for make in generated["makes"]:
        old_make = previous_makes.get(make["qid"])
        if old_make and is_non_wikidata_record(old_make):
            merged_makes.append(old_make)
            continue
        if old_make:
            old_models = {record_key(row): row for row in old_make.get("models", []) if record_key(row)}
            merged_models = []
            seen_models = set()
            for model in make["models"]:
                model_key = record_key(model)
                old_model = old_models.get(model_key)
                if old_model and is_non_wikidata_record(old_model):
                    merged_models.append(old_model)
                else:
                    if old_model:
                        merge_existing_generations(old_model, model)
                    merged_models.append(model)
                seen_models.add(model_key)
            merged_models.extend(
                row for key, row in old_models.items()
                if key not in seen_models
                and (is_non_wikidata_record(row) or row.get("generations"))
            )
            merged_models.extend(
                row for row in old_make.get("models", [])
                if not record_key(row) and is_non_wikidata_record(row)
            )
            make["models"] = merged_models
        merged_makes.append(make)

    merged_makes.extend(
        row for key, row in previous_makes.items()
        if key not in generated_qids and is_non_wikidata_record(row)
    )
    generated["makes"] = merged_makes
    generated["body_types"] = merge_catalog_records(
        previous.get("body_types", []), generated.get("body_types", [])
    )
    generated["regions"] = previous.get("regions", generated.get("regions", []))
    if "geography_source" in previous:
        generated["geography_source"] = previous["geography_source"]
    validate_catalog(generated)
    return generated


def update_control_generation_counts(coverage: dict, catalog: dict) -> None:
    models_by_key = {
        key: model
        for make in catalog.get("makes", [])
        for model in make.get("models", [])
        for key in (model.get("qid"), model.get("slug"))
        if key
    }
    for control in coverage.get("control_models", []):
        model = models_by_key.get(control.get("matching_model_qid"))
        if model is None:
            model = models_by_key.get(control.get("matching_model_slug"))
        generations = (model or {}).get("generations", [])
        control["generation_count"] = len(generations)
        control["body_variant_count"] = sum(
            len(generation.get("body_variants", [])) for generation in generations
        )


def preserve_existing_control_slugs(path: Path, coverage: dict, catalog: dict) -> None:
    if not path.exists():
        return
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"existing coverage cannot be read safely: {error}") from error

    models_by_slug = {
        model.get("slug"): model
        for make in catalog.get("makes", [])
        for model in make.get("models", [])
        if model.get("slug")
    }
    previous_by_control = {
        control.get("requested"): control
        for control in previous.get("control_models", [])
        if control.get("requested")
    }
    for control in coverage.get("control_models", []):
        old_control = previous_by_control.get(control.get("requested"), {})
        old_slug = old_control.get("matching_model_slug")
        if old_control.get("matching_model_qid") or old_slug not in models_by_slug:
            continue
        control["matching_model_qid"] = None
        control["matching_model_slug"] = old_slug
        control["model_present_in_seed"] = old_control.get("model_present_in_seed", True)


def atomic_write(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False) as stream:
            temp_name = stream.name
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp_name, mode)
        os.replace(temp_name, path)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="atomically replace catalog and coverage JSON files")
    parser.add_argument("--output", type=Path, default=ROOT / "data/catalog.json")
    parser.add_argument("--coverage-output", type=Path, default=ROOT / "data/catalog-coverage.json")
    parser.add_argument("--max-models-per-make", type=int, default=MAX_MODELS_PER_MAKE)
    args = parser.parse_args()
    if args.max_models_per_make < 1 or args.max_models_per_make > 100:
        parser.error("--max-models-per-make must be between 1 and 100")

    try:
        bindings = fetch_bindings()
        records, _ = collect(bindings)
        retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        catalog, coverage = build_catalog(records, retrieved_at, args.max_models_per_make)
        catalog = merge_existing_catalog(args.output, catalog)
        validate_catalog(catalog)
        preserve_existing_control_slugs(args.coverage_output, coverage, catalog)
        coverage["counts"]["makes"] = len(catalog["makes"])
        coverage["counts"]["models_in_seed"] = sum(len(make.get("models", [])) for make in catalog["makes"])
        coverage["counts"]["makes_with_labeled_models"] = sum(1 for make in catalog["makes"] if make.get("models"))
        coverage["counts"]["generations"] = sum(
            len(model.get("generations", []))
            for make in catalog["makes"]
            for model in make.get("models", [])
        )
        all_models = [model for make in catalog["makes"] for model in make.get("models", [])]
        all_generations = [generation for model in all_models for generation in model.get("generations", [])]
        all_body_variants = [
            variant
            for generation in all_generations
            for variant in generation.get("body_variants", [])
        ]
        coverage["counts"]["body_types"] = len(catalog.get("body_types", []))
        coverage["counts"]["body_variants"] = len(all_body_variants)
        coverage["counts"]["manual_models_added"] = sum(
            is_non_wikidata_record(model) for model in all_models
        )
        coverage["counts"]["manual_generation_rows_added"] = sum(
            is_non_wikidata_record(generation) for generation in all_generations
        )
        coverage["counts"]["manual_body_variant_rows_added"] = sum(
            is_non_wikidata_record(variant) for variant in all_body_variants
        )
        coverage["counts"]["makes_verified_as_brand_entities"] = sum(
            1 for make in catalog["makes"]
            if make.get("source", {}).get("brand_class") == "Q431289"
            or make.get("source", {}).get("vehicle_brand_relation_property") == "P1716"
        )
        for row in coverage["makes"]:
            make = next((item for item in catalog["makes"] if item.get("qid") == row["qid"]), None)
            row["models_in_seed"] = len((make or {}).get("models", []))
        update_control_generation_counts(coverage, catalog)
        threshold = coverage["row_count_threshold"]
        coverage["row_count_threshold_met"] = (
            coverage["counts"]["makes"] >= threshold["makes"]
            and coverage["counts"]["models_in_seed"] >= threshold["models"]
        )
        coverage["plan_acceptance"]["generation_rows_present"] = coverage["counts"]["generations"]
        coverage["plan_acceptance"]["generation_depth_verified"] = False
        if args.write:
            atomic_write(args.output, catalog)
            atomic_write(args.coverage_output, coverage)
        print(json.dumps(coverage, ensure_ascii=False, indent=2))
        if args.write:
            print(f"Wrote {args.output} and {args.coverage_output}")
        else:
            print("Dry run only; pass --write to replace the files.")
        return 0
    except (OSError, ValueError, RuntimeError, urllib.error.URLError, KeyError) as error:
        print(f"Catalog refresh failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
