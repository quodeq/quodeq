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

To add a case: copy the structure of an existing one (source files +
`truth.json` with `language`, `exhaustive`, `clean_files`, and one label
per planted issue — each label needs `file`, `line`, an `anchor`
substring that appears on that line, `dimension`, `severity`, and at
least one of `cwes`/`reqs`). The integrity test
(`tests/benchmarks/test_corpus_integrity.py`) validates labels
automatically.
