"""Remember operator placement independently from automatic GUI translation."""

Geometry = tuple[int, int, int, int]


class PreviewGeometryGuard:
    """A manual move or resize opts this window out until close/reopen or an explicit reset."""

    def __init__(self) -> None:
        self.last: Geometry | None = None
        self.manual = False

    def observe(self, geometry: Geometry) -> bool:
        if self.last is not None and any(
            abs(a - b) > 2 for a, b in zip(self.last, geometry, strict=True)
        ):
            self.manual = True
        return not self.manual

    def arranged(self, geometry: Geometry) -> None:
        self.last = geometry
