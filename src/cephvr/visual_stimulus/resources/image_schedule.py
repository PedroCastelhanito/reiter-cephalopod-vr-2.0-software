"""Resolved image identities and first-use requirements, independent of graphics."""

import heapq
from bisect import bisect_left
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field, replace

from cephvr.visual_stimulus.config.models.artifact_models import PreparedTrial
from cephvr.visual_stimulus.config.models.program_model import Settings

from .assets import PreparedResourceBundle
from .budget import PreparationBudget
from .image_crops import ImageCrop
from .image_source import ImageSource


def image_asset(settings: Settings) -> str | None:
    if settings.kind == "image":
        return str(settings.asset_id)
    if settings.kind == "texture" and settings.pattern.kind == "image_tile":
        return str(settings.pattern.asset_id)
    return None


@dataclass(frozen=True, slots=True)
class ImageSchedule:
    sources: Mapping[str, ImageSource]
    aliases: Mapping[tuple[str, str], str]
    generations: Mapping[str, str]
    epochs: Mapping[str, tuple[tuple[tuple[str, str], ...], ...]]
    first: Mapping[tuple[str, str], str]
    indices: Mapping[tuple[str, str], int]
    occurrences: Mapping[str, Mapping[str, tuple[int, ...]]] = field(init=False)

    def __post_init__(self) -> None:
        indexed = {}
        for trial, rows in self.epochs.items():
            uses: dict[str, list[int]] = {}
            for index, row in enumerate(rows):
                for key in {self.aliases[(trial, asset)] for _, asset in row}:
                    uses.setdefault(key, []).append(index)
            indexed[trial] = {key: tuple(values) for key, values in uses.items()}
        object.__setattr__(self, "occurrences", indexed)

    @classmethod
    def build(
        cls,
        artifacts: tuple[PreparedTrial, ...],
        bundles: Mapping[str, PreparedResourceBundle],
        budget: PreparationBudget | None = None,
    ) -> "ImageSchedule":
        if budget is not None:
            aliases_count = sum(
                len(bundle.image_sources) for bundle in bundles.values()
            )
            settings_count = sum(
                len(epoch.settings)
                for artifact in artifacts
                for epoch in artifact.epochs
            )
            epoch_count = sum(len(artifact.epochs) for artifact in artifacts)
            budget.reserve(
                owner="visual_stimulus:image-schedule",
                cpu_bytes=aliases_count * 4096
                + settings_count * 512
                + epoch_count * 128,
                gpu_bytes=0,
            )
        sources: dict[str, ImageSource] = {}
        aliases: dict[tuple[str, str], str] = {}
        generations: dict[str, str] = {}
        epochs: dict[str, tuple[tuple[tuple[str, str], ...], ...]] = {}
        first: dict[tuple[str, str], str] = {}
        indices: dict[tuple[str, str], int] = {}
        used_outputs: dict[str, set[str]] = {}
        crop_bounds: dict[str, dict[str, ImageCrop]] = {}
        crop_disabled: set[tuple[str, str]] = set()
        from .image_crops import fold_crop

        footprint_cache = {}
        for artifact in artifacts:
            trial = artifact.identity.trial_id
            generations[trial] = artifact.identity.resource_generation
            for index, (asset, source) in enumerate(
                sorted(bundles[trial].image_sources.items())
            ):
                sources.setdefault(source.key, source)
                aliases[(trial, asset)] = source.key
                indices[(trial, asset)] = index
            rows = []
            for epoch in artifact.epochs:
                row = []
                for setting in epoch.settings:
                    selected_asset = image_asset(setting)
                    if selected_asset is None or (trial, selected_asset) not in aliases:
                        continue
                    row.append((setting.instance_id, selected_asset))
                    first.setdefault((trial, setting.instance_id), selected_asset)
                    assert setting.kind in ("image", "texture")
                    surfaces = (
                        {item.surface_id for item in setting.space.mappings}
                        if setting.space.kind == "physical_surface"
                        else set(setting.space.surfaces)
                    )
                    key = aliases[(trial, selected_asset)]
                    for mapping in artifact.display.active_mappings:
                        if mapping.surface_id not in surfaces:
                            continue
                        output = mapping.output_id
                        cache_key = (trial, key, mapping.mapping_id)
                        eligible = setting.kind == "image" and setting.fit == "fold"
                        if eligible and cache_key not in footprint_cache:
                            footprint_cache[cache_key] = fold_crop(
                                artifact, mapping.mapping_id, sources[key]
                            )
                        rectangle = footprint_cache[cache_key] if eligible else None
                        if rectangle is None:
                            crop_disabled.add((key, output))
                        else:
                            bounds = crop_bounds.setdefault(key, {})
                            if output in bounds and bounds[output] != rectangle:
                                raise ValueError(
                                    "shared Fold image requires identical prepared mapping"
                                )
                            bounds[output] = rectangle
                    used_outputs.setdefault(key, set()).update(
                        mapping.output_id
                        for mapping in artifact.display.active_mappings
                        if mapping.surface_id in surfaces
                    )
                rows.append(tuple(row))
            epochs[trial] = tuple(rows)
        for key, outputs in used_outputs.items():
            source = sources[key]
            sources[key] = replace(
                source,
                output_ids=tuple(sorted(outputs)),
                gpu_bytes=source.width * source.height * 16 * len(outputs),
            )
            if outputs and all(
                (key, output) not in crop_disabled for output in outputs
            ):
                crops = []
                offset = 0
                for output in sorted(outputs):
                    crop = replace(crop_bounds[key][output], offset=offset)
                    crops.append(crop)
                    offset += crop.width * crop.height * 16
                sources[key] = replace(
                    sources[key], output_crops=tuple(crops), gpu_bytes=offset
                )
        return cls(sources, aliases, generations, epochs, first, indices)

    @property
    def anchors(self) -> frozenset[str]:
        return frozenset(
            self.aliases[(trial, asset)] for (trial, _), asset in self.first.items()
        )

    def lookahead(self, trial: str) -> "ImageLookahead":
        return ImageLookahead(self.occurrences[trial])


class ImageLookahead:
    """Advance next-use indices; enumerate only the nearest requested heap entries."""

    def __init__(self, occurrences: Mapping[str, tuple[int, ...]]) -> None:
        self.occurrences = occurrences
        self._heap = [(uses[0], key) for key, uses in occurrences.items()]
        heapq.heapify(self._heap)
        self._epoch = 0

    def advance(self, epoch: int) -> None:
        if epoch < self._epoch:
            raise ValueError("image lookahead cannot move its epoch backwards")
        self._epoch = epoch
        while self._heap and self._heap[0][0] < epoch:
            _, key = heapq.heappop(self._heap)
            uses = self.occurrences[key]
            index = bisect_left(uses, epoch)
            if index < len(uses):
                heapq.heappush(self._heap, (uses[index], key))

    def __iter__(self) -> Iterator[str]:
        if not self._heap:
            return
        frontier = [(self._heap[0], 0)]
        while frontier:
            (_, key), index = heapq.heappop(frontier)
            yield key
            for child in (index * 2 + 1, index * 2 + 2):
                if child < len(self._heap):
                    heapq.heappush(frontier, (self._heap[child], child))
