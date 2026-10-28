"""Exception hierarchy. The command layer turns every one of these into a failed Result."""

from __future__ import annotations


class HopperError(Exception):
    """Base class for everything Hopper raises on purpose."""


class ConfigError(HopperError):
    """hopper.toml, environment, or arguments are inconsistent."""


class GatewayError(HopperError):
    """The gateway could not complete a call (network, server error, bad payload)."""


class AuthRequired(GatewayError):
    """No usable session: run ``asi-hopper auth login``."""


class NotRecorded(GatewayError):
    """The replay gateway has no fixture for this call."""


class NotFound(HopperError):
    """A verb, issue, project, or issue type does not exist."""


class PolicyViolation(HopperError):
    """A write was refused by policy (there are no write verbs; kept for the wire format)."""


class ValidationError(HopperError):
    def __init__(self, *errors: str) -> None:
        super().__init__("; ".join(errors))
        self.errors = list(errors)
