"""Deterministic safety net for blind screening.

Models redact identity inconsistently — small local models especially, which may
strip a surname but leave the first name behind. Blind screening is a guarantee we
should not stake on model judgment, so every anonymized resume is swept in code
before it reaches the evaluator.
"""

import re

# Name particles too common as ordinary words to scrub on their own.
PARTICLES = {
    "de", "del", "la", "las", "los", "van", "der", "den", "von", "da", "das",
    "do", "dos", "di", "du", "el", "al", "bin", "ibn", "mac", "mc", "san", "santa",
}

EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
URL_RE = re.compile(r"\b(?:https?://|www\.)\S+|\b(?:linkedin\.com|github\.com)/\S+", re.IGNORECASE)
# Phone candidates never span lines; the digit count below is what actually decides,
# so date ranges like "2019 - 2021" (8 digits) are left alone.
PHONE_CANDIDATE_RE = re.compile(r"\(?\+?\d[\d ().-]{6,}\d")
MIN_PHONE_DIGITS = 9


def _scrub_phones(text: str) -> tuple[str, int]:
    """Replace only runs holding enough digits to be a real phone number."""
    hits = 0

    def repl(match: re.Match) -> str:
        nonlocal hits
        if sum(c.isdigit() for c in match.group()) >= MIN_PHONE_DIGITS:
            hits += 1
            return "[CONTACT]"
        return match.group()

    return PHONE_CANDIDATE_RE.sub(repl, text), hits


def _name_tokens(candidate_name: str) -> list[str]:
    tokens = []
    for raw in re.split(r"[\s,]+", candidate_name.strip()):
        token = raw.strip(".")
        if len(token) >= 3 and token.casefold() not in PARTICLES:
            tokens.append(token)
    # Longest first, so "Ana María" is replaced before its parts.
    return sorted(set(tokens), key=len, reverse=True)


def scrub_residual_identity(text: str, candidate_name: str) -> tuple[str, list[str]]:
    """Remove identity the model left behind. Returns the text and what was caught."""
    caught: list[str] = []

    # Contacts first: an email whose local part is the candidate's name must be
    # matched whole, before name scrubbing rewrites it into something unmatchable.
    for label, pattern in (("email", EMAIL_RE), ("URL", URL_RE)):
        text, n = pattern.subn("[CONTACT]", text)
        if n:
            caught.append(label)

    text, phone_hits = _scrub_phones(text)
    if phone_hits:
        caught.append("phone")

    for token in _name_tokens(candidate_name):
        pattern = re.compile(rf"\b{re.escape(token)}\b", re.IGNORECASE)
        text, n = pattern.subn("[NAME]", text)
        if n:
            caught.append("name")

    # Collapse the placeholder runs left by adjacent replacements ("[NAME] [NAME]").
    text = re.sub(r"(\[NAME\])(\s*\[NAME\])+", r"\1", text)
    text = re.sub(r"(\[CONTACT\])(\s*\[CONTACT\])+", r"\1", text)

    return text, sorted(set(caught))
