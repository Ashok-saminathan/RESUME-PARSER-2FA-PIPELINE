import re

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$")


def normalize_email(value: str) -> str:
    value = value.strip().lower()
    if len(value) > 254 or not EMAIL_RE.match(value):
        raise ValueError("Enter a valid email address")
    return value


def normalize_phone(raw: str) -> str:
    """Return an E.164 phone number. Bare 10-digit numbers are treated as Indian mobiles."""
    s = raw.strip()
    digits = re.sub(r"\D", "", s)
    if s.startswith("+"):
        candidate = "+" + digits
    elif s.startswith("00"):
        candidate = "+" + digits[2:]
    elif len(digits) == 10 and digits[0] in "6789":
        candidate = "+91" + digits
    elif len(digits) == 11 and digits.startswith("0") and digits[1] in "6789":
        candidate = "+91" + digits[1:]
    elif len(digits) == 12 and digits.startswith("91") and digits[2] in "6789":
        candidate = "+" + digits
    else:
        raise ValueError("Enter a valid phone number, e.g. +919876543210")
    if not re.fullmatch(r"\+[1-9]\d{9,14}", candidate):
        raise ValueError("Enter a valid phone number, e.g. +919876543210")
    return candidate


def clean_skills(skills: list) -> list:
    """Strip, drop empties, de-duplicate case-insensitively, keep order."""
    seen = set()
    result = []
    for item in skills:
        name = re.sub(r"\s+", " ", str(item)).strip()
        if not name:
            continue
        if len(name) > 50:
            raise ValueError("Each skill must be 50 characters or fewer")
        key = name.lower()
        if key not in seen:
            seen.add(key)
            result.append(name)
    return result
