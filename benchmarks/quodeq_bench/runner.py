"""Materialize a corpus case and run quodeq over it (or replay recorded evidence)."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from quodeq_bench.evidence import Finding, find_evidence_dir, load_findings

_ALL_DIMENSIONS = "security,reliability,maintainability,performance,flexibility,usability"


class RunError(RuntimeError):
    """Infrastructure failure: quodeq did not produce usable evidence."""


@dataclass(frozen=True)
class RunConfig:
    provider: str
    model: str
    dimensions: str = _ALL_DIMENSIONS
    time_limit: int = 900
    n_subagents: int = 2
    quodeq_cmd: tuple[str, ...] = ("quodeq",)


def run_case(case_dir: Path, cfg: RunConfig, workdir: Path) -> list[Finding]:
    repo = workdir / "repo"
    out = workdir / "out"
    if repo.exists():
        shutil.rmtree(repo)
    shutil.copytree(case_dir, repo, ignore=shutil.ignore_patterns("truth.json"))
    out.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    env["AI_PROVIDER"] = cfg.provider
    env["AI_MODEL"] = cfg.model
    cmd = [
        *cfg.quodeq_cmd,
        "evaluate",
        str(repo),
        "-d",
        cfg.dimensions,
        "--clean-scan",
        "-o",
        str(out),
        "--time-limit",
        str(cfg.time_limit),
        "--n-subagents",
        str(cfg.n_subagents),
    ]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "")[-2000:]
        raise RunError(
            f"{case_dir.name}: quodeq exit code {result.returncode}\n{tail}"
        )
    evidence = find_evidence_dir(out)
    if evidence is None:
        raise RunError(f"{case_dir.name}: no evidence directory produced")
    findings, _errored = load_findings(evidence)
    return findings


def replay_case(evidence_dir: Path) -> list[Finding]:
    findings, _errored = load_findings(evidence_dir)
    return findings
