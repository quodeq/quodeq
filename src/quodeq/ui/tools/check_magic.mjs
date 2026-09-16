#!/usr/bin/env node
// Ratchet gate for magic numbers in production UI code.
//
// Existing violations are grandfathered per-file in tools/magic_baseline.json
// so the gate runs green today while blocking NEW ones. The baseline only
// shrinks: when a file's count drops, lock the progress in with:
//     npm run lint:magic:update
//
// Same shape as tools/check_hygiene.mjs (per-file counts, not line keys, so
// unrelated edits don't churn the baseline), reading eslint.magic.config.js
// with inline config disabled so an eslint-disable comment cannot waive the rule.
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { ESLint } from 'eslint';

const UI_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const BASELINE_PATH = path.join(UI_ROOT, 'tools', 'magic_baseline.json');
const CONFIG_PATH = path.join(UI_ROOT, 'eslint.magic.config.js');

const RATCHET_RULES = new Set(['no-magic-numbers']);

// Revise DOWNWARD as burn-down tasks land; NEVER raise without a
// justification reviewed in the PR that raises it.
const TOTAL_CEILING = 514; // set to the total printed by --update; lower it as entries burn down

async function collectCounts() {
  const eslint = new ESLint({
    cwd: UI_ROOT,
    overrideConfigFile: CONFIG_PATH,
    allowInlineConfig: false,
  });
  const results = await eslint.lintFiles(['src/**/*.jsx', 'src/**/*.js']);
  const counts = {};
  for (const r of results) {
    const fatal = r.messages.filter((m) => m.fatal);
    if (fatal.length > 0) {
      throw new Error(`lint failed on ${r.filePath}: ${fatal[0].message}`);
    }
    const n = r.messages.filter((m) => RATCHET_RULES.has(m.ruleId)).length;
    if (n > 0) {
      counts[path.relative(UI_ROOT, r.filePath).split(path.sep).join('/')] = n;
    }
  }
  return counts;
}

function loadBaseline() {
  if (!existsSync(BASELINE_PATH)) return {};
  return JSON.parse(readFileSync(BASELINE_PATH, 'utf8'));
}

function writeBaseline(counts) {
  const sorted = Object.fromEntries(
    Object.entries(counts).sort(([a], [b]) => (a < b ? -1 : 1)),
  );
  writeFileSync(BASELINE_PATH, JSON.stringify(sorted, null, 2) + '\n', 'utf8');
  return sorted;
}

function total(counts) {
  return Object.values(counts).reduce((a, b) => a + b, 0);
}

async function main() {
  const args = process.argv.slice(2);
  const update = args.includes('--update');
  const unknown = args.filter((a) => a !== '--update');
  if (unknown.length > 0) {
    console.error(`Unknown argument(s): ${unknown.join(' ')}. Usage: check_magic.mjs [--update]`);
    return 2;
  }

  const counts = await collectCounts();

  if (update) {
    const written = writeBaseline(counts);
    console.log(
      `Wrote baseline for ${Object.keys(written).length} file(s), ${total(written)} violation(s), to ${path.relative(UI_ROOT, BASELINE_PATH)}`,
    );
    return 0;
  }

  const baseline = loadBaseline();
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
  const baselineTotal = total(baseline);
  const overCeiling = baselineTotal > TOTAL_CEILING;

  if (grew.length > 0) {
    console.error(`Found NEW magic number(s) in ${grew.length} file(s):\n`);
    for (const { file, count, allowed } of grew) {
      console.error(`  ${file}: ${count} violation(s), baseline allows ${allowed}`);
    }
    console.error(
      '\nName the literal (`const UPPER_SNAKE = value; // why`) in the module, the feature constants module, or src/constants.js. Run `npx eslint --no-inline-config -c eslint.magic.config.js <file>` for details.',
    );
  }
  if (shrank.length > 0) {
    console.error(`Baseline is stale for ${shrank.length} file(s) (fewer violations than allowed):\n`);
    for (const { file, count, allowed } of shrank) {
      console.error(`  ${file}: ${count} violation(s), baseline allows ${allowed}`);
    }
    console.error('\nLock the progress in: npm run lint:magic:update (commit the baseline change).');
  }
  if (overCeiling) {
    console.error(
      `Baseline total grew to ${baselineTotal} (ceiling ${TOTAL_CEILING}). Fix the new violation instead of grandfathering it; if growth is truly justified, raise TOTAL_CEILING in tools/check_magic.mjs in the same PR and explain why.`,
    );
  }

  if (grew.length === 0 && shrank.length === 0 && !overCeiling) {
    console.log(
      `OK: no new magic numbers (${total(counts)} grandfathered across ${Object.keys(counts).length} files).`,
    );
    return 0;
  }
  return 1;
}

main().then(
  (code) => process.exit(code),
  (err) => {
    console.error(err.message || err);
    process.exit(2);
  },
);
