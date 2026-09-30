"""Bounded local operator credential authentication for controller RPCs."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import cast

from cephvr.shared.auth import AuthenticationError, require_authenticated_peer
from cephvr.shared.credentials import CredentialError, CredentialStore

ClientAuthentication = Callable[[str, str, str, object], Awaitable[None]]


def credential_store_authentication(
    store: CredentialStore, *, timeout_s: float = 2.0
) -> ClientAuthentication:
    """Resolve a bounded local credential outside the lifecycle state loop."""

    async def authenticate(
        client_id: str, controller_generation: str, peer: str, metadata: object
    ) -> None:
        if controller_generation != store.controller_generation:
            raise AuthenticationError("controller generation mismatch")
        try:
            principal = await asyncio.wait_for(
                asyncio.to_thread(store.lookup, client_id), timeout_s
            )
        except (TimeoutError, CredentialError, ValueError) as exc:
            raise AuthenticationError("operator credential unavailable") from exc
        if principal is None:
            raise AuthenticationError("operator credential missing")
        require_authenticated_peer(
            peer,
            cast(list[tuple[str, str]], metadata),
            expected_role=principal.role,
            expected_generation=principal.generation,
            expected_token=principal.token,
        )

    return authenticate
