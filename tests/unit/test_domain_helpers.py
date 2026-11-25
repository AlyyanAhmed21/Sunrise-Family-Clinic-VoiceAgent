import pytest

from clinic.security.hashing import generate_salt, hash_last4, normalize_last4, verify_last4
from clinic.security.parsing import names_match


def test_last_four_hash_helpers() -> None:
    salt = generate_salt()
    digest = hash_last4("3344", salt, "test-pepper")
    assert normalize_last4("3344") == "3344"
    assert verify_last4("3344", salt, digest, "test-pepper")
    assert not verify_last4("9999", salt, digest, "test-pepper")
    assert not verify_last4("abc", salt, digest, "test-pepper")
    with pytest.raises(ValueError):
        normalize_last4("12")


def test_name_matching_tolerates_one_edit_per_token() -> None:
    assert names_match("Sarah Johnsn", "Sarah Johnson")
    assert names_match("Michel Brown", "Michael Brown")
    assert not names_match("Sarah Longname Johnson", "Sarah Johnson")
