"""cwmp -- TR-069 CWMP for ACS and CPE.

CWMP is how almost every customer premises device on earth is configured, and Python cannot
speak it.
"""

from __future__ import annotations

from . import (
    apps,
    auth,
    cli,
    clock,
    datamodel,
    endpoint,
    envelope,
    faults,
    instances,
    methods,
    session,
    transfer,
)
from .auth import digest_challenge
from .datamodel import coerce_value, resolve_path
from .endpoint import run_inform
from .envelope import decode_envelope, encode_envelope
from .methods import build_inform, set_parameter_values
from .session import handle_session
from .transfer import build_download

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "apps",
    "auth",
    "build_download",
    "build_inform",
    "cli",
    "clock",
    "coerce_value",
    "datamodel",
    "decode_envelope",
    "digest_challenge",
    "encode_envelope",
    "endpoint",
    "envelope",
    "faults",
    "handle_session",
    "instances",
    "methods",
    "resolve_path",
    "run_inform",
    "session",
    "set_parameter_values",
    "transfer",
]
