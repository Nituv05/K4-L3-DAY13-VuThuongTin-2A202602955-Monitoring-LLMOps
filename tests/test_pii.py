from app.pii import scrub_text
from app.logging_config import scrub_event


def test_scrub_email() -> None:
    out = scrub_text("Email me at student@vinuni.edu.vn")
    assert "student@" not in out
    assert "REDACTED_EMAIL" in out


def test_scrub_common_vietnamese_phone_formats() -> None:
    phone_numbers = (
        "0901234567",
        "090 123 4567",
        "090.123.4567",
        "090-123-4567",
        "+84 90 123 4567",
    )

    for phone_number in phone_numbers:
        out = scrub_text(f"Contact: {phone_number}")
        assert phone_number not in out
        assert "REDACTED_PHONE_VN" in out


def test_scrub_cccd() -> None:
    cccd = "079123456789"
    out = scrub_text(f"CCCD: {cccd}")

    assert cccd not in out
    assert "REDACTED_CCCD" in out


def test_scrub_payment_card_with_spaces_or_hyphens() -> None:
    for card_number in ("4111111111111111", "4111 1111 1111 1111", "4111-1111-1111-1111"):
        out = scrub_text(f"Card: {card_number}")

        assert card_number not in out
        assert "REDACTED_CREDIT_CARD" in out


def test_scrub_event_redacts_nested_and_top_level_strings() -> None:
    event = {
        "event": "request_failed for student@vinuni.edu.vn",
        "exception": "Contact 090 123 4567",
        "payload": {"details": ["CCCD 079123456789"]},
    }

    safe = scrub_event(None, "error", event)

    serialized = str(safe)
    for raw in ("student@vinuni.edu.vn", "090 123 4567", "079123456789"):
        assert raw not in serialized
