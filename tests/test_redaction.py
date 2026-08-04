"""Blind screening must not depend on model judgment — these run on the code path.

Every case here comes from a real failure observed while testing with a local model.
"""

import re

import pytest

from core.redaction import scrub_residual_identity as scrub

NAME = "ANA GARCÍA"


def test_catches_partial_redaction_left_by_the_model():
    # llama3.1 stripped the surname but left the first name: "ANA [NAME]"
    text, caught = scrub("ANA [NAME]\nCustomer Success Manager", NAME)
    assert not re.search(r"\bANA\b", text, re.I)
    assert "name" in caught


def test_does_not_damage_words_containing_a_name_substring():
    text, _ = scrub("Customer Success Manager", NAME)
    assert "Manager" in text  # M-ana-ger must survive


@pytest.mark.parametrize(
    "content",
    [
        "2019 - 2021",
        "3+ years of experience",
        "ARR USD 2.4M across 28 accounts",
        "NRR 118% average",
        "cutting time-to-value from 45 to 21 days",
    ],
)
def test_professional_signal_survives(content):
    """Tenure and metrics are exactly what the rubric scores — never redact them."""
    text, caught = scrub(content, NAME)
    assert text == content
    assert caught == []


@pytest.mark.parametrize(
    "phone",
    ["+54 11 5555-8899", "(011) 4555-8899", "+1 (415) 555-0132"],
)
def test_real_phone_numbers_are_removed(phone):
    text, caught = scrub(f"Call me at {phone} anytime", NAME)
    assert not re.search(r"\d", text)
    assert "phone" in caught


def test_email_is_matched_before_name_scrubbing_breaks_it():
    text, caught = scrub("ana@mail.com", NAME)
    assert "@" not in text and "mail.com" not in text
    assert "email" in caught


def test_removes_every_identity_channel_at_once():
    text, caught = scrub(
        "ANA GARCÍA — ana@mail.com — +54 11 5555 8899 — linkedin.com/in/anagarcia", NAME
    )
    assert not re.search(r"\bANA\b", text, re.I)
    assert "@" not in text and "5555" not in text and "anagarcia" not in text
    assert set(caught) == {"name", "email", "phone", "URL"}


def test_name_particles_are_not_scrubbed_as_words():
    text, _ = scrub("Worked at de Havilland on la Plata project", "Ana de la Cruz")
    assert "de Havilland" in text and "la Plata" in text


def test_matching_is_case_and_accent_aware():
    text, _ = scrub("garcía led it; GARCÍA mentored", NAME)
    assert "garc" not in text.lower()


def test_clean_text_is_left_untouched():
    original = "Nothing identifying here. 2019 - 2021."
    text, caught = scrub(original, NAME)
    assert text == original
    assert caught == []
