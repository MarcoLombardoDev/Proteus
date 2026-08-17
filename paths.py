#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Proteus - filesystem quirks, mostly Windows and network shares.

This module exists because the environment Proteus is actually pointed at — a
corporate file server reached over SMB, with a folder tree nobody has pruned
since 2009 — breaks assumptions that hold perfectly on a developer's laptop.

Two of them matter enough to be handled here rather than discovered in
production:

* **Paths longer than 260 characters.** Windows API calls fail on them unless
  the path carries the `\\\\?\\` extended-length prefix. `MAX_PATH` is easy to
  exceed on a share: a few nested department folders, a document title used as a
  file name, and `.20260817-101500.bak` appended by a second campaign.
* **Files somebody has open.** On Windows a file open in Word cannot be
  replaced, and the error says `PermissionError` — which sounds like a rights
  problem and sends the user to the wrong place. The distinction is worth making
  in the message.

It sits below `office.py` in the import order and depends only on `i18n`, so
every other module can use it without a cycle.
"""

from __future__ import annotations

import os

from i18n import t

#: The prefix that lifts the Windows MAX_PATH limit.
EXTENDED_PREFIX = "\\\\?\\"

#: Same, for UNC paths: `\\\\server\\share` becomes `\\\\?\\UNC\\server\\share`.
EXTENDED_UNC_PREFIX = "\\\\?\\UNC\\"

#: Length at which a Windows path needs the prefix. The limit is 260 including
#: the terminating NUL, and a directory needs room for `8.3` names beneath it,
#: so the prefix is applied well before the true ceiling.
MAX_PATH = 260


def long_path(path: str) -> str:
    """
    A form of `path` that Windows will accept however long it is.

    A no-op everywhere except Windows, and on Windows only for absolute paths:
    the extended-length syntax disables all normalisation, so a relative path or
    one containing `..` would stop resolving the way the caller expects.

    Returns the path unchanged when it already carries the prefix, so applying
    this twice is harmless.
    """
    if os.name != "nt" or not path:
        return path
    if path.startswith(EXTENDED_PREFIX):
        return path

    absolute = os.path.abspath(path)
    if absolute.startswith("\\\\"):
        # UNC: \\server\share\... -> \\?\UNC\server\share\...
        return EXTENDED_UNC_PREFIX + absolute[2:]
    return EXTENDED_PREFIX + absolute


def is_long(path: str) -> bool:
    """True when the path is long enough to need the extended-length form."""
    return len(path) >= MAX_PATH


def describe_os_error(exc: OSError, path: str) -> tuple[str, str]:
    """
    Turn a filesystem error into a reason and a remedy, in the user's language.

    The default string representation of these errors is written for
    programmers. "Permission denied" on a file server usually means one of three
    quite different things, and telling them apart is the difference between a
    user fixing it in ten seconds and filing a ticket.
    """
    import errno

    code = getattr(exc, "errno", None)
    winerror = getattr(exc, "winerror", None)

    # Windows: 32 = sharing violation, 33 = lock violation. Both mean somebody
    # has the file open, which is not a permissions problem at all.
    if winerror in (32, 33):
        return (t("«{name}» is open in another program, so it cannot be "
                  "replaced.").format(name=os.path.basename(path)),
                t("Close the file and run the replacement again."))

    if code == errno.EACCES:
        # On Windows EACCES also covers a read-only file, which is why the
        # remedy names both possibilities rather than guessing.
        return (t("Access denied to «{name}».").format(name=os.path.basename(path)),
                t("Check the file is not read-only and that you have write "
                  "permission on the folder. On Windows it may also be open in "
                  "another program."))

    # Checked before plain ENOENT, and deliberately so: Windows reports a
    # too-long path as "the system cannot find the file", so the generic
    # not-found message would fire first and send the user looking for a file
    # that is right there. Length is the more specific explanation, so it wins.
    if code in (errno.ENAMETOOLONG, errno.ENOENT) and is_long(path):
        return (t("The path is too long for this filesystem ({length} "
                  "characters).").format(length=len(path)),
                t("Shorten the folder names, or map the share to a drive letter "
                  "closer to the file."))

    if code == errno.ENOENT:
        return (t("«{name}» no longer exists.").format(name=os.path.basename(path)),
                t("It may have been moved or deleted since the scan."))

    if code == errno.ENOSPC:
        return (t("No space left on the destination."),
                t("Free some space and run the replacement again."))

    # No t() here: the string is only placeholders, so a catalogue entry would
    # be identical in every language — and the guard that looks for exactly
    # that would flag it.
    return (f"{os.path.basename(path)}: {exc}",
            t("Check the file and the folder, then run the scan again."))


def describe_unreadable_folder(exc: OSError, path: str) -> tuple[str, str]:
    """
    Reason and remedy for a folder the scan could not enter.

    Reported rather than logged in passing, because a folder nobody could open
    may be full of logos: "we scanned everything" is false while one branch of
    the tree was refused, and the user is the only one who can say whether it
    matters.
    """
    reason, _hint = describe_os_error(exc, path)
    return (t("Could not list «{path}», so anything inside it was not "
              "examined: {reason}").format(path=path, reason=reason),
            t("Check your permissions on that folder, then scan it separately."))
