"""Bounded, transfer-scoped native resource ledger (E08/A03)."""

from __future__ import annotations

from dataclasses import dataclass, field

from cephvr.shared.identity import require_uuid4


class LedgerError(RuntimeError):
    """A resource transfer or release does not match its registered obligation."""


@dataclass(frozen=True, slots=True)
class ResourceKey:
    resource_id: str
    owner_process_instance_id: str

    def __post_init__(self) -> None:
        if not self.resource_id or not self.owner_process_instance_id:
            raise ValueError(
                "native resource key requires resource and owner instance IDs"
            )


@dataclass(frozen=True, slots=True)
class TransferSnapshot:
    peer_instance_id: str
    transfer_id: str
    attached: bool
    released: bool


@dataclass(frozen=True, slots=True)
class ResourceSnapshot:
    key: ResourceKey
    kind: str
    owner_released: bool
    retired: bool
    transfers: tuple[TransferSnapshot, ...]


@dataclass(slots=True)
class _Transfer:
    peer_instance_id: str
    attached: bool = False
    released: bool = False


@dataclass(slots=True)
class _Resource:
    kind: str
    owner_released: bool = False
    retired: bool = False
    transfers: dict[str, _Transfer] = field(default_factory=dict)


class NativeResourceLedger:
    """Implements the shared ResourceLedger contract and exact ring transfer evidence."""

    def __init__(self, *, max_resources: int, max_transfers_per_resource: int) -> None:
        if max_resources <= 0 or max_transfers_per_resource <= 0:
            raise ValueError("ledger bounds must be positive")
        self.max_resources = max_resources
        self.max_transfers_per_resource = max_transfers_per_resource
        self._resources: dict[ResourceKey, _Resource] = {}

    def register(self, key: ResourceKey, *, kind: str) -> None:
        if not kind:
            raise ValueError("native resource kind is required")
        if key in self._resources:
            raise LedgerError("resource key is already registered")
        if len(self._resources) >= self.max_resources:
            raise LedgerError("native resource ledger capacity exhausted")
        self._resources[key] = _Resource(kind)

    def expect_attachment(
        self, key: ResourceKey, *, peer_instance_id: str, transfer_id: str
    ) -> None:
        resource = self._require(key)
        if resource.owner_released or resource.retired:
            raise LedgerError("released or retired resource cannot accept a transfer")
        if not peer_instance_id or not transfer_id:
            raise ValueError("transfer requires exact peer-instance and transfer IDs")
        try:
            require_uuid4(transfer_id)
        except ValueError as exc:
            raise ValueError("transfer ID must be a UUIDv4") from exc
        previous = resource.transfers.get(transfer_id)
        if previous is not None:
            if previous.peer_instance_id != peer_instance_id:
                raise LedgerError("transfer ID was reused for another peer")
            if previous.released:
                raise LedgerError("released transfer ID cannot be reused")
            return
        if len(resource.transfers) >= self.max_transfers_per_resource:
            raise LedgerError("resource attachment transfer capacity exhausted")
        if any(
            transfer.peer_instance_id == peer_instance_id and not transfer.released
            for transfer in resource.transfers.values()
        ):
            raise LedgerError("peer already has an active resource transfer")
        resource.transfers[transfer_id] = _Transfer(peer_instance_id)

    def confirm_attachment(
        self, key: ResourceKey, *, peer_instance_id: str, transfer_id: str
    ) -> None:
        transfer = self._transfer(key, transfer_id, peer_instance_id=peer_instance_id)
        if transfer.released:
            raise LedgerError("released attachment cannot become active again")
        transfer.attached = True

    def confirm_release(
        self,
        key: ResourceKey,
        *,
        peer_instance_id: str,
        transfer_id: str,
    ) -> None:
        transfer = self._transfer(key, transfer_id, peer_instance_id=peer_instance_id)
        transfer.released = True

    def prune_released_transfer(self, key: ResourceKey, *, transfer_id: str) -> None:
        """Drop one released transfer after the lifecycle owner retained its receipt."""
        resource = self._require(key)
        transfer = resource.transfers.get(transfer_id)
        if transfer is None or not transfer.released:
            raise LedgerError("only an exactly released transfer can be pruned")
        del resource.transfers[transfer_id]

    def remove_completed_resource(self, key: ResourceKey) -> None:
        """Forget an allocation only after owner and every holder release are proven."""
        resource = self._require(key)
        if not resource.owner_released or any(
            not transfer.released for transfer in resource.transfers.values()
        ):
            raise LedgerError("resource still has an unresolved owner or holder")
        del self._resources[key]

    def confirm_owner_release(self, key: ResourceKey) -> None:
        resource = self._require(key)
        if not self.may_close_owner(key):
            raise LedgerError("owner cannot close while a transfer remains unresolved")
        resource.owner_released = True

    def retire(self, key: ResourceKey, *, reason: str) -> None:
        """Retirement marks failure; it never substitutes for holder release evidence."""
        if not reason:
            raise ValueError("resource retirement needs a failure reason")
        self._require(key).retired = True

    def may_close_owner(self, key: ResourceKey) -> bool:
        resource = self._require(key)
        return all(transfer.released for transfer in resource.transfers.values())

    def unresolved(self) -> tuple[ResourceKey, ...]:
        return tuple(
            key
            for key, resource in self._resources.items()
            if not resource.owner_released
            or any(not transfer.released for transfer in resource.transfers.values())
        )

    def snapshot(self, key: ResourceKey) -> ResourceSnapshot:
        resource = self._require(key)
        return ResourceSnapshot(
            key,
            resource.kind,
            resource.owner_released,
            resource.retired,
            tuple(
                TransferSnapshot(
                    transfer.peer_instance_id,
                    transfer_id,
                    transfer.attached,
                    transfer.released,
                )
                for transfer_id, transfer in resource.transfers.items()
            ),
        )

    def _transfer(
        self, key: ResourceKey, transfer_id: str, *, peer_instance_id: str
    ) -> _Transfer:
        resource = self._require(key)
        try:
            transfer = resource.transfers[transfer_id]
        except KeyError as exc:
            raise LedgerError("resource transfer is not registered") from exc
        if transfer.peer_instance_id != peer_instance_id:
            raise LedgerError("resource transfer peer differs from registered process")
        return transfer

    def _require(self, key: ResourceKey) -> _Resource:
        try:
            return self._resources[key]
        except KeyError as exc:
            raise LedgerError("native resource key is not registered") from exc
