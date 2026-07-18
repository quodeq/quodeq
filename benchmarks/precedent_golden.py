"""Golden-set threshold calibration for semantic precedent matching (Phase B).

Dataset: benchmarks/data/precedent_golden.jsonl, one record per line:
  {"id": "d1", "kind": "dismissal",  "req": "...", "snippet": "..."}
  {"id": "p1", "kind": "paraphrase", "of": "d1", "req": "...", "snippet": "..."}
  {"id": "n1", "kind": "negative",   "req": "...", "snippet": "..."}
Paraphrases should match their dismissal; negatives should match nothing.
Include scope-level negatives (same file, different requirement).

Usage (needs a running Ollama with the embedding model pulled):
  uv run python benchmarks/precedent_golden.py
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Callable

_DEFAULT_DATA = Path(__file__).parent / "data" / "precedent_golden.jsonl"
_DEFAULT_THRESHOLDS = [round(0.70 + i * 0.01, 2) for i in range(26)]  # 0.70..0.95


def _unit(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec] if norm else vec


def _cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def sweep(
    records: list[dict[str, Any]],
    embed_record: Callable[[dict[str, Any]], list[float]],
    thresholds: list[float] = _DEFAULT_THRESHOLDS,
) -> list[dict[str, Any]]:
    """For each threshold: TP = paraphrase matches its dismissal's corpus,
    FP = negative matches any dismissal, FN = paraphrase fails to match."""
    dismissals = [r for r in records if r["kind"] == "dismissal"]
    candidates = [r for r in records if r["kind"] != "dismissal"]
    corpus = {d["id"]: _unit(embed_record(d)) for d in dismissals}

    scored: list[tuple[dict[str, Any], float]] = []
    for rec in candidates:
        vec = _unit(embed_record(rec))
        best = max((_cos(vec, v) for v in corpus.values()), default=-1.0)
        scored.append((rec, best))

    rows = []
    for thr in thresholds:
        tp = sum(1 for rec, s in scored if rec["kind"] == "paraphrase" and s >= thr)
        fn = sum(1 for rec, s in scored if rec["kind"] == "paraphrase" and s < thr)
        fp = sum(1 for rec, s in scored if rec["kind"] == "negative" and s >= thr)
        precision = tp / (tp + fp) if tp + fp else 1.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        rows.append({"threshold": thr, "tp": tp, "fp": fp, "fn": fn,
                     "precision": round(precision, 3), "recall": round(recall, 3)})
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=_DEFAULT_DATA)
    args = parser.parse_args(argv)
    if not args.data.is_file():
        print(f"No golden set at {args.data} — build it in Phase B (see docstring).")
        return 1

    from quodeq.context.precedent import precedent_text
    from quodeq.llm_bridge._embeddings import BATCH_TIMEOUT, embed_texts
    from quodeq.shared._env import get_embedding_base_url, get_embedding_model

    records = [
        json.loads(line)
        for line in args.data.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    model = get_embedding_model()
    base = get_embedding_base_url()
    texts = [precedent_text(r["req"], r["snippet"]) or "" for r in records]
    vectors = embed_texts(texts, model=model, base_url=base, timeout=BATCH_TIMEOUT)
    by_id = {r["id"]: v for r, v in zip(records, vectors)}

    rows = sweep(records, lambda rec: by_id[rec["id"]])
    print(f"model={model} records={len(records)}")
    print(f"{'thr':>5} {'tp':>4} {'fp':>4} {'fn':>4} {'precision':>10} {'recall':>7}")
    for row in rows:
        print(f"{row['threshold']:>5} {row['tp']:>4} {row['fp']:>4} "
              f"{row['fn']:>4} {row['precision']:>10} {row['recall']:>7}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
