"""Phone normalisation, matching the rules of the existing n8n phone-formatter.js."""

import re


def normalize_phone(raw: object, default_country: str = "234") -> str | None:
    """Return E.164 (+2348012345678) or None if the number can't be used on WhatsApp.

    Handles Excel quirks: numbers stored as floats ("8012345678.0") and dropped leading zeros.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if re.fullmatch(r"\d+\.0", text):
        text = text[:-2]
    has_plus = text.startswith("+")
    digits = re.sub(r"\D", "", text)
    if not digits:
        return None

    if has_plus:
        pass
    elif digits.startswith("00"):
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        # Local Nigerian format 08012345678
        digits = default_country + digits[1:]
    elif len(digits) == 10 and digits[0] in "789":
        # Leading zero lost in Excel: 8012345678
        digits = default_country + digits
    elif digits.startswith(default_country + "0") and len(digits) == 14:
        # 23408012345678: people often keep the 0 after the country code
        digits = default_country + digits[4:]

    if len(digits) < 8 or len(digits) > 15:
        return None
    if not has_plus and (digits.startswith("0") or len(digits) <= 10):
        return None  # a local number of the wrong length; we can't guess the country
    if digits.startswith(default_country) and len(digits) != 13:
        return None  # Nigerian mobiles are 234 + 10 digits
    return "+" + digits


def wa_id(e164: str) -> str:
    """WhatsApp Cloud API wants digits only."""
    return e164.lstrip("+")
