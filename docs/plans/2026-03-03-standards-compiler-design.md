# Standards Compiler & Practices Resolver — Design

## Problem

Three standards sources (ISO 25010, CISQ, ASVS) reference CWEs but are disconnected:
- ISO 25010 has sub-characteristics (principles) with requirements, each having CWE arrays
- CISQ has flat CWE lists with `{id, name, requirement}` — no principle grouping
- ASVS has its own requirement IDs with CWE arrays — security only

The evaluator practices reference CWEs as bare integers with no link to principles or
standards. The scoring pipeline groups by practice ID, not by principle. The evaluation
output reports "py-005: Keep source files under 300 lines" instead of "Analyzability: 4/10".

25 CISQ CWEs have no corresponding ISO 25010 requirement (orphans).

## Solution

Two scripts + one enrichment step:

1. **Enrich ISO 25010 files** — add the 25 orphan CISQ CWEs to the correct principles
2. **`tools/compile_standards.py`** — merge all standards into compiled dimension files
3. **`tools/resolve_practices.py`** — enrich per-language practices with principle + standards refs

## Architecture

```
standards/iso25010/*.json  ──┐
standards/cisq/*.json      ──┼──► compile_standards.py ──► standards/compiled/*.json
standards/asvs/level1.json ──┘         │
        cwe2 library ─────────────────┘

standards/compiled/*.json  ──┐
evaluators/*/practices.json ─┼──► resolve_practices.py ──► evaluators/*/practices.resolved.json
                             │
```

## Data Structures

### Compiled Standards (`standards/compiled/<dimension>.json`)

ISO 25010 is the structural backbone (provides principles). CISQ and ASVS attach as refs.

```json
{
  "id": "maintainability",
  "name": "Maintainability",
  "sources": ["iso25010", "cisq"],
  "principles": [
    {
      "name": "Modularity",
      "cwes": [
        {
          "id": 1121,
          "name": "Excessive McCabe Cyclomatic Complexity",
          "refs": [
            { "source": "iso25010", "ref": "M-MOD-1", "title": "Cyclomatic complexity MUST be ≤10 per function" },
            { "source": "cisq", "title": "Function cyclomatic complexity MUST be ≤10" }
          ]
        }
      ]
    }
  ]
}
```

Ref rules:
- ISO 25010 refs have `source`, `ref`, `title`
- CISQ refs have `source`, `title` (no `ref` — the ref IS the CWE id)
- ASVS refs have `source`, `ref`, `section`, `title` (security dimension only)
- CWE `name` comes from the `cwe2` Python library (canonical MITRE names)
- A CWE may appear under multiple principles (when the real standard says so)

### Resolved Practices (`evaluators/<lang>/knowledge/practices.resolved.json`)

```json
{
  "runtime": "python",
  "version": "1.0.0",
  "practices": [
    {
      "id": "py-005",
      "title": "Keep source files under 300 lines",
      "dimension": "maintainability",
      "principle": "Analyzability",
      "cwe": {
        "id": 1080,
        "name": "Source File With Excessive Lines of Code"
      },
      "standards": [
        { "source": "iso25010", "ref": "M-ANA-1", "title": "Source files MUST NOT exceed 300 lines" },
        { "source": "cisq", "title": "Source files MUST NOT exceed language-appropriate line limits" }
      ],
      "severity": "medium",
      "bad": "...",
      "good": "...",
      "explanation": "..."
    }
  ]
}
```

### Input Practices (manual change needed)

Each practice in `evaluators/<lang>/knowledge/practices.json` needs a new `principle` field:

```json
{
  "id": "py-005",
  "title": "Keep source files under 300 lines",
  "dimension": "maintainability",
  "principle": "Analyzability",
  "cwe": 1080,
  ...
}
```

The `principle` must match a sub-characteristic name from the dimension's ISO 25010 file.

## Severity Vocabulary

Practices use 4-level: `critical`, `high`, `medium`, `low`.
Scoring engine uses 3-level: `critical`, `major`, `minor`.

The normalization mapping lives in the scoring layer (already implemented):
- `high` → `critical`
- `medium` → `major`
- `low` → `minor`

Practices and resolved files keep the 4-level vocabulary.

## Script Behaviors

### `tools/compile_standards.py`

Input: `standards/iso25010/*.json`, `standards/cisq/*.json`, `standards/asvs/level1.json`
Output: `standards/compiled/<dimension>.json` (one per dimension)
Dependency: `cwe2` Python library

Steps:
1. For each ISO 25010 dimension file, iterate sub-characteristics (principles)
2. For each CWE in each requirement, look up canonical name via `cwe2`
3. Attach CISQ refs for matching CWEs (same dimension)
4. For security dimension only: attach ASVS refs for overlapping CWEs
5. Write compiled file

Validation/gap reporting (`--gaps` flag):
- CWEs in CISQ with no ISO 25010 principle → "orphan: CWE-XXXX not in any principle"
- CWEs in ISO 25010 with no CISQ entry → "iso-only: CWE-XXXX has no CISQ backing"
- ASVS CWEs with no ISO/CISQ match → "asvs-only: CWE-XXXX (skipped)"

### `tools/resolve_practices.py`

Input: `evaluators/<lang>/knowledge/practices.json`, `standards/compiled/*.json`
Output: `evaluators/<lang>/knowledge/practices.resolved.json`

Steps:
1. Load compiled standards for the practice's dimension
2. Find the CWE under the practice's declared principle
3. Copy refs as `standards`, enrich `cwe` to `{id, name}`
4. If CWE exists under a different principle than declared → warning
5. If CWE not found in compiled standards at all → warning
6. Write resolved file

Flags:
- `--lang python` — resolve one language
- `--all` — resolve all evaluators
- `--validate` — check only, don't write (for CI)

## Orphan CWE Assignments

Before first compile, enrich ISO 25010 files with these 25 CISQ orphans:

### Maintainability

| CWE | Name | Principle |
|-----|------|-----------|
| 1064 | Excessive Number of Parameters | Modularity |
| 1048 | Large Number of Outward Calls | Modularity |
| 1074 | Excessively Deep Inheritance | Modularity |
| 1045 | Parent/Child Virtual Destructor Mismatch | Modularity |
| 1054 | Invocation at Unnecessarily Deep Horizontal Layer | Modularity |
| 1090 | Method from Different Trust Level | Modularity |
| 1075 | Unconditional Control Flow Transfer out of Nested Blocks | Analyzability |
| 1095 | Loop Condition Update within Loop Body | Analyzability |
| 1085 | Excessive Volume of Commented-out Code | Modifiability |

### Security

| CWE | Name | Principle |
|-----|------|-----------|
| 259 | Use of Hard-coded Password | Confidentiality |
| 611 | XML External Entity Reference | Integrity |
| 918 | Server-Side Request Forgery | Authenticity |

### Reliability

| CWE | Name | Principle |
|-----|------|-----------|
| 252 | Unchecked Return Value | Fault Tolerance |
| 396 | Catch for Generic Exception | Fault Tolerance |
| 397 | Throws for Generic Exception | Fault Tolerance |
| 754 | Improper Check for Unusual Conditions | Fault Tolerance |
| 691 | Insufficient Control Flow Management | Fault Tolerance |
| 674 | Uncontrolled Recursion | Fault Tolerance |
| 835 | Loop with Unreachable Exit Condition | Fault Tolerance |

### Performance

| CWE | Name | Principle |
|-----|------|-----------|
| 1046 | String Concatenation in Loops | Time Behaviour |
| 1049 | Excessive Data Query Operations in Large Table | Time Behaviour |
| 1067 | Excessive Sequential Searches | Time Behaviour |
| 405 | Asymmetric Resource Consumption (Amplification) | Resource Utilisation |
| 770 | Allocation Without Limits or Throttling | Resource Utilisation |
| 1050 | Excessive Resource Consumption within a Loop | Resource Utilisation |

## Pipeline Integration (future)

After the compiler and resolver are working:
1. Update `practices_schema.json` to accept `principle` field
2. Update `context_builder.py` to include principle in LLM prompts
3. Update `judge.py` / `_assemble_evidence` to group by principle
4. Update scoring to report at principle level
5. Update dashboard to display principle-level scores

These are separate tasks — this design covers only the data compilation layer.

## Dimensions Covered

| Dimension | ISO 25010 | CISQ | ASVS | Practices exist |
|-----------|-----------|------|------|-----------------|
| Maintainability | yes | yes | no | yes |
| Security | yes | yes | overlap only | yes |
| Reliability | yes | yes | no | yes |
| Performance | yes | yes | no | yes |
| Usability | yes | no | no | no |
| Flexibility | yes | no | no | no |

Usability and Flexibility compile with ISO 25010 as the only source. Practices for
these dimensions can be added incrementally.
