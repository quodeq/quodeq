#!/usr/bin/env node
// Ratchet gate for copy-paste duplication (jscpd) in Python and UI sources.
//
// Duplication is what the self-eval keeps charging maintainability for: the
// same fragment edited in one copy and forgotten in the other. The fix is a
// shared helper (in `core/`, `shared/`, `utils/` or the feature's helper
// module), never a third copy.
//
// Detection is jscpd, configured once in `.jscpd.json` at the repo root
// (5 lines / 50 tokens, formats python+javascript+jsx, tests, snapshots,
// fixtures, node_modules and dist excluded). jscpd is a devDependency of
// this package, so it runs via `npx --no-install`; if it is missing the
// gate says how to install it instead of passing silently.
//
// This is a node port of the former tools/check_clones.py: that Python
// ratchet lived in the `test` CI job's tests/tools suite, which runs on
// three OSes with only `uv sync` (no node_modules), so `npx --no-install
// jscpd` always failed there. jscpd is a UI devDependency, so the gate
// belongs in the node-only `ui` CI job instead.
//
// Existing clones are grandfathered in tools/clones_baseline.json (a JSON
// array of span keys) so the gate runs green today while blocking NEW ones.
// Unlike the UI's other ratchets (magic/hygiene/a11y/fault, all driven by
// tools/ratchet.mjs), a clone's identity is a PAIR of files+spans, not
// something one file's violation count can capture: two files could keep
// the same combined count while a grandfathered clone is quietly swapped
// for a different new one between them, and the count-based baseline would
// never notice. So this keeps the same span-keyed set the Python version
// used (`fileA:start-end|fileB:start-end`, repo-relative, pair sorted)
// instead of ratchet.mjs's per-file-count shape.
//
// Entries are span-keyed, so editing above a grandfathered clone shifts its
// entry and the gate reports it as new. That is the intended prompt to
// extract the helper; regenerate only when the move is deliberate, because
// a blind --update can absorb a genuinely new clone from the same change.
//     npm run lint:clones:update
import { spawnSync } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const UI_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const REPO_ROOT = path.resolve(UI_ROOT, '..', '..', '..');
const CONFIG_PATH = path.join(REPO_ROOT, '.jscpd.json');
const BASELINE_PATH = path.join(UI_ROOT, 'tools', 'clones_baseline.json');
const REPORT_NAME = 'jscpd-report.json';

const INSTALL_HINT =
  'jscpd is not available. Install the UI dev dependencies first:\n' +
  '    cd src/quodeq/ui && npm install';

const HINT =
  'Extract a shared helper (core/, shared/, utils/ or the feature\'s helper ' +
  'module) instead of copy-pasting. Regenerate the baseline only with ' +
  'justification: npm run lint:clones:update';

// The baseline was burned to zero: every grandfathered clone is now a
// shared helper. NEVER raise this without a
// justification reviewed in the PR that raises it -- at zero, any new clone
// has to be extracted, not absorbed.
const TOTAL_CEILING = 0;

/** Map a jscpd file name (relative to *baseDir*) to a repo-relative one. */
function relative(name, baseDir, repoRoot) {
  const absolute = path.normalize(path.join(baseDir, name));
  return path.relative(repoRoot, absolute).split(path.sep).join('/');
}

function span(entry, baseDir, repoRoot) {
  return `${relative(entry.name, baseDir, repoRoot)}:${entry.start}-${entry.end}`;
}

/**
 * Turn a raw jscpd JSON report into sorted, de-duplicated clones.
 *
 * jscpd reports file names relative to the directory it ran in (*baseDir*);
 * keys are repo-relative and the pair is sorted so the same duplication
 * keys identically whichever copy jscpd lists first.
 */
export function parseReport(payload, baseDir, repoRoot) {
  const seen = new Map();
  for (const entry of payload.duplicates ?? []) {
    const first = span(entry.firstFile, baseDir, repoRoot);
    const second = span(entry.secondFile, baseDir, repoRoot);
    const key = [first, second].sort().join('|');
    if (!seen.has(key)) {
      seen.set(key, { key, fmt: String(entry.format ?? ''), lines: Number(entry.lines ?? 0) });
    }
  }
  return [...seen.keys()].sort().map((key) => seen.get(key));
}

/** One-line report of a clone, with its format and size. */
export function describe(clone) {
  return `${clone.key} (${clone.lines} lines, ${clone.fmt})`;
}

function jscpdArgs(outputDir) {
  return ['--no-install', 'jscpd', '--config', CONFIG_PATH, '--reporters', 'json', '--output', outputDir, '--silent'];
}

/** Run jscpd from this package and return its parsed JSON report. */
function runJscpd() {
  const outDir = mkdtempSync(path.join(tmpdir(), 'jscpd-'));
  try {
    const proc = spawnSync('npx', jscpdArgs(outDir), { cwd: UI_ROOT, encoding: 'utf8' });
    if (proc.error) {
      throw new Error(`${INSTALL_HINT}\n  (${proc.error.message})`);
    }
    const reportPath = path.join(outDir, REPORT_NAME);
    if (!existsSync(reportPath)) {
      const detail = (proc.stderr || proc.stdout || '').trim();
      throw new Error(`${INSTALL_HINT}\n  (jscpd wrote no report: ${detail})`);
    }
    try {
      return JSON.parse(readFileSync(reportPath, 'utf8'));
    } catch (e) {
      throw new Error(`unreadable jscpd report at ${reportPath}: ${e.message}`);
    }
  } finally {
    rmSync(outDir, { recursive: true, force: true });
  }
}

/** Return every clone in the current tree. */
export function scan() {
  return parseReport(runJscpd(), UI_ROOT, REPO_ROOT);
}

export function loadBaseline(baselinePath) {
  if (!existsSync(baselinePath)) return new Set();
  return new Set(JSON.parse(readFileSync(baselinePath, 'utf8')));
}

export function writeBaseline(baselinePath, keys) {
  const sorted = [...new Set(keys)].sort();
  writeFileSync(baselinePath, JSON.stringify(sorted, null, 2) + '\n', 'utf8');
  return sorted.length;
}

/**
 * Compare *clones* against the baseline at *baselinePath* (or rewrite it,
 * with `update: true`) and return `{ code, lines }`: the process exit code
 * and the messages to print (via console.log on success, console.error
 * otherwise). Kept separate from `main` so tests can drive it with a fixture
 * report instead of a real jscpd run.
 */
export function evaluateGate(clones, baselinePath, { update = false, ceiling = TOTAL_CEILING } = {}) {
  const keys = [...new Set(clones.map((c) => c.key))].sort();

  if (update) {
    const n = writeBaseline(baselinePath, keys);
    return { code: 0, lines: [`Wrote ${n} clone(s) to ${baselinePath}`] };
  }

  const baseline = loadBaseline(baselinePath);
  const byKey = new Map(clones.map((c) => [c.key, c]));
  const newKeys = keys.filter((k) => !baseline.has(k));
  const grandfathered = keys.length - newKeys.length;
  const overCeiling = baseline.size > ceiling;

  const lines = [];
  if (newKeys.length > 0) {
    lines.push(`Found ${newKeys.length} NEW clone violation(s) (${grandfathered} grandfathered):`, '');
    for (const k of newKeys) lines.push(`  ${describe(byKey.get(k))}`);
    lines.push('', HINT);
  }
  if (overCeiling) {
    lines.push(
      `Baseline grew to ${baseline.size} entries (ceiling ${ceiling}). Extract the new clone instead of ` +
        'grandfathering it; if growth is truly justified, raise TOTAL_CEILING in tools/check_clones.mjs ' +
        'in the same PR and explain why.',
    );
  }

  if (newKeys.length === 0 && !overCeiling) {
    return { code: 0, lines: [`OK: no new clone violations (${grandfathered} grandfathered).`] };
  }
  return { code: 1, lines };
}

/** Run the ratchet CLI: `check_clones.mjs [--update]`. */
export function main(argv = process.argv.slice(2)) {
  const update = argv.includes('--update');
  const unknown = argv.filter((a) => a !== '--update');
  if (unknown.length > 0) {
    console.error(`Unknown argument(s): ${unknown.join(' ')}. Usage: check_clones.mjs [--update]`);
    return 2;
  }

  let clones;
  try {
    clones = scan();
  } catch (e) {
    console.error(`error: ${e.message}`);
    return 2;
  }

  const { code, lines } = evaluateGate(clones, BASELINE_PATH, { update });
  for (const line of lines) (code === 0 ? console.log : console.error)(line);
  return code;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  process.exit(main());
}
