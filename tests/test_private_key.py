from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa

from snowglobe.private_key import PrivateKeyError, load_private_key


@pytest.mark.parametrize("encoding", [serialization.Encoding.PEM, serialization.Encoding.DER])
def test_loads_rsa_key_as_pkcs8_der(tmp_path: Path, encoding: serialization.Encoding) -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    source = key.private_bytes(
        encoding=encoding,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    path = tmp_path / "key-material"
    path.write_bytes(source)

    loaded = serialization.load_der_private_key(load_private_key(path), password=None)

    assert isinstance(loaded, rsa.RSAPrivateKey)
    assert loaded.public_key().public_numbers() == key.public_key().public_numbers()


@pytest.mark.parametrize("case", ["missing", "malformed", "encrypted", "non-rsa"])
def test_rejects_key_failures_without_detail(tmp_path: Path, case: str) -> None:
    path = tmp_path / "sensitive-key-name"
    if case == "malformed":
        path.write_bytes(b"not a key")
    elif case == "encrypted":
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.BestAvailableEncryption(b"secret"),
            )
        )
    elif case == "non-rsa":
        key = ed25519.Ed25519PrivateKey.generate()
        path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )

    with pytest.raises(PrivateKeyError) as caught:
        load_private_key(path)

    assert str(caught.value) == ""
