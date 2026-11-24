import hashlib
import hmac
import secrets


def generate_salt() -> str:
    return secrets.token_hex(16)


def normalize_last4(value: str) -> str:
    if len(value) != 4 or not value.isdigit():
        raise ValueError("last-four value must contain exactly four digits")
    return value


def hash_last4(value: str, salt: str, secret: str) -> str:
    normalized = normalize_last4(value)
    key = secret.encode("utf-8")
    payload = f"{salt}:{normalized}".encode()
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def verify_last4(value: str, salt: str, digest: str, secret: str) -> bool:
    try:
        candidate = hash_last4(value, salt, secret)
    except ValueError:
        return False
    return hmac.compare_digest(candidate, digest)
