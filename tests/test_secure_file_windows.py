import os
import subprocess
import sys
from pathlib import Path

import pytest

from snowglobe.secure_file import SecureFileError, read_secure_file

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows ACL test")


def _restrict_to_current_user(path: Path) -> None:
    account = f"{os.environ['USERDOMAIN']}\\{os.environ['USERNAME']}"
    subprocess.run(
        ["icacls", str(path), "/inheritance:r", "/grant:r", f"{account}:(R,W)"],
        check=True,
        capture_output=True,
    )


def test_reads_current_user_only_file(tmp_path: Path) -> None:
    path = tmp_path / "private.txt"
    path.write_bytes(b"private")
    _restrict_to_current_user(path)

    assert read_secure_file(path) == b"private"


def test_rejects_file_readable_by_everyone(tmp_path: Path) -> None:
    path = tmp_path / "shared.txt"
    path.write_bytes(b"private")
    _restrict_to_current_user(path)
    subprocess.run(
        ["icacls", str(path), "/grant", "*S-1-1-0:(R)"],
        check=True,
        capture_output=True,
    )

    with pytest.raises(SecureFileError):
        read_secure_file(path)


def test_rejects_symlink(tmp_path: Path) -> None:
    target = tmp_path / "private.txt"
    target.write_bytes(b"private")
    _restrict_to_current_user(target)
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip()

    with pytest.raises(SecureFileError):
        read_secure_file(link)
