from pydantic import ValidationError

from app.config import Settings


def test_validation_error_hides_values_from_unknown_dotenv_fields(tmp_path):
    secret_marker = "dummy-secret"
    env_file = tmp_path / "settings.env"
    env_file.write_text(f"UNKNOWN_SECRET={secret_marker}\n", encoding="utf-8")

    try:
        Settings(_env_file=env_file)
    except ValidationError as exc:
        assert "extra_forbidden" in str(exc)
        assert secret_marker not in str(exc)
    else:
        raise AssertionError("unknown dotenv fields must remain forbidden")


def test_public_app_url_requires_a_secure_origin_without_credentials():
    try:
        Settings(public_app_url="http://mailer:private-value@cars.example.test/path")
    except ValidationError as exc:
        assert "PUBLIC_APP_URL" in str(exc)
        assert "private-value" not in str(exc)
    else:
        raise AssertionError("public app URL must be an HTTPS origin without credentials")
