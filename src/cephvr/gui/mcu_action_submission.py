"""Submit only the selected MCU diagnostic settings before starting its test."""

from typing import Any

from cephvr.client.session import ClientError, HeadlessClient
from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.managed_device_commands import _update_configuration
from cephvr.gui.pin_numbers import firmware_pin


async def prepare_mcu_test(client: HeadlessClient, options: dict[str, Any]) -> None:
    proposed = _proposal(client, options)
    acquisition = next(
        (
            item.acquisition
            for item in proposed.backends
            if item.backend_name == "acquisition"
        ),
        None,
    )
    if acquisition is None:
        raise ClientError("Acquisition settings are unavailable.")
    pulses = acquisition.pulses
    pulses.port = options["port"]
    signal = options["signal"]
    pin = firmware_pin(options["pin"])
    if signal == pb.MICROCONTROLLER_SIGNAL_KIND_TRIAL_STATE:
        pulses.trial_state_pin = pin
        pulses.trial_state_enabled = True
    elif signal == pb.MICROCONTROLLER_SIGNAL_KIND_PROJECTOR_FLIP:
        pulses.projector_flip_pin = pin
        pulses.projector_flip_enabled = True
    else:
        role = {
            pb.MICROCONTROLLER_SIGNAL_KIND_BEHAVIORAL: "behavioral",
            pb.MICROCONTROLLER_SIGNAL_KIND_TRACKING: "tracking",
            pb.MICROCONTROLLER_SIGNAL_KIND_EYE_TRACKING: "eye_tracking",
        }.get(signal)
        if role is None:
            raise ClientError("Unsupported MCU diagnostic signal.")
        pulse = getattr(pulses, role)
        pulse.pin = pin
        pulse.requested_frequency_hz = float(options["frequency"])
    await _submit(client, options, proposed)


async def prepare_mcu_connection(
    client: HeadlessClient, options: dict[str, Any]
) -> None:
    proposed = _proposal(client, options)
    acquisition = next(
        (
            item.acquisition
            for item in proposed.backends
            if item.backend_name == "acquisition"
        ),
        None,
    )
    if acquisition is None:
        raise ClientError("Acquisition settings are unavailable.")
    acquisition.pulses.port = options["port"]
    await _submit(client, options, proposed)


def _proposal(
    client: HeadlessClient, options: dict[str, Any]
) -> pb.ExperimentConfiguration:
    state = client.snapshot
    if (
        state.controller_generation != options["generation"]
        or state.configuration.revision != options["base_revision"]
        or state.configuration_values.revision != state.configuration.revision
        or state.configuration_values.current.SerializeToString(deterministic=True)
        != options["base_configuration"]
    ):
        raise ClientError("MCU configuration changed; refresh before retrying Test.")
    if state.session.phase != pb.SESSION_PHASE_CONFIGURATION:
        raise ClientError("MCU pin tests require Configuration.")
    return pb.ExperimentConfiguration.FromString(options["base_configuration"])


async def _submit(
    client: HeadlessClient,
    options: dict[str, Any],
    proposed: pb.ExperimentConfiguration,
) -> None:
    state = client.snapshot
    await _update_configuration(client, state, proposed, "MCU diagnostic settings")
    confirmed = client.snapshot
    if (
        confirmed.controller_generation != options["generation"]
        or confirmed.configuration_values.revision != confirmed.configuration.revision
        or confirmed.configuration_values.current != proposed
    ):
        raise ClientError("MCU diagnostic settings were not confirmed; test not sent.")
