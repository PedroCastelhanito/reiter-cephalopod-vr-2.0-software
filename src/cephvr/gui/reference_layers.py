"""Blank reference layers remain local until a stimulus family is selected."""

from dataclasses import dataclass, field


@dataclass
class ReferenceLayers:
    order: list[str] = field(default_factory=list)
    blanks: set[str] = field(default_factory=set)
    selected: str = ""
    counter: int = 0

    def sync(self, identities: list[str]) -> None:
        """Refresh canonical order while preserving locally inserted empty slots."""
        remaining = iter(identities)
        self.order = [
            key if key in self.blanks else next(remaining, "") for key in self.order
        ]
        self.order = [key for key in self.order if key] + list(remaining)
        if self.selected not in self.order:
            self.selected = next(iter(self.order), "")

    def add(self) -> None:
        self.counter += 1
        key = f"@blank_{self.counter}"
        self.order.append(key)
        self.blanks.add(key)
        self.selected = key

    def fill(self, identity: str, previous: str = "") -> None:
        if self.selected in self.blanks:
            index = self.order.index(self.selected)
            self.blanks.remove(self.selected)
            self.order[index] = identity
            self.selected = identity
        elif previous in self.order:
            self.order[self.order.index(previous)] = identity
            self.selected = identity

    def remove_blank(self) -> bool:
        if self.selected not in self.blanks:
            return False
        self.blanks.remove(self.selected)
        self.order.remove(self.selected)
        self.selected = next(iter(self.order), "")
        return True
