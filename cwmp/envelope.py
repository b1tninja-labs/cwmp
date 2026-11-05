"""SOAP 1.2 envelope codec with XML hardening (TR-069 Annex 2).

Every object in this module is a placeholder until the milestone named in ROADMAP.md lands. A
stub raises instead of returning a plausible empty value: a protocol library that silently
answers nothing is worse than one that refuses to answer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

    Rpc = Any  # placeholder: give it a real type in the milestone that needs it
    SessionContext = Any  # placeholder: give it a real type in the milestone that needs it

__all__ = [
    "decode_envelope",
    "encode_envelope",
]


def encode_envelope(rpc: Rpc, session: SessionContext) -> bytes:
    """Pending behaviour defined by TR-069 Annex 2.

    Not implemented yet. See the ``envelope.encode_envelope()`` row in ROADMAP.md; this
    stub raises on purpose so nothing downstream mistakes it for working code.
    """
    raise NotImplementedError("encode_envelope() is not implemented: TR-069 Annex 2")


def decode_envelope(raw: bytes) -> Rpc:
    """Pending behaviour defined by TR-069 Annex 2.

    Not implemented yet. See the ``envelope.decode_envelope()`` row in ROADMAP.md; this
    stub raises on purpose so nothing downstream mistakes it for working code.
    """
    raise NotImplementedError("decode_envelope() is not implemented: TR-069 Annex 2")
