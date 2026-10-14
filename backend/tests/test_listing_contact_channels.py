from pydantic import ValidationError

from app.schemas import ListingForm


def test_listing_form_accepts_explicit_opt_in_messenger_links() -> None:
    payload = ListingForm(
        telegram_contact_url="https://t.me/market_seller",
        viber_contact_url="https://viber.me/market-seller",
    )

    assert payload.telegram_contact_url == "https://t.me/market_seller"
    assert payload.viber_contact_url == "https://viber.me/market-seller"


def test_listing_form_rejects_messenger_lookalike_domains() -> None:
    try:
        ListingForm(telegram_contact_url="https://t.me.attacker.example/market_seller")
    except ValidationError as error:
        assert "telegram_contact_url" in str(error)
    else:
        raise AssertionError("Telegram lookalike domain must be rejected")


def test_listing_form_rejects_non_https_viber_links() -> None:
    try:
        ListingForm(viber_contact_url="http://viber.me/market-seller")
    except ValidationError as error:
        assert "viber_contact_url" in str(error)
    else:
        raise AssertionError("Non-HTTPS Viber links must be rejected")
