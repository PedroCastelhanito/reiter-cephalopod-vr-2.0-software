"""Bound display-only hints at both authenticated command boundaries."""

from cephvr.control.v1 import services_pb2 as rpc


def valid_stimulus_tiles(hint: rpc.PreviewWindowPlacement) -> bool:
    tiles = hint.stimulus_tiles
    return (
        (
            not hint.HasField("stimulus_background_rgb")
            or hint.stimulus_background_rgb <= 0xFFFFFF
        )
        and len(hint.stimulus_surface_colors) <= 4
        and all(
            name in ("Left", "Front", "Right", "Bottom") and color <= 0xFFFFFF
            for name, color in hint.stimulus_surface_colors.items()
        )
        and len(hint.hidden_stimulus_surfaces) <= 4
        and len(set(hint.hidden_stimulus_surfaces))
        == len(hint.hidden_stimulus_surfaces)
        and all(
            name in ("Left", "Front", "Right", "Bottom")
            for name in hint.hidden_stimulus_surfaces
        )
        and not set(hint.hidden_stimulus_surfaces).intersection(
            tile.surface for tile in tiles
        )
        and len(tiles) <= 4
        and len({tile.surface for tile in tiles}) == len(tiles)
        and all(
            tile.surface in ("Left", "Front", "Right", "Bottom")
            and 128 <= tile.side <= 2048
            and abs(tile.x) <= 1_000_000
            and abs(tile.y) <= 1_000_000
            for tile in tiles
        )
    )


def valid_preview_placement(
    request: rpc.CameraCommandRequest | rpc.AcquisitionCameraCommand,
) -> bool:
    if not request.HasField("preview_placement"):
        return True
    hint = request.preview_placement
    return (
        request.kind == rpc.CAMERA_COMMAND_KIND_SHOW_PREVIEW
        and not hint.stimulus_tiles
        and not hint.hidden_stimulus_surfaces
        and not hint.HasField("stimulus_background_rgb")
        and not hint.stimulus_surface_colors
        and all(
            not hint.HasField(field) or getattr(hint, field) <= 0xFFFFFF
            for field in ("camera_caption_rgb", "camera_caption_text_rgb")
        )
        and 128 <= hint.side <= 2048
        and abs(hint.x) <= 1_000_000
        and abs(hint.y) <= 1_000_000
        and (
            not (
                hint.gui_window_handle
                or hint.gui_process_id
                or hint.gui_process_creation_time_100ns
            )
            or bool(
                hint.gui_window_handle
                and hint.gui_process_id
                and hint.gui_process_creation_time_100ns
            )
        )
    )
