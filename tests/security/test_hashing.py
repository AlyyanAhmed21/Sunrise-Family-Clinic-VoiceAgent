from clinic.security.hashing import generate_salt, hash_last4, verify_last4


def test_salted_keyed_digest_round_trip() -> None:
    salt = generate_salt()
    digest = hash_last4("3344", salt, "test-pepper")
    assert verify_last4("3344", salt, digest, "test-pepper")
    assert not verify_last4("3345", salt, digest, "test-pepper")


def test_different_salts_produce_different_digests() -> None:
    first = hash_last4("3344", generate_salt(), "test-pepper")
    second = hash_last4("3344", generate_salt(), "test-pepper")
    assert first != second
