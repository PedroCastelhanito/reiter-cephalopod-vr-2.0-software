"""Private, reusable Basler SDK conversion for acquisition consumers (A01/A10/T01)."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any

from cephvr.shared.pixels.scaling import scale_full_range_into
from cephvr.shared.pixels.types import PixelLayout


@dataclass(frozen=True, slots=True)
class PreparedImage:
    """View of prepared pixels; caller-supplied storage remains caller-owned."""

    data: memoryview
    width: int
    height: int
    channels: int
    channel_order: str
    source_effective_bits: int
    effective_bits: int
    container_bits: int
    alignment: str
    row_stride_bytes: int


class PixelPreparationError(RuntimeError):
    """A native layout or SDK conversion cannot satisfy a consumer representation."""


class PixelPreparer:
    """Own one private converter and one reusable native source wrapper.

    The pypylon wrapper exposes ``Convert(source)`` and allocates the result image
    inside the binding. Its memoryview attachment can make a private source copy;
    CephVR-owned outputs remain caller buffers or one reusable bytearray.
    """

    def __init__(self, layout: PixelLayout) -> None:
        _validate_layout(layout)
        self.layout = layout
        try:
            importlib.import_module("pypylon")
            pylon = importlib.import_module("pypylon.pylon")
        except (ImportError, ModuleNotFoundError) as exc:
            raise PixelPreparationError(
                "Basler pypylon is required for conversion"
            ) from exc
        self._pylon: Any = pylon
        try:
            self._numpy: Any = importlib.import_module("numpy")
        except (ImportError, ModuleNotFoundError) as exc:
            raise PixelPreparationError(
                "NumPy is required for fixed-range conversion"
            ) from exc
        self._converter: Any = pylon.ImageFormatConverter()
        self._source: Any = pylon.PylonImage()
        self._source_owner: memoryview | None = None
        self._configure()
        if not callable(getattr(self._source, "AttachMemoryView", None)):
            raise PixelPreparationError(
                "pypylon PylonImage.AttachMemoryView is required"
            )
        symbol = _source_output_symbol(layout)
        self._output_symbol = symbol
        self._channels = 1 if symbol.startswith("Mono") else 3
        self._container_bits = (
            8 if symbol.endswith("8") or symbol.endswith("8packed") else 16
        )
        self._row_bytes = layout.width * self._channels * (self._container_bits // 8)
        self._output_bytes = self._row_bytes * layout.height
        self._reusable_output = bytearray(self._output_bytes)
        self._preview_outputs: dict[int, bytearray] = {}
        self._scale_scratch = self._numpy.empty(
            layout.width * layout.height * self._channels, dtype=self._numpy.uint64
        )

    def prepare_source_depth(
        self, native_pixels: bytes | bytearray | memoryview
    ) -> PreparedImage:
        return self.prepare_source_depth_into(native_pixels, self._reusable_output)

    def prepare_source_depth_into(
        self,
        native_pixels: bytes | bytearray | memoryview,
        output: bytearray | memoryview,
    ) -> PreparedImage:
        target = _writable_exact(output, self._output_bytes, "source-depth output")
        image = self._convert(native_pixels)
        try:
            _validate_converted(
                image,
                self._pylon,
                self.layout,
                self._output_symbol,
                self._output_bytes,
                self._row_bytes,
            )
            target[:] = memoryview(image.GetBuffer()).cast("B")[: self._output_bytes]
        finally:
            image.Release()
        return PreparedImage(
            target,
            self.layout.width,
            self.layout.height,
            self._channels,
            "gray" if self._channels == 1 else "RGB",
            self.layout.pixel_format.effective_bits,
            self.layout.pixel_format.effective_bits,
            self._container_bits,
            "msb" if self._container_bits == 16 else "full",
            self._row_bytes,
        )

    def prepare_preview(
        self, native_pixels: bytes | bytearray | memoryview, output_bits: int = 8
    ) -> PreparedImage:
        size = _preview_size(self.layout, self._channels, output_bits)
        output = self._preview_outputs.get(output_bits)
        if output is None:
            output = bytearray(size)
            self._preview_outputs[output_bits] = output
        return self.prepare_preview_into(native_pixels, output, output_bits)

    def prepare_preview_into(
        self,
        native_pixels: bytes | bytearray | memoryview,
        output: bytearray | memoryview,
        output_bits: int = 8,
    ) -> PreparedImage:
        target_bits = _preview_bits(output_bits)
        size = _preview_size(self.layout, self._channels, target_bits)
        target = _writable_exact(output, size, "preview output")
        image = self._convert(native_pixels)
        try:
            _validate_converted(
                image,
                self._pylon,
                self.layout,
                self._output_symbol,
                self._output_bytes,
                self._row_bytes,
            )
            scale_full_range_into(
                self._numpy,
                image,
                target,
                self.layout.pixel_format.effective_bits,
                self._container_bits,
                target_bits,
                target_bits,
                self._scale_scratch,
            )
        finally:
            image.Release()
        return PreparedImage(
            target,
            self.layout.width,
            self.layout.height,
            self._channels,
            "gray" if self._channels == 1 else "RGB",
            self.layout.pixel_format.effective_bits,
            target_bits,
            target_bits,
            "full",
            self.layout.width * self._channels * (target_bits // 8),
        )

    def prepare_recording_into(
        self,
        native_pixels: bytes | bytearray | memoryview,
        output: bytearray | memoryview,
        target_bits: int | None = None,
    ) -> PreparedImage:
        """Prepare original-depth RGB/gray and optionally quantize once for recording."""
        source_bits = self.layout.pixel_format.effective_bits
        effective_bits = source_bits if target_bits is None else target_bits
        if target_bits is not None and target_bits not in (8, 10):
            raise PixelPreparationError(
                "recording output depth must resolve to 8 or 10 bits"
            )
        container_bits = 8 if effective_bits == 8 else 16
        row_bytes = self.layout.width * self._channels * (container_bits // 8)
        output_bytes = row_bytes * self.layout.height
        target = _writable_exact(output, output_bytes, "recording output")
        image = self._convert(native_pixels)
        try:
            _validate_converted(
                image,
                self._pylon,
                self.layout,
                self._output_symbol,
                self._output_bytes,
                self._row_bytes,
            )
            if source_bits == effective_bits:
                target[:] = memoryview(image.GetBuffer()).cast("B")[:output_bytes]
            else:
                scale_full_range_into(
                    self._numpy,
                    image,
                    target,
                    source_bits,
                    self._container_bits,
                    effective_bits,
                    container_bits,
                    self._scale_scratch,
                )
        finally:
            image.Release()
        return PreparedImage(
            target,
            self.layout.width,
            self.layout.height,
            self._channels,
            "gray" if self._channels == 1 else "RGB",
            source_bits,
            effective_bits,
            container_bits,
            "msb" if container_bits == 16 else "full",
            row_bytes,
        )

    def close(self) -> None:
        """Release SDK wrapper before the retained Python source view."""
        self._source.Release()
        self._source_owner = None

    def _configure(self) -> None:
        # Truncate mode uses the shift control; pypylon makes it read-only after
        # certain other converter settings. Gamma is inactive in this mode.
        if not hasattr(self._converter, "AdditionalLeftShift"):
            raise PixelPreparationError(
                "required pypylon converter control unavailable: AdditionalLeftShift"
            )
        self._converter.AdditionalLeftShift = 0
        for parameter, enum_symbol in (
            ("OutputBitAlignment", "OutputBitAlignment_MsbAligned"),
            ("MonoConversionMethod", "MonoConversionMethod_Truncate"),
            ("InconvertibleEdgeHandling", "InconvertibleEdgeHandling_Extend"),
        ):
            enum_value = getattr(self._pylon, enum_symbol, None)
            if enum_value is None or not hasattr(self._converter, parameter):
                raise PixelPreparationError(
                    f"required pypylon converter control unavailable: {parameter}"
                )
            setattr(self._converter, parameter, enum_value)
        for parameter, enum_symbol in (
            ("OutputOrientation", "OutputOrientation_TopDown"),
        ):
            enum_value = getattr(self._pylon, enum_symbol, None)
            if enum_value is None or not hasattr(self._converter, parameter):
                raise PixelPreparationError(
                    f"required pypylon converter control unavailable: {parameter}"
                )
            setattr(self._converter, parameter, enum_value)
        if not hasattr(self._converter, "OutputPaddingX"):
            raise PixelPreparationError("pypylon OutputPaddingX control is unavailable")
        self._converter.OutputPaddingX = 0

    def _convert(self, native_pixels: bytes | bytearray | memoryview) -> Any:
        source = memoryview(native_pixels).cast("B")
        if source.nbytes != self.layout.image_payload_bytes:
            raise PixelPreparationError(
                "native payload size differs from prepared layout"
            )
        pixel_type = getattr(
            self._pylon, f"PixelType_{self.layout.pixel_format.sdk_name}", None
        )
        if pixel_type is None:
            raise PixelPreparationError(
                "pypylon does not expose the prepared native EPixelType"
            )
        pixel_type = int(pixel_type)
        if (
            self.layout.pixel_format.sdk_value != 0
            and self.layout.pixel_format.sdk_value != pixel_type
        ):
            raise PixelPreparationError(
                "prepared EPixelType value differs from the pinned pypylon mapping"
            )
        padding = _padding_x(self.layout, self._pylon, pixel_type)
        try:
            self._source.Release()
            self._source.AttachMemoryView(
                source,
                pixel_type,
                self.layout.width,
                self.layout.height,
                padding,
            )
            # On this Windows binding AttachMemoryView retains a private bytes
            # copy when native attachment is unavailable. The slot was already
            # copied, so this does not retain or expose shared-ring memory.
            self._source_owner = source
            self._converter.OutputPixelFormat = getattr(
                self._pylon, f"PixelType_{self._output_symbol}"
            )
            converted = self._converter.Convert(self._source)
        except PixelPreparationError:
            raise
        except Exception as exc:
            raise PixelPreparationError(
                f"Basler SDK pixel conversion failed: {exc}"
            ) from exc
        finally:
            self._source.Release()
            self._source_owner = None
        return converted


def _validate_layout(layout: PixelLayout) -> None:
    if layout.width <= 0 or layout.height <= 0 or layout.row_stride_bytes <= 0:
        raise PixelPreparationError("image dimensions and row stride must be positive")
    if layout.image_payload_bytes != layout.row_stride_bytes * layout.height:
        raise PixelPreparationError("payload size does not match stride and height")
    if layout.pixel_format.effective_bits not in (8, 10, 12, 16):
        raise PixelPreparationError("native effective depth is not mapped")


def _padding_x(layout: PixelLayout, pylon: Any, pixel_type: int) -> int:
    compute = getattr(pylon, "ComputePaddingX", None)
    image_size = getattr(pylon, "ComputeBufferSize", None)
    if not callable(compute) or not callable(image_size):
        raise PixelPreparationError("pypylon pixel-layout helpers are required")
    try:
        padding = int(compute(layout.row_stride_bytes, pixel_type, layout.width))
        expected = int(image_size(pixel_type, layout.width, layout.height, padding))
    except Exception as exc:
        raise PixelPreparationError(
            "pylon rejected the prepared native image stride"
        ) from exc
    if expected != layout.image_payload_bytes:
        raise PixelPreparationError(
            "pylon payload size disagrees with prepared image layout"
        )
    return padding


def _source_output_symbol(layout: PixelLayout) -> str:
    fmt = layout.pixel_format
    if fmt.channel_layout.startswith("mono"):
        return "Mono8" if fmt.effective_bits == 8 else "Mono16"
    if fmt.channel_layout.startswith(("bayer", "rgb", "bgr")):
        return "RGB8packed" if fmt.effective_bits == 8 else "RGB16packed"
    raise PixelPreparationError(
        f"unsupported native channel layout {fmt.channel_layout}"
    )


def _validate_converted(
    image: Any,
    pylon: Any,
    layout: PixelLayout,
    output_symbol: str,
    output_bytes: int,
    row_bytes: int,
) -> None:
    if not image.IsValid():
        raise PixelPreparationError("Basler converter returned an invalid image")
    if (
        int(image.GetPixelType()) != int(getattr(pylon, f"PixelType_{output_symbol}"))
        or int(image.GetWidth()) != layout.width
        or int(image.GetHeight()) != layout.height
        or int(image.GetPaddingX()) != 0
        or int(image.GetImageSize()) != output_bytes
        or row_bytes * layout.height != output_bytes
        or int(image.GetOrientation()) != int(pylon.ImageOrientation_TopDown)
    ):
        raise PixelPreparationError(
            "Basler converter output metadata differs from requested layout"
        )


def _preview_bits(output_bits: int) -> int:
    if output_bits not in (8, 16):
        raise PixelPreparationError("preview output depth must be 8 or 16 bits")
    return output_bits


def _preview_size(layout: PixelLayout, channels: int, output_bits: int) -> int:
    bits = _preview_bits(output_bits)
    return layout.width * layout.height * channels * (bits // 8)


def _writable_exact(
    output: bytearray | memoryview, size: int, description: str
) -> memoryview:
    target = memoryview(output).cast("B")
    if target.readonly or target.nbytes != size:
        raise PixelPreparationError(f"{description} has incompatible size or access")
    return target
