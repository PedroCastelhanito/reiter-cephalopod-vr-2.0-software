"""T11 bounded protected manifest/model assets and declared external weights."""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
from typing import Any

from cephvr.tracking.config.models.methods import (
    FileLimits,
    ModelManifest,
    ModelSettings,
    ResolvedAsset,
)
from cephvr.visual_stimulus.resources.protected import ProtectedWindowsSource


class ModelAssets:
    def __init__(self) -> None:
        self.sources: list[ProtectedWindowsSource] = []
        self.evidence: list[ResolvedAsset] = []
        self.used = 0

    def read(
        self, root: Path, relative: str, maximum: int, total_limit: int
    ) -> tuple[Path, bytes]:
        base = root.resolve(strict=True)
        path = base.joinpath(*PurePosixPath(relative).parts).resolve(strict=True)
        if not path.is_relative_to(base):
            raise ValueError("model asset escapes its declared root")
        source = ProtectedWindowsSource(path)
        self.sources.append(source)
        with source.independent_reader() as handle:
            size = path.stat().st_size
            if size > maximum or self.used + size > total_limit:
                raise ValueError("model assets exceed preparation budget")
            data = handle.read(size + 1)
        if len(data) != size:
            raise ValueError("protected model asset size changed")
        self.used += size
        self.evidence.append(
            ResolvedAsset(
                relative_path=relative,
                byte_length=size,
                sha256=hashlib.sha256(data).hexdigest(),
            )
        )
        return path, data

    def prepare(
        self, settings: ModelSettings, root: str, limits: FileLimits
    ) -> tuple[ModelManifest, Any]:
        import onnx

        path, data = self.read(
            Path(root),
            settings.manifest.relative_path,
            limits.max_document_bytes,
            limits.max_asset_bytes,
        )
        manifest = ModelManifest.model_validate_json(data)
        _, model_data = self.read(
            path.parent,
            manifest.model.relative_path,
            limits.max_asset_bytes,
            limits.max_asset_bytes,
        )
        graph = onnx.load_model_from_string(model_data)
        declared = {asset.relative_path for asset in manifest.external_weights}
        loaded = {}
        for relative in declared:
            _, loaded[relative] = self.read(
                path.parent, relative, limits.max_asset_bytes, limits.max_asset_bytes
            )
        used = set()
        # Traverse all tensor-bearing graph attributes as well as initializers.
        tensors = list(onnx.external_data_helper._get_all_tensors(graph))
        for tensor in tensors:
            if tensor.data_location != onnx.TensorProto.EXTERNAL:
                continue
            metadata = {entry.key: entry.value for entry in tensor.external_data}
            relative = metadata.get("location", "")
            if relative not in declared:
                raise ValueError("ONNX references undeclared external weights")
            content = loaded[relative]
            offset = int(metadata.get("offset", "0"))
            length = int(metadata.get("length", str(len(content) - offset)))
            if offset < 0 or length < 0 or offset + length > len(content):
                raise ValueError("external ONNX tensor span exceeds asset")
            tensor.raw_data = content[offset : offset + length]
            tensor.data_location = onnx.TensorProto.DEFAULT
            del tensor.external_data[:]
            used.add(relative)
        if used != declared:
            raise ValueError("declared external weights are not referenced by graph")
        onnx.checker.check_model(graph)
        return manifest, graph

    def close(self) -> None:
        while self.sources:
            self.sources[-1].close_after_consumers()
            self.sources.pop()
