from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path

from codecompass.v2.engine.finding import Finding


class DetectorBase(ABC):
    @abstractmethod
    def run(self, src: Path, config: dict) -> list[Finding]:
        """Run detection against src directory. Return list of Findings."""
        ...
