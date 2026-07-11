# Ground-truth corpus — INTENTIONALLY VULNERABLE FIXTURES

Every violation in these files is planted on purpose and labeled in the
case's `truth.json`. They are the answer key for measuring quodeq's
finding accuracy (precision/recall). Nothing here is imported, executed,
or shipped in the wheel.

- Secret-looking strings (API keys, passwords) are fabricated examples,
  not real credentials.
- Security scanners flagging these files are working as intended — the
  findings are the dataset, like OWASP Benchmark or Juliet.
- The directory is hidden (`.corpus`) so quodeq's own nightly
  self-evaluation skips it (the manifest walker ignores dot-directories);
  do NOT rename it to a visible path or the planted bugs will sink
  quodeq's own dashboard grades.

Add new cases per the format in
`docs/superpowers/specs/2026-07-10-accuracy-benchmark-harness-design.md`;
the integrity test (`tests/benchmarks/test_corpus_integrity.py`)
validates labels automatically.
