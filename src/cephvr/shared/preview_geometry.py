"""Remember operator placement independently from automatic GUI translation."""

Geometry = tuple[int, int, int, int]


class PreviewGeometryGuard:
    """A manual move or resize opts this window out until close/reopen or an explicit reset."""

    def __init__(self) -> None:
        self.last: Geometry | None = None
        self.manual = False
        self.revision: int | None = None

    def observe(self, geometry: Geometry, revision: int | None = None) -> bool:
        if revision is not None:
            self.manual |= self.revision is not None and revision != self.revision
        elif self.last is not None and any(
            abs(a - b) > 2 for a, b in zip(self.last, geometry, strict=True)
        ):
            self.manual = True
        return not self.manual

    def arranged(self, geometry: Geometry, revision: int | None = None) -> None:
        self.last = geometry
        self.revision = revision
