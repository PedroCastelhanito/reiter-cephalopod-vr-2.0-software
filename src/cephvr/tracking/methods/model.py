"""T11 one prepared CUDA ONNX session, reusable input and bounded candidate output."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from cephvr.platform.windows.nvidia_device import verify_tracking_device
from cephvr.tracking.config.annotations import search as validate_search
from cephvr.tracking.config.models.methods import FileLimits, ModelSettings
from cephvr.tracking.methods.model_assets import ModelAssets
from cephvr.tracking.methods.model_placement import verify_placement
from cephvr.tracking.methods.model_tensor import ModelTensor
from cephvr.tracking.types import ImageLayout, PoseCandidate, PrivateFrame
from cephvr.tracking.v1.pose_pb2 import PoseSearchRegion, SubjectReferenceSettings


class ModelPose:
    def __init__(self) -> None:
        self.assets = ModelAssets()
        self.session: Any = None
        self.binding: Any = None
        self.device_input: Any = None

    def prepare(
        self,
        settings: ModelSettings,
        layout: ImageLayout,
        search: PoseSearchRegion,
        reference: SubjectReferenceSettings,
        asset_root: str,
        limits: FileLimits,
    ) -> None:
        import onnx
        import onnxruntime as ort

        validate_search(search, layout.width, layout.height)
        self.device = verify_tracking_device(settings.device_ordinal)
        manifest, graph = self.assets.prepare(settings, asset_root, limits)
        self.settings, self.manifest = settings, manifest
        channels = 1 if manifest.channels == "gray" else 3
        shape = [1, channels, manifest.input_height_px, manifest.input_width_px]
        tensor_bytes = int(np.prod(shape)) * 4
        if (
            self.assets.used + tensor_bytes * 4 + manifest.maximum_candidates * 40 * 4
            > limits.max_native_bytes
        ):
            raise ValueError(
                "ONNX assets and tensor workspace exceed prepared memory budget"
            )
        self.tensor = ModelTensor(manifest, layout, search)
        options = ort.SessionOptions()
        options.enable_profiling = True
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        with tempfile.TemporaryDirectory(prefix="cephvr-tracking-ort-") as temporary:
            options.profile_file_prefix = str(Path(temporary) / "placement")
            optimized = Path(temporary) / "optimized.onnx"
            options.optimized_model_filepath = str(optimized)
            self.session = ort.InferenceSession(
                graph.SerializeToString(),
                sess_options=options,
                providers=[
                    (
                        "CUDAExecutionProvider",
                        {
                            "device_id": settings.device_ordinal,
                            "gpu_mem_limit": limits.max_native_bytes - self.assets.used,
                            "arena_extend_strategy": "kSameAsRequested",
                            "do_copy_in_default_stream": True,
                        },
                    ),
                    "CPUExecutionProvider",
                ],
            )
            self.session.disable_fallback()
            if "CUDAExecutionProvider" not in self.session.get_providers():
                raise ValueError("CUDA inference provider is not active")
            inputs, outputs = self.session.get_inputs(), self.session.get_outputs()
            if (
                len(inputs) != 1
                or inputs[0].name != manifest.input_name
                or inputs[0].type != "tensor(float)"
                or inputs[0].shape != shape
            ):
                raise ValueError(
                    "model input differs from fixed exported tensor contract"
                )
            if (
                len(outputs) != 1
                or outputs[0].name != manifest.output_name
                or outputs[0].type != "tensor(float)"
                or len(outputs[0].shape) != 3
                or outputs[0].shape[0] != 1
                or outputs[0].shape[2] != 10
            ):
                raise ValueError(
                    "model output differs from exported candidate contract"
                )
            count = outputs[0].shape[1]
            if isinstance(count, int) and not 0 <= count <= manifest.maximum_candidates:
                raise ValueError("exported candidate count exceeds manifest bound")
            self.device_input = ort.OrtValue.ortvalue_from_shape_and_type(
                shape, np.float32, "cuda", settings.device_ordinal
            )
            self.binding = self.session.io_binding()
            self.binding.bind_ortvalue_input(manifest.input_name, self.device_input)
            self.binding.bind_output(manifest.output_name, "cpu")
            self.device_input.update_inplace(np.zeros(shape, dtype=np.float32))
            self.binding.synchronize_inputs()
            self.session.run_with_iobinding(self.binding)
            self.binding.synchronize_outputs()
            self.tensor.candidates(self.binding.copy_outputs_to_cpu()[0], settings)
            profile = Path(self.session.end_profiling())
            if (
                profile.stat().st_size > limits.max_document_bytes
                or optimized.stat().st_size > limits.max_asset_bytes
            ):
                raise ValueError("ORT preparation evidence exceeds file bounds")
            self.cpu_nodes = verify_placement(
                onnx.load_model(optimized), json.loads(profile.read_text())
            )
        self.version = ort.__version__

    def compute(self, frame: PrivateFrame) -> tuple[PoseCandidate, ...]:
        if self.session is None:
            raise RuntimeError("model session is not prepared")
        tensor = self.tensor.prepare(frame)
        self.device_input.update_inplace(tensor)
        self.binding.synchronize_inputs()
        self.session.run_with_iobinding(self.binding)
        self.binding.synchronize_outputs()
        return self.tensor.candidates(
            self.binding.copy_outputs_to_cpu()[0], self.settings
        )

    def reset(self, generation: str) -> None:
        pass

    def close(self, deadline_host_ns: int) -> bool:
        # Called by pose owner only after synchronous inference has returned.
        self.binding, self.device_input, self.session = None, None, None
        self.assets.close()
        return True
