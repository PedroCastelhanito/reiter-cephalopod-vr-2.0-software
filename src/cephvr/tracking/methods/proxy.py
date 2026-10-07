"""T42–T45 shared water/fin area-weighted response and interval-average filter."""

from __future__ import annotations

import math
from typing import Any, Literal

import numpy as np

from cephvr.tracking.config.models.methods import (
    FileLimits,
    FinFlowSettings,
    WaterFlowSettings,
)
from cephvr.tracking.config.models.records import (
    DriveTriplet,
    FlowProxyEvidence,
    FlowSampleCounts,
    FlowSectionEvidence,
)
from cephvr.tracking.methods.association import Association, associate
from cephvr.tracking.methods.flow_buffers import host_arrays
from cephvr.tracking.methods.screening import screen
from cephvr.tracking.types import (
    FlowGridMapping,
    FlowProxyInput,
    ImageLayout,
    SamplingGeometry,
)


class FlowProxy:
    def prepare(
        self,
        settings: WaterFlowSettings,
        layout: ImageLayout,
        mapping: FlowGridMapping,
        limits: FileLimits,
    ) -> None:
        self.settings, self.layout, self.mapping, self.maximum = (
            settings,
            layout,
            mapping,
            limits.max_native_bytes,
        )
        self.pipeline: Literal["water_flow", "fin_flow"] = (
            "fin_flow" if isinstance(settings, FinFlowSettings) else "water_flow"
        )
        self.association: Association | None = None
        self.geometry_id: str | None = None
        self.end: Any = None
        self.last: tuple[bytes, str, int, int] | None = None
        self.cached_key: tuple[bytes, str, int, int] | None = None
        self.cached: FlowProxyEvidence | None = None
        cells = mapping.grid_width * mapping.grid_height
        neighbors = (2 * settings.quality.radius_cells + 1) ** 2 - 1
        if (
            cells * (settings.sections.count * 8 + 256) > self.maximum // 2
            or neighbors * 64 + 128 > self.maximum // 8
        ):
            raise ValueError(
                "flow grid, sections or median scratch exceed preparation budget"
            )

    def prepare_geometry(self, geometry: SamplingGeometry) -> None:
        if self.geometry_id != geometry.lease_id:
            self.association = associate(
                geometry, self.mapping, self.layout, self.settings, self.maximum // 2
            )
            self.geometry_id = geometry.lease_id

    def compute(self, sample: FlowProxyInput) -> FlowProxyEvidence:
        flow = sample.flow
        if (
            flow.work != sample.work
            or flow.generation != sample.reset_generation
            or flow.mapping_id != self.mapping.mapping_id
            or sample.mapping.mapping_id != flow.mapping_id
        ):
            raise ValueError("estimator work/generation/mapping mismatch")
        if (flow.grid_width, flow.grid_height) != (
            self.mapping.grid_width,
            self.mapping.grid_height,
        ):
            raise ValueError("grid dimensions differ from prepared mapping")
        dt = (flow.later.host_receipt_ns - flow.earlier.host_receipt_ns) / 1e9
        if dt <= 0 or flow.later.frame_id != flow.earlier.frame_id + 1:
            raise ValueError(
                "flow pair must have contiguous IDs and positive source time"
            )
        key = (
            sample.work.SerializeToString(deterministic=True),
            flow.generation,
            flow.later.frame_id,
            flow.later.host_receipt_ns,
        )
        if key == self.cached_key and self.cached is not None:
            return self.cached
        vector, cost, validity = host_arrays(flow, sample.host_view)
        if sample.geometry is None or sample.pose.disposition not in (
            "manual",
            "valid",
        ):
            result = self.invalid("pose_" + sample.pose.disposition)
        else:
            self.prepare_geometry(sample.geometry)
            association = self.association
            assert association is not None
            displacement = vector.astype(np.float64) * flow.component_scale
            if sample.transform is not None:
                displacement[..., 0] /= sample.transform.scale_x
                displacement[..., 1] /= sample.transform.scale_y
            area = association.area.sum(axis=1)
            accepted, counts = screen(
                displacement,
                area.reshape(vector.shape[:2]) > 0,
                cost,
                validity,
                self.settings.quality,
                self.maximum // 8,
            )
            accepted = accepted.ravel()
            accepted_areas = association.area[accepted].sum(axis=0)
            sections = tuple(
                FlowSectionEvidence(
                    section_index=i,
                    intended_area_px2=float(a),
                    visible_area_px2=float(v),
                    accepted_area_px2=float(c),
                )
                for i, (a, v, c) in enumerate(
                    zip(
                        association.intended,
                        association.visible,
                        accepted_areas,
                        strict=True,
                    )
                )
            )
            required = (
                association.intended > 0
                if self.pipeline == "fin_flow"
                else np.ones(len(sections), dtype=bool)
            )
            if (
                not required.any()
                or np.any(association.intended[required] <= 0)
                or np.any(
                    accepted_areas[required]
                    < association.intended[required]
                    * self.settings.support.minimum_accepted_area_fraction
                )
            ):
                result = self.invalid("section_support", sections, counts)
            else:
                basis = np.array(
                    [sample.geometry.anterior_unit_xy, sample.geometry.left_unit_xy]
                ).T
                velocity = displacement.reshape(-1, 2)[accepted] @ basis / dt
                weights = area[accepted]
                total = weights.sum()
                positions = association.positions[accepted]
                centre = np.sum(weights[:, None] * positions, axis=0) / total
                mean = np.sum(weights[:, None] * velocity, axis=0) / total
                relative = positions - centre
                moment = float(
                    np.sum(
                        weights
                        * (
                            relative[:, 0] * velocity[:, 1]
                            - relative[:, 1] * velocity[:, 0]
                        )
                    )
                    / total
                )
                second = float(
                    np.sum(weights * np.sum(relative * relative, axis=1)) / total
                )
                if (
                    not math.isfinite(second)
                    or second <= 0
                    or not math.isfinite(moment)
                    or not np.isfinite(mean).all()
                ):
                    result = self.invalid("degenerate_response", sections, counts)
                else:
                    raw = np.array([-mean[0], -mean[1], -moment / second])
                    previous = (
                        key[0],
                        key[1],
                        flow.earlier.frame_id,
                        flow.earlier.host_receipt_ns,
                    )
                    seeded = self.end is None or self.last != previous
                    if seeded:
                        average, end = raw.copy(), raw.copy()
                    else:
                        z = dt / self.settings.smoothing.time_constant_s
                        alpha = -math.expm1(-z)
                        factor = 1 - z / 2 + z * z / 6 if z < 1e-6 else alpha / z
                        average = raw + (self.end - raw) * factor
                        end = self.end + alpha * (raw - self.end)
                    self.end, self.last = end, key
                    result = FlowProxyEvidence(
                        schema_version=1,
                        pipeline_id=self.pipeline,
                        validity="valid",
                        reason=None,
                        sections=sections,
                        counts=counts,
                        centroid_body_px=tuple(centre),
                        mean_velocity_body_px_per_s=tuple(mean),
                        centred_moment_px2_per_s=moment,
                        centred_second_moment_px2=second,
                        raw=_drive(raw),
                        filtered_average=_drive(average),
                        filter_end=_drive(end),
                        filter_disposition="seeded" if seeded else "continued",
                    )
        self.cached_key, self.cached = key, result
        return result

    def invalid(
        self,
        reason: str,
        sections: tuple[FlowSectionEvidence, ...] = (),
        counts: FlowSampleCounts | None = None,
    ) -> FlowProxyEvidence:
        self.end, self.last = None, None
        return FlowProxyEvidence(
            schema_version=1,
            pipeline_id=self.pipeline,
            validity="invalid",
            reason=reason,
            sections=sections,
            counts=counts,
            centroid_body_px=None,
            mean_velocity_body_px_per_s=None,
            centred_moment_px2_per_s=None,
            centred_second_moment_px2=None,
            raw=None,
            filtered_average=None,
            filter_end=None,
            filter_disposition="cleared",
        )

    def reset(self, generation: str) -> None:
        self.end, self.last, self.cached_key, self.cached = None, None, None, None

    def close(self, deadline_host_ns: int) -> bool:
        self.association = None
        return True


def _drive(value: Any) -> DriveTriplet:
    return DriveTriplet(
        forward_drive=float(value[0]),
        sideways_drive=float(value[1]),
        turn_drive=float(value[2]),
    )
