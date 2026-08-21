from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Cluster:
    words: list[tuple[str, int]] = field(default_factory=list)

    @property
    def representative(self) -> str:
        return self.words[0][0]

    @property
    def total_frequency(self) -> int:
        return sum(f for _, f in self.words)
