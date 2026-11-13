"""Typed errors for the CWMP codec."""

from __future__ import annotations

__all__ = ["EnvelopeError", "XmlRefused"]


class EnvelopeError(ValueError):
    """The bytes are not a valid CWMP SOAP 1.1 envelope (TR-069 Amendment 6 Corrigendum 1, 3.5)."""


class XmlRefused(EnvelopeError):  # noqa: N818 - the name matches devicespy.xmlsafe.XmlRefused
    """The hardened XML reader refused the document; ``reason`` says why in one short phrase."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
