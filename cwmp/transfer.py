"""TransferFile, Download and Upload with resumable semantics (TR-069).

Every object in this module is a placeholder until the milestone named in ROADMAP.md lands. A
stub raises instead of returning a plausible empty value: a protocol library that silently
answers nothing is worse than one that refuses to answer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

    Rpc = Any  # placeholder: give it a real type in the milestone that needs it

__all__ = [
    "build_download",
]


def build_download(command_key: str, url: str, file_type: str) -> Rpc:
    """Pending behaviour defined by TR-069.

    Not implemented yet. See the ``transfer.build_download()`` row in ROADMAP.md; this
    stub raises on purpose so nothing downstream mistakes it for working code.
    """
    raise NotImplementedError("build_download() is not implemented: TR-069")
