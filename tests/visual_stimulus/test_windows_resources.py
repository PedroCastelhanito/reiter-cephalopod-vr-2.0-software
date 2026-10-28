"""Windows-only ownership checks; no GPU, camera or experiment hardware is used."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from cephvr.platform.windows.protected_source import (
    ProtectedSourceError,
    ProtectedWindowsSource,
)

pytestmark = [
    pytest.mark.windows,
    pytest.mark.skipif(
        sys.platform != "win32", reason="requires Windows file sharing semantics"
    ),
]


def test_protected_source_denies_mutation_until_all_reader_owners_close(tmp_path):
    path = tmp_path / "asset.bin"
    path.write_bytes(b"0123456789")
    source = ProtectedWindowsSource(path)
    try:
        with (
            source.independent_reader() as first,
            source.independent_reader() as second,
        ):
            assert first.read(2) == b"01"
            assert second.read(4) == b"0123"
            assert first.read(2) == b"23"
            with pytest.raises(OSError):
                path.write_bytes(b"replaced")
            with pytest.raises(OSError):
                path.rename(tmp_path / "moved.bin")
            assert source.identity == ProtectedWindowsSource._file_identity(
                source._handle
            )
        for _ in range(32):
            with source.independent_reader() as reader:
                assert reader.read() == b"0123456789"
            assert reader.closed
    finally:
        source.close_after_consumers()
    source.close_after_consumers()
    with pytest.raises(ProtectedSourceError, match="closed"):
        source.independent_reader()
    path.write_bytes(b"released")
    assert path.read_bytes() == b"released"


def test_protected_source_identity_reuses_native_abi_type(monkeypatch):
    import ctypes
    from types import SimpleNamespace

    observed = []

    class Information:
        succeeded = True

        def __call__(self, handle, info):
            observed.append(self.argtypes[1])
            info._obj.volume = handle
            info._obj.index_high = handle + 1
            info._obj.index_low = handle + 2
            return self.succeeded

    information = Information()
    monkeypatch.setattr(
        ctypes,
        "WinDLL",
        lambda *args, **kwargs: SimpleNamespace(GetFileInformationByHandle=information),
    )
    for handle in range(256):
        assert ProtectedWindowsSource._file_identity(handle) == (
            handle,
            handle + 1,
            handle + 2,
        )
    assert len(set(observed)) == 1
    information.succeeded = False
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 6)
    with pytest.raises(OSError) as error:
        ProtectedWindowsSource._file_identity(1)
    assert error.value.winerror == 6


@pytest.mark.parametrize("reuse_fingerprints", [False, True])
@pytest.mark.parametrize("changed_interpretation", [False, True])
def test_setup_batch_reuses_hash_and_validation_but_keeps_each_source_protected(
    tmp_path,
    monkeypatch,
    reuse_fingerprints,
    changed_interpretation,
):
    from PIL import Image
    from PIL.PngImagePlugin import PngInfo

    from cephvr.visual_stimulus.config.models.program_model import Asset, ColorOverride
    from cephvr.visual_stimulus.resources.assets import ProtectedFingerprintCache
    from cephvr.visual_stimulus.resources.budget import BoundedBudget
    from cephvr.visual_stimulus.resources.prepare import prepare_resources
    from cephvr.visual_stimulus.resources.progress import PreparationMetrics

    path = tmp_path / "image.png"
    metadata = PngInfo()
    metadata.add(b"sRGB", b"\x00")
    Image.new("RGB", (32, 32), "red").save(path, pnginfo=metadata)
    budget = BoundedBudget(cpu_limit=1_000_000, gpu_limit=1_000_000)
    cache = ProtectedFingerprintCache(budget)
    metrics = PreparationMetrics()
    validated = {}
    bundles = []
    readers = []
    original = ProtectedWindowsSource.independent_reader

    def counted(source):
        readers.append(source)
        return original(source)

    monkeypatch.setattr(ProtectedWindowsSource, "independent_reader", counted)
    try:
        for index in range(6):
            # Asset IDs and trial owners differ; the protected file is identical.
            asset = Asset(
                asset_id=f"image{index}",
                logical_path=path.name,
                profile="png_uint_v1",
                color_override=ColorOverride(
                    transfer="srgb",
                    primaries="rec709_d65",
                    range="full",
                    matrix="rgb",
                    chroma_location="none",
                    reason=f"source declaration {index}",
                ),
            )
            if index == 5 and changed_interpretation:
                asset = asset.model_copy(
                    update={
                        "color_override": ColorOverride(
                            transfer="linear",
                            primaries="rec709_d65",
                            range="full",
                            matrix="rgb",
                            chroma_location="none",
                            reason="interpretation test",
                        )
                    }
                )
            bundles.append(
                prepare_resources(
                    SimpleNamespace(assets=(asset,), sequence=(), instances=()),
                    tmp_path,
                    budget,
                    announce=lambda *_: None,
                    snapshot_limit_bytes=1_000_000,
                    video_index_limit_bytes=1_000_000,
                    glb_element_limit=100,
                    defer_images=True,
                    owner_prefix=f"trial{index}",
                    validated_images=validated,
                    fingerprints=cache if reuse_fingerprints else None,
                    metrics=metrics,
                )
            )
        unique = 2 if changed_interpretation else 1
        assert metrics.images_validated == unique
        assert metrics.sources_hashed == (1 if reuse_fingerprints else 6)
        assert metrics.fingerprints_reused == (5 if reuse_fingerprints else 0)
        assert metrics.validations_reused == 6 - unique
        # One hash read and one image validation read, regardless of repetitions.
        assert len(readers) == (1 if reuse_fingerprints else 6) + unique
        assert len(validated) == unique
        assert len({id(b.asset_set.assets[0].source) for b in bundles}) == 6
        assert bundles[0].asset_set.close() == ()
        with pytest.raises(OSError):
            path.write_bytes(b"replacement")
        with pytest.raises(OSError):
            path.rename(tmp_path / "moved.png")
    finally:
        for bundle in bundles:
            assert bundle.asset_set.close() == ()
    path.write_bytes(b"released")


def test_fingerprint_batch_rechecks_after_release_and_preserves_limits(tmp_path):
    from cephvr.visual_stimulus.config.models.program_model import Asset
    from cephvr.visual_stimulus.resources.assets import (
        ProtectedFingerprintCache,
        prepare_assets,
    )
    from cephvr.visual_stimulus.resources.budget import BoundedBudget
    from cephvr.visual_stimulus.resources.progress import PreparationMetrics

    path = tmp_path / "recipe.json"
    path.write_bytes(b"1234567890")
    asset = Asset(
        asset_id="recipe",
        logical_path=path.name,
        profile="cephvr1_texture_json_v1",
        color_override=None,
    )
    program = SimpleNamespace(assets=(asset,))
    budget = BoundedBudget(cpu_limit=100_000, gpu_limit=100_000)
    cache = ProtectedFingerprintCache(budget)
    metrics = PreparationMetrics()

    def prepare(limit=100):
        return prepare_assets(
            program,
            tmp_path,
            budget,
            announce=lambda *_: None,
            snapshot_limit_bytes=100,
            max_document_bytes=limit,
            defer_images=True,
            fingerprints=cache,
            metrics=metrics,
        )

    first = prepare()
    try:
        with pytest.raises(ValueError, match="document byte limit"):
            prepare(5)
        with pytest.raises(OSError):
            path.write_bytes(b"still protected")
    finally:
        assert first.close() == ()
    path.write_bytes(b"abcdefghij")
    second = prepare()
    try:
        assert first.assets[0].sha256 != second.assets[0].sha256
        assert metrics.sources_hashed == 2
    finally:
        assert second.close() == ()
    assert budget.usage.gpu_bytes == 0


def test_cached_fingerprint_does_not_bypass_cancellation(tmp_path):
    import threading

    from cephvr.visual_stimulus.config.models.program_model import Asset
    from cephvr.visual_stimulus.resources.assets import (
        ProtectedFingerprintCache,
        prepare_assets,
    )
    from cephvr.visual_stimulus.resources.budget import BoundedBudget

    path = tmp_path / "image.png"
    path.write_bytes(b"protected bytes")
    program = SimpleNamespace(
        assets=(
            Asset(
                asset_id="image",
                logical_path=path.name,
                profile="png_uint_v1",
                color_override=None,
            ),
        )
    )
    cancelled = threading.Event()
    budget = BoundedBudget(cpu_limit=100_000, gpu_limit=100_000, cancelled=cancelled)
    cache = ProtectedFingerprintCache(budget)
    announced = []

    def prepare():
        return prepare_assets(
            program,
            tmp_path,
            budget,
            announce=lambda *args: announced.append(args),
            snapshot_limit_bytes=100,
            defer_images=True,
            fingerprints=cache,
        )

    first = prepare()
    try:
        cancelled.set()
        with pytest.raises(InterruptedError):
            prepare()
        assert len(announced) == 1
    finally:
        assert first.close() == ()
