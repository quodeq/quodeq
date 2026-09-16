// Shared runner for the UI's per-file ratchet gates: tools/check_hygiene.mjs
// and tools/check_magic.mjs. A gate is one eslint flat config, one set of rule
// ids and one baseline JSON of per-file violation counts (counts, not line
// keys, so unrelated edits don't churn the baseline). Existing violations are
// grandfathered so the gate runs green today while blocking NEW ones; the
// baseline only shrinks, via the gate's --update command. Inline config is
// disabled so an eslint-disable comment cannot waive a rule.
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { ESLint } from 'eslint';

const UI_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

async function collectCounts(configPath, rules) {
  const eslint = new ESLint({
    cwd: UI_ROOT,
    overrideConfigFile: configPath,
    allowInlineConfig: false,
  });
  const results = await eslint.lintFiles(['src/**/*.jsx', 'src/**/*.js']);
  const counts = {};
  for (const r of results) {
    const fatal = r.messages.filter((m) => m.fatal);
    if (fatal.length > 0) {
      throw new Error(`lint failed on ${r.filePath}: ${fatal[0].message}`);
    }
    const n = r.messages.filter((m) => rules.has(m.ruleId)).length;
    if (n > 0) {
      counts[path.relative(UI_ROOT, r.filePath).split(path.sep).join('/')] = n;
    }
  }
  return counts;
}

function loadBaseline(baselinePath) {
  if (!existsSync(baselinePath)) return {};
  return JSON.parse(readFileSync(baselinePath, 'utf8'));
}

function writeBaseline(baselinePath, counts) {
  const sorted = Object.fromEntries(
    Object.entries(counts).sort(([a], [b]) => (a < b ? -1 : 1)),
  );
  writeFileSync(baselinePath, JSON.stringify(sorted, null, 2) + '\n', 'utf8');
  return sorted;
}

function total(counts) {
  return Object.values(counts).reduce((a, b) => a + b, 0);
}

/**
 * Runs one gate against process.argv (`--update` rewrites the baseline) and
 * resolves to the process exit code: 0 green, 1 violations, 2 bad usage.
 *
 * @param {object} gate
 * @param {string} gate.script          wrapper basename under tools/, for the usage and ceiling messages
 * @param {string} gate.configPath      eslint flat config, relative to the UI root
 * @param {string} gate.baselinePath    per-file counts JSON, relative to the UI root
 * @param {Iterable<string>} gate.rules eslint rule ids that count as violations
 * @param {number} gate.ceiling         the wrapper's TOTAL_CEILING; the baseline total may not exceed it
 * @param {string} gate.noun            plural noun for the OK line ("hygiene violations")
 * @param {string} gate.found           what a new violation is called ("magic number(s)")
 * @param {string} gate.hint            how to fix a new violation, printed after the file list
 * @param {string} gate.updateCommand   npm script that rewrites the baseline
 */
export async function runRatchet({ script, configPath, baselinePath, rules, ceiling, noun, found, hint, updateCommand }) {
  const config = path.join(UI_ROOT, configPath);
  const baselineFile = path.join(UI_ROOT, baselinePath);
  const ruleSet = new Set(rules);

  const args = process.argv.slice(2);
  const update = args.includes('--update');
  const unknown = args.filter((a) => a !== '--update');
  if (unknown.length > 0) {
    console.error(`Unknown argument(s): ${unknown.join(' ')}. Usage: ${script} [--update]`);
    return 2;
  }

  const counts = await collectCounts(config, ruleSet);

  if (update) {
    const written = writeBaseline(baselineFile, counts);
    console.log(
      `Wrote baseline for ${Object.keys(written).length} file(s), ${total(written)} violation(s), to ${path.relative(UI_ROOT, baselineFile)}`,
    );
    return 0;
  }

  const baseline = loadBaseline(baselineFile);
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
  const overCeiling = baselineTotal > ceiling;

  if (grew.length > 0) {
    console.error(`Found NEW ${found} in ${grew.length} file(s):\n`);
    for (const { file, count, allowed } of grew) {
      console.error(`  ${file}: ${count} violation(s), baseline allows ${allowed}`);
    }
    console.error(`\n${hint}`);
  }
  if (shrank.length > 0) {
    console.error(`Baseline is stale for ${shrank.length} file(s) (fewer violations than allowed):\n`);
    for (const { file, count, allowed } of shrank) {
      console.error(`  ${file}: ${count} violation(s), baseline allows ${allowed}`);
    }
    console.error(`\nLock the progress in: ${updateCommand} (commit the baseline change).`);
  }
  if (overCeiling) {
    console.error(
      `Baseline total grew to ${baselineTotal} (ceiling ${ceiling}). Fix the new violation instead of grandfathering it; if growth is truly justified, raise TOTAL_CEILING in tools/${script} in the same PR and explain why.`,
    );
  }

  if (grew.length === 0 && shrank.length === 0 && !overCeiling) {
    console.log(
      `OK: no new ${noun} (${total(counts)} grandfathered across ${Object.keys(counts).length} files).`,
    );
    return 0;
  }
  return 1;
}

/** Wrapper entry point: run the gate and exit with its code (2 on a crash). */
export function main(gate) {
  runRatchet(gate).then(
    (code) => process.exit(code),
    (err) => {
      console.error(err.message || err);
      process.exit(2);
    },
  );
}
