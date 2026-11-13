"""Fetch the Broadband Forum data-model XML this project is tested against, into a cache outside the repository.

    python tools/fetch_bbf.py            fetch what is missing, verify every file, report
    python tools/fetch_bbf.py --verify   verify only, never touch the network

The cache is ``$CWMP_DATA_CACHE`` when set, otherwise ``%LOCALAPPDATA%\\cwmp-data`` on Windows and
``$XDG_CACHE_HOME/cwmp-data`` (default ``~/.cache/cwmp-data``) elsewhere. Nothing is written into the repository
and nothing is vendored: the files are the Forum's, fetched by whoever runs the tool.

Each file is pinned by sha256 and size. A file that does not match is never installed: the download is
discarded and the tool exits non-zero, so a changed upstream file is a decision and not a surprise. Requests
run one per second, smallest file first, with a plain User-Agent that carries no personal detail.

Why this does not use the primarysource ``bbf`` collection: that collection pins the repository at one commit
and does not catalogue ``tr-106-types.xml``, and its XML reader refuses every document type declaration, which
is exactly what ``tr-106-types.xml`` carries (``devicespy.xmlsafe`` has that one file on its pin list). The
Device:2.22 files fetched here have the same sha256 and size as primarysource's catalogue lists for
``tr-181-2-22-0-cwmp-full`` and its ``tr-181-2-22-0-cwmp``.

Terms read on 2026-11-13: the header of each file is a Broadband Forum copyright notice and a BSD-3-Clause-style
licence (redistribution and use, with or without modification, with the notice retained; a licence under
copyright only, patents are the Forum IPR policy's). The data-model site itself states no other terms. Even so,
nothing is vendored here.
"""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

SITE = "https://cwmp-data-models.broadband-forum.org/"
SITE_READ = "site and file headers read 2026-11-13"
USER_AGENT = "portfolio-fetch/1"
INTERVAL = 1.0  # seconds between requests


@dataclass(frozen=True, slots=True)
class Pin:
    name: str
    size: int
    sha256: str
    read: str


#: Smallest first. Device:2.22 is the current Device:2 release on the site's index on 2026-11-13.
PINS = (
    Pin(
        "tr-106-types.xml",
        21157,
        "68237466c70b9f48ea647878af65d54c16a42e45d2ef2ba5f6e4a1042e0484a1",
        f"{SITE}tr-106-types.xml; {SITE_READ}; BSD-3-Clause-style header; internal DTD of 6 entities",
    ),
    Pin(
        "tr-181-2-22-0-cwmp-full.xml",
        5425272,
        "d331ed729226d86b6ee426531eda823289f363fa1a6e4b445531fad79dc581d7",
        f"{SITE}tr-181-2-22-0-cwmp-full.xml; {SITE_READ}; BSD-3-Clause-style header; no DTD, self-contained",
    ),
)


def cache_dir() -> Path:
    """The cache directory: ``$CWMP_DATA_CACHE``, else the user cache directory."""
    override = os.environ.get("CWMP_DATA_CACHE")
    if override:
        return Path(override)
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "cwmp-data"
    return Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "cwmp-data"


def check(path: Path, pin: Pin) -> str | None:
    """None when ``path`` is the pinned file, else why it is not."""
    if not path.is_file():
        return "missing"
    raw = path.read_bytes()
    if len(raw) != pin.size:
        return f"size {len(raw)}, pinned {pin.size}"
    if hashlib.sha256(raw).hexdigest() != pin.sha256:
        return "sha256 differs from the pin"
    return None


def _download(pin: Pin, destination: Path) -> None:
    request = urllib.request.Request(SITE + pin.name, headers={"User-Agent": USER_AGENT})  # noqa: S310
    with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
        raw = response.read(pin.size + 1)
    if len(raw) != pin.size or hashlib.sha256(raw).hexdigest() != pin.sha256:
        raise SystemExit(
            f"{pin.name}: the download does not match the pin ({len(raw)} bytes); not installed"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=destination.parent, delete=False, suffix=".part"
    ) as handle:
        handle.write(raw)
    Path(handle.name).replace(destination)


def main(argv: list[str]) -> int:
    verify_only = "--verify" in argv
    root = cache_dir()
    failures = 0
    requested = False
    for pin in sorted(PINS, key=lambda p: p.size):
        path = root / pin.name
        problem = check(path, pin)
        if problem is not None and not verify_only:
            if requested:
                time.sleep(INTERVAL)
            requested = True
            _download(pin, path)
            problem = check(path, pin)
        status = "ok" if problem is None else problem
        failures += problem is not None
        print(f"{pin.name}  {pin.size}  {pin.sha256}  {status}  ({root})")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
