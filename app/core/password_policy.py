"""Standalone, reusable password validation policy.

Why this module exists:
Keeping password rules in an isolated pure-Python module makes it trivial to unit-test every
edge case without spinning up FastAPI or a database, and allows reuse across registration,
password reset, or CLI admin scripts.
"""

import re

COMMON_PASSWORDS: frozenset[str] = frozenset(
    {
        "password1!",
        "password123!",
        "admin123!",
        "welcome1!",
        "qwerty123!",
        "letmein1!",
        "iloveyou1!",
        "12345678aA!",
        "passw0rd!",
        "football1!",
    }
)

SPECIAL_CHARS_PATTERN = re.compile(r"[!@#$%^&*(),.?:{}|<>_+=/~-]")


def validate_password_strength(password: str) -> str:
    """Validate that a password meets complexity rules and is not commonly breached.

    Rules:
    - Minimum 8 characters
    - At least one uppercase letter (A-Z)
    - At least one lowercase letter (a-z)
    - At least one digit (0-9)
    - At least one special character
    - Not in the common passwords blocklist (case-insensitive check)

    Raises ValueError with a descriptive message if any check fails.
    """
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    if not any(ch.isupper() for ch in password):
        raise ValueError("Password must contain at least one uppercase letter.")
    if not any(ch.islower() for ch in password):
        raise ValueError("Password must contain at least one lowercase letter.")
    if not any(ch.isdigit() for ch in password):
        raise ValueError("Password must contain at least one digit.")
    if not SPECIAL_CHARS_PATTERN.search(password):
        raise ValueError("Password must contain at least one special character.")
    if password.lower() in {p.lower() for p in COMMON_PASSWORDS}:
        raise ValueError("Password is too common and easily guessed.")
    return password
