# ADR 0015: Native Windows credential-file safety

- **Status:** Accepted
- **Date:** August 20, 2026
- **Extends:** ADR 0008

## Context

Snowglobe originally supported connected execution only on Linux and macOS because
its credential boundary required POSIX ownership, mode bits, and `O_NOFOLLOW`. The
application otherwise uses cross-platform Python, Node.js, loopback TCP, and browser
APIs. Requiring a separate POSIX host prevents an analyst whose primary workstation is
Windows from using the local product.

Removing the credential-file checks or treating Windows' synthetic POSIX mode values
as equivalent would weaken the reviewed boundary. Windows provides the needed native
primitives through file handles, security descriptors, access-control lists (ACLs),
and reparse-point flags.

## Decision

- Support native Windows 10 and 11 on NTFS in addition to current Linux and macOS.
- Open each credential file with `CreateFileW`, exclusive sharing, and
  `FILE_FLAG_OPEN_REPARSE_POINT`. Reject directories and all reparse points before
  reading from that same verified handle.
- Require the file owner SID to equal the current process-token user SID.
- Reject a null DACL and every allow ACE for a principal other than the current user,
  Local System, or the local Administrators group. System and administrators are the
  Windows privileged-host equivalents of POSIX root and are not an isolation boundary.
- Fail closed on object-specific or callback allow ACEs rather than attempting to
  interpret their variable layouts.
- Provide PowerShell setup and check scripts, document `icacls` commands that remove
  inherited access and grant the current account read/write access, and exercise the
  Windows boundary in a native Windows CI job.
- Keep the existing POSIX descriptor, owner-ID, mode-bit, and `O_NOFOLLOW` path
  unchanged.

## Consequences

- Native Windows can host the credential-bearing runtime without weakening checks to
  ordinary inherited users or groups.
- Credential files on FAT, exFAT, network shares without compatible Windows security
  descriptors, or paths implemented as reparse points are unsupported and fail
  closed. Use a local NTFS path.
- Administrators and Local System may still read or take control of files, just as
  root can on POSIX. Snowglobe does not claim to isolate secrets from privileged host
  administrators or other software running as the analyst.
- Windows setup uses PowerShell and `icacls`; POSIX setup continues to use Bash and
  `chmod`.
