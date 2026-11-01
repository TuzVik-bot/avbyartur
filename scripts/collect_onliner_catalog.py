"""Collect the permissioned Onliner make/model dictionary, one request at a time."""
import argparse
import datetime
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://ab.onliner.by/sdapi/ab.api"


def fetch(path):
    for attempt in range(4):
        try:
            request = urllib.request.Request(BASE + path, headers={"Accept": "application/json", "User-Agent": "avtorinok-catalog/1.0"})
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504):
                raise
        except (TimeoutError, urllib.error.URLError):
            if attempt == 3:
                raise
        time.sleep(2 ** attempt + 1)
    raise RuntimeError("Source unavailable after four attempts")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cache = args.output.with_suffix(".cache")
    cache.mkdir(parents=True, exist_ok=True)
    dictionary = fetch("/dictionaries")
    makes = []
    for index, make in enumerate(dictionary["manufacturer"], 1):
        path = cache / f"{make['id']}.json"
        if path.exists():
            detail = json.loads(path.read_text())
        else:
            time.sleep(1)
            detail = fetch(f"/manufacturers/{make['id']}")
            path.write_text(json.dumps(detail, ensure_ascii=False))
        assert detail["id"] == make["id"] and isinstance(detail["models"], list)
        assert len(detail["models"]) == detail["counters"]["models"]
        makes.append({**make, "models": [{key: model[key] for key in ("id", "name", "slug")} for model in detail["models"]]})
        if index % 25 == 0:
            print(f"Collected {index}/{len(dictionary['manufacturer'])} makes", flush=True)
    document = {"format": "onliner-catalog-v1", "source_url": BASE, "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "permission": "Owner confirmed written permission for required catalog information on 2026-11-01", "makes": makes}
    args.output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n")
    print(f"Complete: {len(makes)} makes, {sum(len(make['models']) for make in makes)} models", flush=True)


if __name__ == "__main__":
    main()
