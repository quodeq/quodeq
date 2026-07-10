"""Command-line entry point: run / compare / markdown."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from quodeq_bench.compare import compare_reports
from quodeq_bench.matcher import match_case
from quodeq_bench.metrics import aggregate, count_kloc
from quodeq_bench.models import load_truth
from quodeq_bench.report import (
    average_reports,
    build_report,
    collect_meta,
    load_report,
    to_markdown,
    write_report,
)
from quodeq_bench.runner import RunConfig, RunError, replay_case, run_case

_ALL_DIMENSIONS = "security,reliability,maintainability,performance,flexibility,usability"


def _case_dirs(corpus: Path) -> list[Path]:
    return sorted(p.parent for p in corpus.glob("*/truth.json"))


def _run(args: argparse.Namespace) -> int:
    corpus = Path(args.corpus)
    cases = _case_dirs(corpus)
    if not cases:
        print(f"no cases found under {corpus}", file=sys.stderr)
        return 2
    cfg = RunConfig(
        provider=args.provider,
        model=args.model,
        dimensions=args.dimensions,
        time_limit=args.time_limit,
        quodeq_cmd=tuple(args.quodeq_cmd.split()),
    )
    repo_root = Path.cwd()
    rep_reports: list[dict] = []
    for rep in range(args.reps):
        matches, klocs = [], []
        for case_dir in cases:
            truth = load_truth(case_dir)
            try:
                if args.replay_root:
                    replay_dir = Path(args.replay_root) / case_dir.name
                    if not any(replay_dir.glob("*_evidence.jsonl")):
                        raise RunError(
                            f"{case_dir.name}: no recorded evidence under {replay_dir}"
                        )
                    findings = replay_case(replay_dir)
                else:
                    with tempfile.TemporaryDirectory() as tmp:
                        findings = run_case(case_dir, cfg, Path(tmp))
            except RunError as exc:
                print(f"ERRORED: {exc}", file=sys.stderr)
                meta = collect_meta(repo_root, args.provider, args.model, args.reps)
                write_report(
                    Path(args.out) / "report.json",
                    build_report(meta, {}, errored=True),
                )
                return 2
            matches.append(match_case(truth, findings))
            klocs.append(count_kloc(case_dir, truth.language))
            print(f"rep {rep + 1}/{args.reps} case {case_dir.name}: "
                  f"{len(findings)} findings", file=sys.stderr)
        metrics = aggregate(matches, klocs)
        meta = collect_meta(repo_root, args.provider, args.model, args.reps)
        rep_reports.append(build_report(meta, metrics))
    final = average_reports(rep_reports)
    write_report(Path(args.out) / "report.json", final)
    print(to_markdown(final))
    return 0


def _compare(args: argparse.Namespace) -> int:
    baseline = load_report(Path(args.baseline))
    candidate = load_report(Path(args.candidate))
    if candidate.get("errored"):
        print("candidate run errored (infrastructure failure)", file=sys.stderr)
        return 2
    if baseline.get("bootstrap"):
        print("baseline is bootstrap; gate not armed")
        return 0
    regressions = compare_reports(baseline, candidate, args.threshold)
    for r in regressions:
        print(f"REGRESSION {r.dimension}.{r.metric}: "
              f"{r.baseline} -> {r.candidate}")
    return 1 if regressions else 0


def _markdown(args: argparse.Namespace) -> int:
    print(to_markdown(load_report(Path(args.report))))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="quodeq_bench")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="run the corpus and write report.json")
    run_p.add_argument("--corpus", required=True)
    run_p.add_argument("--provider", required=True)
    run_p.add_argument("--model", required=True)
    run_p.add_argument("--dimensions", default=_ALL_DIMENSIONS)
    run_p.add_argument("--reps", type=int, default=1)
    run_p.add_argument("--time-limit", type=int, default=900)
    run_p.add_argument("--out", default="benchmarks/results/local")
    run_p.add_argument("--replay-root", default=None)
    run_p.add_argument("--quodeq-cmd", default="quodeq")
    run_p.set_defaults(func=_run)

    cmp_p = sub.add_parser("compare", help="compare candidate vs baseline")
    cmp_p.add_argument("baseline")
    cmp_p.add_argument("candidate")
    cmp_p.add_argument("--threshold", type=float, default=0.05)
    cmp_p.set_defaults(func=_compare)

    md_p = sub.add_parser("markdown", help="render a report as markdown")
    md_p.add_argument("report")
    md_p.set_defaults(func=_markdown)

    args = parser.parse_args(argv)
    return int(args.func(args))
