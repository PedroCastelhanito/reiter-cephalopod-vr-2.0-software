"""Protected metadata checks for E08 loopback gRPC admissions."""

from __future__ import annotations

import hmac
import ipaddress
from collections.abc import Iterable
from dataclasses import dataclass, field

from cephvr.shared.identity import require_uuid4

Metadata = Iterable[tuple[str, str]]


class AuthenticationError(ValueError):
    """The connection does not prove the registered peer identity."""


@dataclass(frozen=True)
class Principal:
    """Registered role and generation (client_id for GUI/headless clients)."""

    role: str
    generation: str
    token: str = field(repr=False)

    def metadata(self) -> tuple[tuple[str, str], ...]:
        require_uuid4(self.generation)
        if not self.role or not self.token:
            raise AuthenticationError("principal credentials are incomplete")
        return (
            ("x-cephvr-role", self.role),
            ("x-cephvr-generation", self.generation),
            ("x-cephvr-token", self.token),
        )


def require_loopback_peer(peer: str) -> None:
    """Accept only a gRPC IPv4/IPv6 loopback peer string."""
    if peer.startswith("ipv4:"):
        host, separator, port = peer[5:].rpartition(":")
    elif peer.startswith("ipv6:") and peer[5:].startswith("["):
        host, separator, port = peer[6:].partition("]:")
    else:
        raise AuthenticationError("control peer is not TCP loopback")
    if not separator or not port.isdecimal() or not 0 < int(port) <= 65535:
        raise AuthenticationError("invalid control peer endpoint")
    try:
        if not ipaddress.ip_address(host).is_loopback:
            raise AuthenticationError("control peer is not loopback")
    except ValueError as exc:
        raise AuthenticationError("invalid control peer address") from exc


def require_authenticated_peer(
    peer: str,
    metadata: Metadata,
    *,
    expected_role: str,
    expected_token: str,
    expected_generation: str,
) -> Principal:
    """Bind protected token, role and generation to trusted registration values.

    The caller selects all expected values from its own registry. Request payloads
    must never supply the expected token or become authority by themselves.
    """
    require_loopback_peer(peer)
    try:
        require_uuid4(expected_generation)
    except ValueError as exc:
        raise AuthenticationError("registered peer generation is invalid") from exc
    if not expected_role or not expected_token:
        raise AuthenticationError("registered peer credentials are incomplete")
    selected: dict[str, str] = {}
    required = {"x-cephvr-role", "x-cephvr-generation", "x-cephvr-token"}
    for key, value in metadata:
        if key in required:
            if key in selected or not isinstance(value, str):
                raise AuthenticationError("duplicate or malformed credential metadata")
            selected[key] = value
    if set(selected) != required:
        raise AuthenticationError("missing credential metadata")
    try:
        require_uuid4(selected["x-cephvr-generation"])
    except ValueError as exc:
        raise AuthenticationError("invalid credential generation") from exc
    if selected["x-cephvr-role"] != expected_role:
        raise AuthenticationError("credential role mismatch")
    if selected["x-cephvr-generation"] != expected_generation:
        raise AuthenticationError("credential generation mismatch")
    if not hmac.compare_digest(selected["x-cephvr-token"], expected_token):
        raise AuthenticationError("credential token mismatch")
    return Principal(expected_role, expected_generation, expected_token)
