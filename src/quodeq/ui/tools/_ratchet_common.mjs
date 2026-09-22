/**
 * Shared plumbing for the UI's per-file ratchet gates: tools/ratchet.mjs (the
 * runner behind check_hygiene/check_magic/check_a11y/check_fault) and
 * tools/check_strings.mjs, which keeps its own main because it also validates
 * the string catalog.
 *
 * All of them do the same four things: resolve the UI root, lint
 * `src/**` with eslint and count the rules they care about per file, read and
 * rewrite a per-file-counts JSON baseline, and compare today's counts against
 * it. Counts, not line keys, so unrelated edits don't churn the baseline.
 */
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { ESLint } from 'eslint';

/** Absolute path of src/quodeq/ui, the cwd every gate lints from. */
export const UI_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

/** Everything the gates lint: the UI's JSX and plain-JS sources. */
const LINT_GLOBS = ['src/**/*.jsx', 'src/**/*.js'];

/**
 * Lint the UI sources and count, per file, the messages whose rule id is in
 * *rules*. Files with zero are omitted. A fatal (parse) error is raised
 * rather than counted, so a broken file can never look clean.
 *
 * Stray messages from other sources (e.g. an eslint-disable comment naming a
 * rule the config doesn't define) are ignored: only the gate's own rules count.
 *
 * @param {Set<string>|Iterable<string>} rules eslint rule ids that count
 * @param {object} [eslintOptions] extra ESLint constructor options (config file, inline-config policy)
 * @returns {Promise<Record<string, number>>} repo-relative file -> violation count
 */
export async function collectCounts(rules, eslintOptions = {}) {
  const ruleSet = rules instanceof Set ? rules : new Set(rules);
  const eslint = new ESLint({ cwd: UI_ROOT, ...eslintOptions });
  const results = await eslint.lintFiles(LINT_GLOBS);
  const counts = {};
  for (const r of results) {
    const fatal = r.messages.filter((m) => m.fatal);
    if (fatal.length > 0) {
      throw new Error(`lint failed on ${r.filePath}: ${fatal[0].message}`);
    }
    const n = r.messages.filter((m) => ruleSet.has(m.ruleId)).length;
    if (n > 0) {
      counts[path.relative(UI_ROOT, r.filePath).split(path.sep).join('/')] = n;
    }
  }
  return counts;
}

/**
 * Read a per-file-counts baseline; a missing file means "nothing grandfathered".
 *
 * @param {string} baselinePath
 * @returns {Record<string, number>}
 */
export function loadBaseline(baselinePath) {
  if (!existsSync(baselinePath)) return {};
  return JSON.parse(readFileSync(baselinePath, 'utf8'));
}

/**
 * Rewrite *baselinePath* with *counts*, sorted by file so the diff is stable.
 *
 * @param {string} baselinePath
 * @param {Record<string, number>} counts
 * @returns {Record<string, number>} what was written
 */
export function writeBaseline(baselinePath, counts) {
  const sorted = Object.fromEntries(
    Object.entries(counts).sort(([a], [b]) => (a < b ? -1 : 1)),
  );
  writeFileSync(baselinePath, JSON.stringify(sorted, null, 2) + '\n', 'utf8');
  return sorted;
}

/**
 * Sum a per-file counts map.
 *
 * @param {Record<string, number>} counts
 * @returns {number}
 */
export function total(counts) {
  return Object.values(counts).reduce((a, b) => a + b, 0);
}

/**
 * Compare today's *counts* against *baseline*.
 *
 * `grew` is the gate failure (a file has more violations than it is allowed);
 * `shrank` is the stale-baseline nudge, and covers files that dropped to zero
 * or disappeared entirely.
 *
 * @param {Record<string, number>} counts
 * @param {Record<string, number>} baseline
 * @returns {{grew: Array<{file: string, count: number, allowed: number}>,
 *            shrank: Array<{file: string, count: number, allowed: number}>}}
 */
export function diffCounts(counts, baseline) {
  const grew = [];
  const shrank = [];
  for (const [file, count] of Object.entries(counts)) {
    const allowed = baseline[file] ?? 0;
    if (count > allowed) grew.push({ file, count, allowed });
    else if (count < allowed) shrank.push({ file, count, allowed });
  }
  for (const [file, allowed] of Object.entries(baseline)) {
    if (!(file in counts)) shrank.push({ file, count: 0, allowed });
  }
  return { grew, shrank };
}

/**
 * Parse a gate's argv. Returns `{ update }`, or `{ error }` with the usage
 * message when an unknown argument is present.
 *
 * @param {string[]} args
 * @param {string} script wrapper basename under tools/, for the usage line
 * @returns {{update: boolean, error?: string}}
 */
export function parseGateArgs(args, script) {
  const unknown = args.filter((a) => a !== '--update');
  if (unknown.length > 0) {
    return { update: false, error: `Unknown argument(s): ${unknown.join(' ')}. Usage: ${script} [--update]` };
  }
  return { update: args.includes('--update') };
}
