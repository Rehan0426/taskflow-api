"""Unit tests for the standalone password policy module."""

import pytest

from app.core.password_policy import validate_password_strength


def test_valid_password_passes() -> None:
    assert validate_password_strength("ValidPass9#") == "ValidPass9#"


@pytest.mark.parametrize(
    "bad_password,expected_substring",
    [
        ("Short1!", "at least 8 characters"),
        ("alllowercase1!", "uppercase"),
        ("ALLUPPERCASE1!", "lowercase"),
        ("NoDigitsHere!", "digit"),
        ("NoSpecialChar1", "special character"),
        ("Password123!", "too common"),
        ("Qwerty123!", "too common"),
    ],
)
def test_invalid_passwords_rejected(bad_password: str, expected_substring: str) -> None:
    with pytest.raises(ValueError) as exc_info:
        validate_password_strength(bad_password)
    assert expected_substring in str(exc_info.value)
