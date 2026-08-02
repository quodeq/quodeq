#!/usr/bin/env node
// Ratchet gate for hardcoded user-visible strings in the web UI.
//
// Existing literals are grandfathered per-file in tools/strings_baseline.json
// so the gate runs green today while blocking NEW hardcoded strings. The
// baseline only shrinks: when a file's literal count drops (strings moved to
// the catalog, or the file deleted), lock the progress in with:
//     npm run lint:strings:update
//
// Same pattern as tools/check_imports.py at the repo root, but counts per
// file instead of line-keyed entries so unrelated edits don't churn it.
//
// Also validates the catalog itself: no em-dashes in user-facing strings.
import { readFileSync, readdirSync, writeFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { ESLint } from 'eslint';

const UI_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const BASELINE_PATH = path.join(UI_ROOT, 'tools', 'strings_baseline.json');
const CATALOG_PATH = path.join(UI_ROOT, 'src', 'strings', 'en.json');

async function collectCounts() {
  const eslint = new ESLint({ cwd: UI_ROOT });
  const results = await eslint.lintFiles(['src/**/*.jsx']);
  const counts = {};
  for (const r of results) {
    const fatal = r.messages.filter((m) => m.fatal);
    if (fatal.length > 0) {
      throw new Error(`lint failed on ${r.filePath}: ${fatal[0].message}`);
    }
    // Count only the ratchet rule itself. Stray messages from other sources
    // (e.g. an eslint-disable comment naming a rule this single-rule config
    // doesn't define) must not masquerade as hardcoded strings.
    const n = r.messages.filter((m) => m.ruleId === 'react/jsx-no-literals').length;
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
  return Object.keys(sorted).length;
}

function checkCatalog() {
  const catalog = JSON.parse(readFileSync(CATALOG_PATH, 'utf8'));
  const offenders = Object.entries(catalog).filter(([, v]) => /—/.test(v));
  for (const [key] of offenders) {
    console.error(`em-dash in user-facing string: "${key}" (use a period or comma instead)`);
  }
  return offenders.length === 0;
}

// t('some.key') with no matching catalog entry renders the key itself, so the
// UI silently shows "settings.needModelBeforeEval" where a sentence belongs.
// The jsx-no-literals ratchet cannot see this (there is no literal left), and
// tests only catch it where they assert on the exact copy -- so check it here.
const T_CALL = /\bt(?:Rich)?\(\s*'([a-zA-Z0-9_.]+)'/g;

function sourceFiles(dir, out = []) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) sourceFiles(p, out);
    else if (/\.jsx?$/.test(entry.name) && !/\.test\.jsx?$/.test(entry.name)) out.push(p);
  }
  return out;
}

function checkKeysResolve() {
  const catalog = JSON.parse(readFileSync(CATALOG_PATH, 'utf8'));
  const missing = [];
  for (const file of sourceFiles(path.join(UI_ROOT, 'src'))) {
    const src = readFileSync(file, 'utf8');
    for (const m of src.matchAll(T_CALL)) {
      if (!(m[1] in catalog)) missing.push([m[1], path.relative(UI_ROOT, file)]);
    }
  }
  for (const [key, file] of missing) {
    console.error(`missing catalog key: "${key}" used in ${file} (it would render as the key itself)`);
  }
  return missing.length === 0;
}

async function main() {
  const args = process.argv.slice(2);
  const update = args.includes('--update');
  const unknown = args.filter((a) => a !== '--update');
  if (unknown.length > 0) {
    console.error(`Unknown argument(s): ${unknown.join(' ')}. Usage: check_strings.mjs [--update]`);
    return 2;
  }

  const catalogOk = checkCatalog() && checkKeysResolve();
  const counts = await collectCounts();

  if (update) {
    const n = writeBaseline(counts);
    console.log(`Wrote baseline for ${n} file(s) to ${path.relative(UI_ROOT, BASELINE_PATH)}`);
    return catalogOk ? 0 : 1;
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

  if (grew.length > 0) {
    console.error(`Found NEW hardcoded user-visible string(s) in ${grew.length} file(s):\n`);
    for (const { file, count, allowed } of grew) {
      console.error(`  ${file}: ${count} literal(s), baseline allows ${allowed}`);
    }
    console.error(
      '\nMove new strings into src/strings/en.json and render them via t() from src/strings/index.js.',
    );
  }
  if (shrank.length > 0) {
    console.error(`Baseline is stale for ${shrank.length} file(s) (fewer literals than allowed):\n`);
    for (const { file, count, allowed } of shrank) {
      console.error(`  ${file}: ${count} literal(s), baseline allows ${allowed}`);
    }
    console.error('\nLock the progress in: npm run lint:strings:update (commit the baseline change).');
  }

  if (grew.length === 0 && shrank.length === 0 && catalogOk) {
    const total = Object.values(counts).reduce((a, b) => a + b, 0);
    console.log(`OK: no new hardcoded strings (${total} grandfathered across ${Object.keys(counts).length} files).`);
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
