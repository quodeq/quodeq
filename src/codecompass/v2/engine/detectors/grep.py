from __future__ import annotations
import configparser
import subprocess
from pathlib import Path

from codecompass.v2.engine.detectors.base import DetectorBase
from codecompass.v2.engine.finding import Finding


class GrepDetector(DetectorBase):
    def run(self, src: Path, config: dict) -> list[Finding]:
        rules_file = Path(config["rules_file"])
        parser = configparser.ConfigParser()
        parser.read(rules_file)

        findings: list[Finding] = []
        for section in parser.sections():
            rule = parser[section]
            command = rule.get("command", "").replace("{src}", str(src))
            cwe_raw = rule.get("cwe")
            cwe = int(cwe_raw) if cwe_raw and cwe_raw.isdigit() else None

            try:
                result = subprocess.run(
                    command, shell=True, capture_output=True, text=True, timeout=30
                )
                for line in result.stdout.strip().splitlines():
                    if not line.strip():
                        continue
                    file_part, _, snippet = line.partition(":")
                    findings.append(Finding(
                        rule=section,
                        label=rule.get("label", section),
                        file=file_part.strip(),
                        dimension=rule.get("dimension", "maintainability"),
                        detector="grep",
                        cwe=cwe,
                        snippet=snippet.strip() or None,
                    ))
            except subprocess.TimeoutExpired:
                continue

        return findings
