#!/usr/bin/env python3
"""Service-aware Compose image validation for the 2026-10-21 first-wave release."""
import json
import re
import sys

TAG_PATTERN = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}\Z")
DIGEST_PATTERN = re.compile(r"sha256:[A-Fa-f0-9]{64}\Z")
REPOSITORY_PATTERN = re.compile(r"[a-z0-9][a-z0-9./:_-]*\Z")


def parse_image(image):
    if not isinstance(image, str) or any(ch.isspace() for ch in image) or image.count("@") > 1:
        raise ValueError("unsafe image reference")
    image_name, separator, digest = image.partition("@")
    if separator and not DIGEST_PATTERN.fullmatch(digest):
        raise ValueError("unsafe image reference")
    slash = image_name.rfind("/")
    colon = image_name.rfind(":")
    if colon <= slash:
        raise ValueError("unsafe image reference")
    tag = image_name[colon + 1:]
    repository = image_name[:colon]
    if (
        not REPOSITORY_PATTERN.fullmatch(repository)
        or "//" in repository
        or repository.endswith("/")
        or not TAG_PATTERN.fullmatch(tag)
        or tag.casefold() in {"local", "latest"}
    ):
        raise ValueError("unsafe image reference")
    return repository, tag


def validate(config, expected_tag, worker_expected):
    services = config.get("services") if isinstance(config, dict) else None
    if not isinstance(services, dict) or not services:
        raise ValueError("unsafe image reference")
    images = {}
    for name, service in services.items():
        image = service.get("image") if isinstance(service, dict) else None
        if image is None:
            raise ValueError("unsafe image reference")
        parse_image(image)
        images[name] = image
    expected_services = {
        "api": ("avtorinok-api", expected_tag),
        "web": ("avtorinok-web", expected_tag),
    }
    for service, (repo, tag) in expected_services.items():
        image = images.get(service)
        if image is None:
            raise ValueError("effective image tags do not match")
        actual_repo, actual_tag = parse_image(image)
        if actual_repo.rsplit("/", 1)[-1] != repo or actual_tag != tag:
            raise ValueError("effective image tags do not match")
    worker_image = images.get("worker")
    if worker_image != worker_expected:
        raise ValueError("effective image tags do not match")
    return True


def self_test():
    digest = "sha256:" + "a" * 64
    good = {"services": {
        "db": {"image": "postgres:17.11-alpine"},
        "api": {"image": "avtorinok-api:competitive-first-wave-20261021-r1"},
        "worker": {"image": "avtorinok-api:pilot-catalog-product-20261015T1241Z"},
        "web": {"image": "avtorinok-web:competitive-first-wave-20261021-r1"},
        "test-mail": {"image": "axllent/mailpit:v1.31.4@" + digest},
    }}
    expected = "competitive-first-wave-20261021-r1"
    worker = "avtorinok-api:pilot-catalog-product-20261015T1241Z"
    assert validate(good, expected, worker)
    for service in ("api", "web"):
        bad = json.loads(json.dumps(good))
        repo = "avtorinok-api" if service == "api" else "avtorinok-web"
        bad["services"][service]["image"] = repo + ":wrong-tag"
        try:
            validate(bad, expected, worker)
        except ValueError as error:
            assert str(error) == "effective image tags do not match"
        else:
            raise AssertionError(f"accepted invalid {service} tag")
    bad_worker = json.loads(json.dumps(good))
    bad_worker["services"]["worker"]["image"] = "avtorinok-api:unexpected-worker"
    try:
        validate(bad_worker, expected, worker)
    except ValueError as error:
        assert str(error) == "effective image tags do not match"
    else:
        raise AssertionError("accepted unexpected worker tag")
    print("SELF_TEST=PASS api_bad_rejected web_bad_rejected unchanged_worker_accepted unexpected_worker_rejected")


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        self_test()
        raise SystemExit(0)
    try:
        with open(sys.argv[1], encoding="utf-8") as source:
            config = json.load(source)
        validate(config, sys.argv[2], sys.argv[3])
    except Exception as error:
        message = str(error)
        if message not in {"unsafe image reference", "effective image tags do not match"}:
            message = "unsafe image reference"
        print(message)
        raise SystemExit(1)
