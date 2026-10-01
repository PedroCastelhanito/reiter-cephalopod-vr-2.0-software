"""Acquisition binding of the shared protected backend bootstrap."""

from collections.abc import Mapping

from cephvr.shared.backend_bootstrap import BackendBootstrap, decode_backend_bootstrap

AcquisitionBootstrap = BackendBootstrap


def decode_acquisition_bootstrap(document: Mapping[str, object]) -> BackendBootstrap:
    return decode_backend_bootstrap(document, expected_role="acquisition")
