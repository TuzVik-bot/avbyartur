"""Pure, additive reconciliation of permissioned Onliner make/model names."""
import re
import unicodedata


def normalized(value):
    text = unicodedata.normalize("NFKD", value.casefold())
    return re.sub(r"[^a-zа-я0-9+]+", "", "".join(c for c in text if not unicodedata.combining(c)))


MAKE_EQUIVALENTS = {"vaz": "lada"}
# Reviewed exact-slug crosswalk against the pre-import production dictionary.
# These names remain untouched; only the source's shorter display label differs.
MODEL_DISPLAY_EQUIVALENTS = {
    ("chery", "amulet"): {"amuleta15"},
    ("chery", "fora"): {"foraa21"},
    ("chery", "indis"): {"indiss18d"},
    ("chery", "qq"): {"qqsweet"},
    ("chery", "tiggo"): {"tiggot11"},
    ("geely", "ck"): {"ckotaka"},
    ("toyota", "solara"): {"solara"},
}


def labels(row):
    return [row["name"], row["slug"], *(row.get("aliases") or [])]


def model_keys(row, prefixes, *, include_slug=True):
    keys = set()
    values = labels(row) if include_slug else [row["name"], *(row.get("aliases") or [])]
    for value in values:
        key = normalized(value)
        keys.add(key)
        for prefix in prefixes:
            if key.startswith(prefix) and len(key) > len(prefix):
                keys.add(key[len(prefix):])
    return keys


def validate_source(source):
    if source.get("format") != "onliner-catalog-v1" or not isinstance(source.get("makes"), list) or not source["makes"]:
        raise ValueError("Invalid Onliner catalog document")
    make_ids, make_slugs, model_ids = set(), set(), set()
    for make in source["makes"]:
        for row, ids, slugs in [(make, make_ids, make_slugs), *[(model, model_ids, set()) for model in make.get("models", [])]]:
            if not isinstance(row.get("id"), int) or row["id"] <= 0:
                raise ValueError("Invalid source identity")
            if not isinstance(row.get("name"), str) or not row["name"].strip() or len(row["name"]) > 180:
                raise ValueError("Invalid source name")
            if not isinstance(row.get("slug"), str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,139}", row["slug"]):
                raise ValueError("Invalid source slug")
            if row["id"] in ids or row["slug"] in slugs:
                raise ValueError("Duplicate source identity")
            ids.add(row["id"])
            slugs.add(row["slug"])
        if not isinstance(make.get("models"), list):
            raise ValueError("Missing source models")
        if len({m["slug"] for m in make["models"]}) != len(make["models"]):
            raise ValueError("Duplicate source model slug")


def reconcile(source, existing):
    validate_source(source)
    plan = {"makes": [], "models": [], "aliases": [], "categories": [], "coverage": [], "equivalent_models": []}
    targets = [{**row, "models": [dict(model) for model in row["models"]]} for row in existing["makes"]]
    for make in source["makes"]:
        keys = {normalized(value) for value in labels(make)}
        if make["slug"] in MAKE_EQUIVALENTS:
            keys.add(normalized(MAKE_EQUIVALENTS[make["slug"]]))
        matches = [row for row in targets if keys & {normalized(v) for v in labels(row)}]
        if len(matches) > 1:
            raise ValueError(f"Ambiguous make: {make['name']}")
        if matches:
            target = matches[0]
        else:
            target = {"slug": make["slug"], "name": make["name"], "models": []}
            targets.append(target)
            plan["makes"].append({"source_id": make["id"], "slug": make["slug"], "name": make["name"]})
        if make["slug"] in MAKE_EQUIVALENTS and normalized(make["name"]) not in {normalized(v) for v in labels(target)}:
            plan["aliases"].append({"make_slug": target["slug"], "alias": make["name"]})
            target["aliases"] = [*(target.get("aliases") or []), make["name"]]
        prefixes = {normalized(v) for v in labels(make) + labels(target)} - {""}
        coverage = {"source_id": make["id"], "source_slug": make["slug"], "target_slug": target["slug"], "models": []}
        for model in make["models"]:
            source_keys = model_keys(model, prefixes)
            candidates = [row for row in target["models"] if source_keys & model_keys(row, prefixes)]
            slug_matches = [row for row in target["models"] if row["slug"] == model["slug"]]
            accepted_names = model_keys(model, prefixes, include_slug=False) | MODEL_DISPLAY_EQUIVALENTS.get((make["slug"], model["slug"]), set())
            if slug_matches and not all(accepted_names & model_keys(row, prefixes, include_slug=False) for row in slug_matches):
                raise ValueError(f"Model slug/name conflict: {make['name']} {model['name']}")
            if candidates:
                chosen = sorted(candidates, key=lambda row: (row["slug"] != model["slug"], row["slug"]))[0]
                if len(candidates) > 1:
                    plan["equivalent_models"].append({"make": make["name"], "model": model["name"], "existing_slugs": [row["slug"] for row in candidates]})
            else:
                chosen = {"slug": model["slug"], "name": model["name"], "source_metadata": {"category_codes": ["cars"]}}
                target["models"].append(chosen)
                plan["models"].append({"source_id": model["id"], "source_make_id": make["id"], "make_slug": target["slug"], "slug": chosen["slug"], "name": chosen["name"]})
            metadata = chosen.get("source_metadata") or {}
            categories = metadata.get("category_codes") or []
            if not isinstance(categories, list):
                raise ValueError("Invalid existing category metadata")
            if "cars" not in categories:
                plan["categories"].append({"make_slug": target["slug"], "model_slug": chosen["slug"]})
                chosen["source_metadata"] = {**metadata, "category_codes": [*categories, "cars"]}
            coverage["models"].append({"source_id": model["id"], "source_slug": model["slug"], "target_slug": chosen["slug"]})
        plan["coverage"].append(coverage)
    return plan
