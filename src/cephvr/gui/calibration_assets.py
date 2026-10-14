"""Remove superseded content-addressed calibration assets from a Protocol Assets folder.

Every submitted calibration writes ``calibration/reference_<face>_<sha256>.json``; old
ones accumulate. A file is kept when a saved configuration still references it or when
it is among the newest few for its face. Nothing is deleted without ``--apply``.
"""

import argparse
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

_NAME = re.compile(r"^reference_(front|left|right|bottom)_[0-9a-f]{64}\.json$")


@dataclass(frozen=True)
class PruneReport:
    kept: tuple[Path, ...]
    removed: tuple[Path, ...]


def referenced_names(documents: Iterable[Path]) -> frozenset[str]:
    """Reference-profile file names mentioned anywhere in the given saved documents."""
    found: set[str] = set()
    pattern = re.compile(r"reference_(?:front|left|right|bottom)_[0-9a-f]{64}\.json")
    for document in documents:
        if document.is_file():
            found.update(pattern.findall(document.read_text(encoding="utf-8")))
    return frozenset(found)


def prune_reference_profiles(
    root: Path,
    referenced: frozenset[str],
    *,
    keep_newest: int = 3,
    apply: bool = False,
) -> PruneReport:
    """Keep referenced files and the newest ``keep_newest`` per face; delete the rest."""
    folder = root / "calibration"
    if not folder.is_dir():
        raise ValueError(f"No calibration folder in {root}")
    by_face: dict[str, list[Path]] = {}
    for path in folder.iterdir():
        match = _NAME.match(path.name)
        if match and path.is_file() and not path.is_symlink():
            by_face.setdefault(match.group(1), []).append(path)
    kept: list[Path] = []
    removed: list[Path] = []
    for paths in by_face.values():
        paths.sort(key=lambda p: (p.stat().st_mtime_ns, p.name), reverse=True)
        for index, path in enumerate(paths):
            (
                kept if path.name in referenced or index < keep_newest else removed
            ).append(path)
    if apply:
        for path in removed:
            path.unlink()
    return PruneReport(tuple(sorted(kept)), tuple(sorted(removed)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assets", type=Path, help="Protocol Assets folder")
    parser.add_argument(
        "--saved",
        type=Path,
        nargs="+",
        default=[Path("config/runtime_gui.json"), Path("config/review_draft.json")],
        help="saved GUI/projector JSON files whose references must be kept",
    )
    parser.add_argument("--keep-newest", type=int, default=3)
    parser.add_argument("--apply", action="store_true", help="delete (default: list)")
    args = parser.parse_args()
    report = prune_reference_profiles(
        args.assets,
        referenced_names(args.saved),
        keep_newest=args.keep_newest,
        apply=args.apply,
    )
    verb = "Removed" if args.apply else "Would remove"
    for path in report.removed:
        print(f"{verb}: {path}")
    print(f"{len(report.kept)} kept, {len(report.removed)} {verb.lower()}.")
    if not args.apply and report.removed:
        print("Run again with --apply to delete them.")


if __name__ == "__main__":
    main()
