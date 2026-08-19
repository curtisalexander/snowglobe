"""Fail-closed reads for analyst-owned local configuration and secrets."""

import os
import stat
from pathlib import Path


class SecureFileError(Exception):
    """A deliberately detail-free local-file policy failure."""


def read_secure_file(path: Path) -> bytes:
    """Read one owner-only regular file without following its final symlink."""

    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise SecureFileError

    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | no_follow)
        metadata = os.fstat(descriptor)
        permissions = stat.S_IMODE(metadata.st_mode)
        allowed_permissions = stat.S_IRUSR | stat.S_IWUSR
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or not permissions & stat.S_IRUSR
            or permissions & ~allowed_permissions
        ):
            raise SecureFileError

        with os.fdopen(descriptor, "rb") as file:
            descriptor = None
            return file.read()
    except (OSError, SecureFileError) as error:
        raise SecureFileError from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
