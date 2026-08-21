"""Snowflake RSA private-key loading."""

from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey


class PrivateKeyError(Exception):
    """A local private-key loading failure."""


def load_private_key(path: Path) -> bytes:
    """Return an RSA private key as unencrypted PKCS#8 DER bytes."""

    try:
        key_bytes = path.read_bytes()
    except OSError as error:
        raise PrivateKeyError(f"could not read private key {path}: {error}") from error

    try:
        try:
            key = serialization.load_pem_private_key(key_bytes, password=None)
        except ValueError:
            key = serialization.load_der_private_key(key_bytes, password=None)
    except (TypeError, ValueError) as error:
        raise PrivateKeyError(f"could not parse private key {path}: {error}") from error
    if not isinstance(key, RSAPrivateKey):
        raise PrivateKeyError(f"private key {path} must be RSA")
    return key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
