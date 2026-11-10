"""docker-compose.yml and .env.example must stay in sync with Settings."""

import re
from pathlib import Path

import yaml
from app.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"
ENV_EXAMPLE_PATH = REPO_ROOT / ".env.example"
COMPOSE_VARIABLE = re.compile(r"\$\{([A-Z][A-Z0-9_]*)")
# Settings the API and worker intentionally do not receive from compose.
INTENTIONALLY_OMITTED: dict[str, str] = {}


def _compose() -> dict:
    return yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))


def _settings_env_names() -> set[str]:
    return {name.upper() for name in Settings.model_fields}


def _service_environment(service: str) -> dict:
    return _compose()["services"][service]["environment"]


def test_api_and_worker_receive_every_setting():
    expected = _settings_env_names() - set(INTENTIONALLY_OMITTED)
    for service in ("api", "worker"):
        missing = expected - set(_service_environment(service))
        assert not missing, f"{service} is missing settings: {sorted(missing)}"


def test_compose_does_not_pass_unknown_backend_settings():
    # Settings forbids extra fields, so an unknown key would break startup.
    unknown = set(_service_environment("api")) - _settings_env_names()
    assert not unknown


def test_trusted_proxy_default_covers_docker_private_ranges():
    value = _service_environment("api")["TRUSTED_PROXY_CIDRS"]
    for cidr in ("172.16.0.0/12", "10.0.0.0/8", "192.168.0.0/16"):
        assert cidr in value


def test_web_receives_analytics_measurement_id():
    assert _service_environment("web")["GA_MEASUREMENT_ID"] == "${GA_MEASUREMENT_ID:-}"


def _env_example_keys() -> set[str]:
    keys = set()
    for line in ENV_EXAMPLE_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            keys.add(stripped.partition("=")[0].strip())
    return keys


def test_env_example_lists_every_compose_variable():
    referenced = set(COMPOSE_VARIABLE.findall(COMPOSE_PATH.read_text(encoding="utf-8")))
    missing = referenced - _env_example_keys()
    assert not missing, f".env.example is missing: {sorted(missing)}"


def test_env_example_lists_every_setting():
    expected = _settings_env_names() - {"DATABASE_URL", "CATALOG_PATH", "MEDIA_ROOT"}
    missing = expected - _env_example_keys()
    assert not missing, f".env.example is missing: {sorted(missing)}"


def test_web_receives_assistant_budget_settings():
    web = _service_environment("web")
    assert web["ASSISTANT_FALLBACK_MODELS"] == "${ASSISTANT_FALLBACK_MODELS:-}"
    assert web["ASSISTANT_DAILY_MODEL_BUDGET"] == "${ASSISTANT_DAILY_MODEL_BUDGET:-45}"


def test_override_files_give_api_and_worker_the_same_backend_settings():
    for path in sorted(REPO_ROOT.glob("docker-compose.*.yml")):
        services = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("services", {})
        api_env = (services.get("api") or {}).get("environment") or {}
        worker_env = (services.get("worker") or {}).get("environment") or {}
        assert api_env == worker_env, f"{path.name}: api and worker environment differ"
