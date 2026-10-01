"""Bounded FFV1 Configuration Record version reader.

FFV1 stores ``version`` as the first unsigned symbol in its range-coded
Configuration Record. This module decodes only that first symbol and never
allocates from file-declared dimensions or table counts.
"""

from __future__ import annotations


class FFV1ConfigurationError(ValueError):
    """The Configuration Record cannot be safely identified as FFV1 v3."""


_RANGE_INITIAL = 0xFF00
_RANGE_FACTOR = 214_748_364  # int(0.05 * 2**32), as used by FFmpeg.
_RANGE_MAX_PROBABILITY = 248
_MAX_VERSION_SYMBOL_BYTES = 16
_MAX_SYMBOL_EXPONENT = 16


def read_ffv1_version(extradata: bytes) -> int:
    """Return the version symbol from a Matroska FFV1 Configuration Record.

    The parser consumes at most 16 bytes, enough for the first bounded symbol,
    and rejects truncated/overread headers. Full record validation remains the
    FFmpeg decoder's responsibility when the stream is opened and decoded.
    """
    if len(extradata) < 2:
        raise FFV1ConfigurationError("FFV1 Configuration Record is truncated")
    decoder = _RangeDecoder(extradata[:_MAX_VERSION_SYMBOL_BYTES])
    states = bytearray([128] * 32)
    if decoder.get_bit(states, 0):
        return 0

    exponent = 0
    while decoder.get_bit(states, min(1 + exponent, 10)):
        exponent += 1
        if exponent > _MAX_SYMBOL_EXPONENT:
            raise FFV1ConfigurationError("FFV1 version symbol is unbounded")

    value = 1
    for bit_index in range(exponent - 1, -1, -1):
        value = value * 2 + decoder.get_bit(states, 22 + min(bit_index, 9))
    if decoder.overread:
        raise FFV1ConfigurationError("FFV1 version symbol is truncated")
    return value


def require_ffv1_version3(extradata: bytes) -> None:
    version = read_ffv1_version(extradata)
    if version != 3:
        raise FFV1ConfigurationError(
            f"profile requires version 3, received version {version}"
        )


class _RangeDecoder:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.position = 2
        self.low = int.from_bytes(data[:2], "big")
        self.range = _RANGE_INITIAL
        self.overread = False
        if self.low >= 0xFF00:
            self.low = 0xFF00
            self.position = len(data)
        self.zero_state, self.one_state = _probability_states()

    def get_bit(self, states: bytearray, state_index: int) -> int:
        state = states[state_index]
        range1 = (self.range * state) >> 8
        self.range -= range1
        if self.low < self.range:
            states[state_index] = self.zero_state[state]
            bit = 0
        else:
            self.low -= self.range
            states[state_index] = self.one_state[state]
            self.range = range1
            bit = 1
        if self.range < 0x100:
            self.range <<= 8
            self.low <<= 8
            if self.position < len(self.data):
                self.low += self.data[self.position]
                self.position += 1
            else:
                self.overread = True
        return bit


def _probability_states() -> tuple[bytes, bytes]:
    one = 1 << 32
    one_state = [0] * 256
    zero_state = [0] * 256
    last_probability = 0
    probability = one // 2
    for _ in range(128):
        probability8 = (256 * probability + one // 2) >> 32
        if probability8 <= last_probability:
            probability8 = last_probability + 1
        if (
            last_probability
            and last_probability < 256
            and probability8 <= _RANGE_MAX_PROBABILITY
        ):
            one_state[last_probability] = probability8
        probability += ((one - probability) * _RANGE_FACTOR + one // 2) >> 32
        last_probability = probability8

    for state in range(256 - _RANGE_MAX_PROBABILITY, _RANGE_MAX_PROBABILITY + 1):
        if one_state[state]:
            continue
        probability = (state * one + 128) >> 8
        probability += ((one - probability) * _RANGE_FACTOR + one // 2) >> 32
        probability8 = (256 * probability + one // 2) >> 32
        if probability8 <= state:
            probability8 = state + 1
        one_state[state] = min(probability8, _RANGE_MAX_PROBABILITY)
    for state in range(1, 255):
        zero_state[state] = (256 - one_state[256 - state]) & 0xFF
    return bytes(zero_state), bytes(one_state)
