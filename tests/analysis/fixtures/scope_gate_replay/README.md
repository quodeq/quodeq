# Scope-gate replay fixture (TES-01)

Reduced `security.json` from a real self-scan, replayed by
`../../mcp/test_scope_gate_replay.py` against `apply_scope_gate` /
`apply_provenance_gate`. Mirrors `tests/analysis/fixtures/provenance_gate/`:
a synthetic unit suite proves each gate rule fires in isolation; this
fixture proves the rules against real model output, the same way
`test_scope_gate_replay.py`'s module docstring describes.

## Provenance

- Project: `d33f1fd0-d685-4c3c-97f5-9ae26a1b3723` (this repo's own self-scan,
  local to the machine that generated it — evaluation data outside the repo,
  never committed as a whole run).
- Run: `959ea2fe-6906-4119-86f3-5a86932d2354`
- Source: `~/.quodeq/evaluations/d33f1fd0-d685-4c3c-97f5-9ae26a1b3723/959ea2fe-6906-4119-86f3-5a86932d2354/evaluation/security.json`
- Run date: 2026-08-29T08:02:27+00:00 (security dimension; the overall run
  later failed on a different dimension with `failure_streak` — the security
  dimension itself finished cleanly, `exitReason: null`, 91.3% coverage).
- Selected as the newest local run under this project with a `security.json`
  present, by `status.json` mtime, among the runs on this machine at the time
  Group V (TES-03 sweep) was implemented. The original pinned run
  (`3a19b93f-1e01-428a-9d38-fea8e8929e63`) no longer exists locally.

## How it was reduced

Every `violations[]` row was reduced to the 5 fields the replay test reads
(`severity`, `req`, `title`, `reason`, `file`); only `major`/`critical` rows
were kept (10 major, 0 critical — this run's `security.json` had no critical
findings). Scrubbed for absolute home paths before committing (none were
present in the retained fields — every `file` value was already
repo-relative).

## Known limitation

This run's findings do not trigger any `scope_gate` demotion (no
`sourceless_path` / `cross_principal` hits) and it carries zero criticals, so
`test_replay_chains_provenance_then_scope_on_criticals` exercises an empty
loop. The replay test still holds real coverage value for
`test_replay_is_a_no_op_under_the_conservative_default` (still exercises 10
real major findings against the conservative trust model) and for future
re-generation: the next time this fixture is regenerated from a richer local
run, whichever gates fire will show up in the recomputed counts. Re-run this
script against the newest local run to regenerate:

```python
import json
from quodeq.analysis.mcp.provenance_gate import apply_provenance_gate
from quodeq.analysis.mcp.scope_gate import apply_scope_gate
from quodeq.context.trust_model import CONSERVATIVE, TrustModel

LOCAL = TrustModel(multi_tenant=False, network_exposure="loopback")
security = json.load(open("<path-to-security.json>"))
reduced = [
    {"severity": v["severity"], "req": v.get("req"), "title": v["title"],
     "reason": v["reason"], "file": v["file"]}
    for v in security["violations"] if v["severity"] in ("major", "critical")
]
json.dump({"violations": reduced}, open("security_findings.json", "w"), indent=2)
```
