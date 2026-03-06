import pytest

pytestmark = pytest.mark.skip(reason="detector/judge code removed in PR2")

from pathlib import Path
from codecompass.v2.engine.detectors.base import DetectorBase
from codecompass.v2.engine.finding import Finding


class ConcreteDetector(DetectorBase):
    def run(self, src: Path, config: dict) -> list[Finding]:
        return [Finding(rule="test", label="Test", file="a.py",
                        dimension="maintainability", detector="test")]


def test_detector_returns_findings():
    d = ConcreteDetector()
    findings = d.run(Path("."), {})
    assert len(findings) == 1
    assert isinstance(findings[0], Finding)


def test_abstract_detector_cannot_be_instantiated():
    import pytest
    with pytest.raises(TypeError):
        DetectorBase()
