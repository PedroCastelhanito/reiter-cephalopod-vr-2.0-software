"""Resolved image identities and first-use requirements, independent of graphics."""

import heapq
from bisect import bisect_left
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field, replace

from cephvr.visual_stimulus.config.models.artifact_models import PreparedTrial
from cephvr.visual_stimulus.config.models.program_model import Settings

from .assets import PreparedResourceBundle
from .budget import PreparationBudget
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
                sum(
                    len(s.sparse_noise.asset_ids)
                    if s.kind == "image" and s.sparse_noise is not None
                    else 1
                    for s in epoch.settings
                )
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
                    assets = (
                        setting.sparse_noise.asset_ids
                        if setting.kind == "image" and setting.sparse_noise is not None
                        else (image_asset(setting),)
                    )
                    for selected_asset in assets:
                        if (
                            selected_asset is not None
                            and (trial, selected_asset) in aliases
                        ):
                            row.append((setting.instance_id, selected_asset))
                            first.setdefault(
                                (trial, setting.instance_id), selected_asset
                            )
                            assert setting.kind in ("image", "texture")
                            surfaces = (
                                {item.surface_id for item in setting.space.mappings}
                                if setting.space.kind == "physical_surface"
                                else set(setting.space.surfaces)
                            )
                            key = aliases[(trial, selected_asset)]
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
