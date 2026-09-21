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
// file instead of line-keyed entries so unrelated edits don't churn it. The
// eslint pass, the baseline I/O and the counts comparison come from
// tools/_ratchet_common.mjs, shared with tools/ratchet.mjs; this gate keeps
// its own main because it also validates the catalog itself.
//
// Also validates the catalog itself: no em-dashes in user-facing strings.
import { readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';
import {
  UI_ROOT, collectCounts, diffCounts, loadBaseline, total, writeBaseline, parseGateArgs,
} from './_ratchet_common.mjs';

const BASELINE_PATH = path.join(UI_ROOT, 'tools', 'strings_baseline.json');
const CATALOG_PATH = path.join(UI_ROOT, 'src', 'strings', 'en.json');

// The three surfaces that carry user-visible English, each needing its own
// detector: JSX text nodes, visible JSX attributes, and prose in plain-JS
// logic. All three feed one per-file baseline -- the contract is "this file
// has N grandfathered hardcoded strings", regardless of which shape they are.
const RATCHET_RULES = new Set([
  'react/jsx-no-literals',
  'i18n/no-literal-visible-attrs',
  'i18n/no-prose-literals',
]);

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
  const { update, error } = parseGateArgs(process.argv.slice(2), 'check_strings.mjs');
  if (error) {
    console.error(error);
    return 2;
  }

  const catalogOk = checkCatalog() && checkKeysResolve();
  const counts = await collectCounts(RATCHET_RULES);

  if (update) {
    const n = Object.keys(writeBaseline(BASELINE_PATH, counts)).length;
    console.log(`Wrote baseline for ${n} file(s) to ${path.relative(UI_ROOT, BASELINE_PATH)}`);
    return catalogOk ? 0 : 1;
  }

  const baseline = loadBaseline(BASELINE_PATH);
  const { grew, shrank } = diffCounts(counts, baseline);

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
    console.log(`OK: no new hardcoded strings (${total(counts)} grandfathered across ${Object.keys(counts).length} files).`);
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
