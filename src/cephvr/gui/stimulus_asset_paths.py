"""Apply typed stimulus-file paths to a candidate program without redundant work."""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cephvr.gui.program_editing import NodePath, data_node
from cephvr.gui.stimulus_files import (
    StimulusFile,
    apply_texture_dimensions,
    resolve_stimulus_file,
    select_epoch_asset,
)

_MEMO_LIMIT = 64


class AssetPathResolver:
    """Re-use a resolved plain media file while its path, stamp and target are unchanged.

    Texture JSON recipes are never memoized: their image dependencies are not covered
    by the recipe file's own stamp.
    """

    def __init__(self) -> None:
        self.memo: dict[tuple[Any, ...], StimulusFile] = {}

    def resolve(
        self, root: str, text: str, *, texture: bool, grating: bool
    ) -> StimulusFile:
        source = Path(text)
        full = source if source.is_absolute() else Path(root) / source
        stamp = None
        if full.suffix.lower() != ".json":
            try:
                stat = full.stat()
                stamp = (stat.st_size, stat.st_mtime_ns)
            except OSError:
                pass
        key = (root, str(full), texture, grating, stamp)
        cached = self.memo.get(key) if stamp is not None else None
        if cached is not None and (Path(root) / cached.path).is_file():
            return cached
        result = resolve_stimulus_file(
            root, str(full), texture=texture, grating=grating
        )
        if stamp is not None:
            if len(self.memo) >= _MEMO_LIMIT:
                self.memo.clear()
            self.memo[key] = result
        return result


def apply_asset_edits(
    candidate: dict[str, Any],
    setting: dict[str, Any],
    node_index: NodePath,
    layer_index: int,
    typed: Mapping[str, str],
    pending_profiles: Mapping[str, str],
    *,
    root: str,
    compact: bool,
    replacing_asset: str | None,
    resolver: AssetPathResolver,
) -> None:
    """Fold each edited stimulus-file path (``typed``: asset id -> text) into ``candidate``."""
    for asset in tuple(candidate["assets"]):
        identity = asset["asset_id"]
        if identity == replacing_asset:
            continue  # The picker validates and applies this replacement atomically.
        if identity not in typed:
            continue
        path = typed[identity]
        if compact and not path:
            if asset["logical_path"]:
                raise ValueError("Choose an asset")
            continue
        profile = pending_profiles.get(identity, asset["profile"])
        if path != asset["logical_path"] and identity not in pending_profiles:
            selected = resolver.resolve(
                root,
                path,
                texture=setting["kind"] == "texture",
                grating=setting.get("grating", False),
            )
            path, profile = selected.path, selected.profile
            apply_texture_dimensions(setting, selected)
        select_epoch_asset(candidate, node_index, layer_index, identity, path, profile)


def replace_tile(
    candidate: dict[str, Any],
    node_index: NodePath,
    layer_index: int,
    selected: StimulusFile,
) -> None:
    """Swap in an exported physical tile, adopting its dimensions, in one candidate."""
    target = data_node(candidate, node_index)["settings"][layer_index]
    apply_texture_dimensions(target, selected)
    select_epoch_asset(
        candidate,
        node_index,
        layer_index,
        target["pattern"]["asset_id"],
        selected.path,
        selected.profile,
    )


def apply_link(setting: dict[str, Any], linked_to: str | None) -> None:
    """Record the motion source; a linked layer holds its own motion and phase."""
    setting["linked_to"] = linked_to
    if linked_to is not None:
        setting["phase_x"] = {"kind": "hold"}
        setting["phase_y"] = {"kind": "hold"}
        setting["motion"] = {key: {"kind": "hold"} for key in ("x", "y", "rotation")}
