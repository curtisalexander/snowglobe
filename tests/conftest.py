import os
import subprocess
import sys
from pathlib import Path

import pytest

if sys.platform == "win32":

    @pytest.fixture(autouse=True)
    def translate_test_chmod_to_windows_acl(monkeypatch: pytest.MonkeyPatch) -> None:
        """Give POSIX-oriented credential fixtures equivalent native Windows ACLs."""

        original_chmod = Path.chmod
        account = f"{os.environ['USERDOMAIN']}\\{os.environ['USERNAME']}"

        def windows_chmod(path: Path, mode: int, *, follow_symlinks: bool = True) -> None:
            original_chmod(path, mode, follow_symlinks=follow_symlinks)
            if mode in {0o400, 0o600}:
                rights = "(R)" if mode == 0o400 else "(R,W)"
                command = [
                    "icacls",
                    str(path),
                    "/inheritance:r",
                    "/grant:r",
                    f"{account}:{rights}",
                ]
            else:
                command = ["icacls", str(path), "/grant", "*S-1-1-0:(R)"]
            subprocess.run(command, check=True, capture_output=True)

        monkeypatch.setattr(Path, "chmod", windows_chmod)
