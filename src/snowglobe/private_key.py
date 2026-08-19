"""Snowflake RSA private-key loading with detail-free failures."""

from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from snowglobe.secure_file import SecureFileError, read_secure_file


class PrivateKeyError(Exception):
    """A deliberately detail-free private-key failure."""


def load_private_key(path: Path) -> bytes:
    """Return an RSA private key as unencrypted PKCS#8 DER bytes."""

    try:
        key_bytes = read_secure_file(path)
        try:
            key = serialization.load_pem_private_key(key_bytes, password=None)
        except ValueError:
            key = serialization.load_der_private_key(key_bytes, password=None)
        if not isinstance(key, RSAPrivateKey):
            raise PrivateKeyError
        return key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    except (OSError, SecureFileError, TypeError, ValueError, PrivateKeyError) as error:
        raise PrivateKeyError from error
