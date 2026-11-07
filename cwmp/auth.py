"""HTTP Digest challenge and response (RFC 7616, TR-069).

Every object in this module is a placeholder until the milestone named in ROADMAP.md lands. A
stub raises instead of returning a plausible empty value: a protocol library that silently
answers nothing is worse than one that refuses to answer.
"""

from __future__ import annotations

__all__ = [
    "digest_challenge",
]


def digest_challenge(nonce: bytes, realm: str) -> str:
    """Pending behaviour defined by RFC 7616 sec. 3.3.

    Not implemented yet. See the ``auth.digest_challenge()`` row in ROADMAP.md; this stub
    raises on purpose so nothing downstream mistakes it for working code.
    """
    raise NotImplementedError("digest_challenge() is not implemented: RFC 7616 sec. 3.3")
