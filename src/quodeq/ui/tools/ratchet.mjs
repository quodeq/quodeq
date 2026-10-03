// Shared runner for the UI's per-file ratchet gates: tools/check_hygiene.mjs
// and tools/check_magic.mjs. A gate is one eslint flat config, one set of rule
// ids and one baseline JSON of per-file violation counts (counts, not line
// keys, so unrelated edits don't churn the baseline). Existing violations are
// grandfathered so the gate runs green today while blocking NEW ones; the
// baseline only shrinks, via the gate's --update command. Inline config is
// disabled so an eslint-disable comment cannot waive a rule.
//
// The eslint pass, the baseline I/O and the counts comparison live in
// tools/_ratchet_common.mjs, shared with tools/check_strings.mjs.
import path from 'node:path';
import {
  UI_ROOT, collectCounts, diffCounts, exitWith, loadBaseline, okSummary, total, writeBaseline, parseGateArgs,
} from './_ratchet_common.mjs';

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

  const { update, error } = parseGateArgs(process.argv.slice(2), script);
  if (error) {
    console.error(error);
    return 2;
  }

  const counts = await collectCounts(rules, {
    overrideConfigFile: config,
    allowInlineConfig: false,
  });

  if (update) {
    const written = writeBaseline(baselineFile, counts);
    console.log(
      `Wrote baseline for ${Object.keys(written).length} file(s), ${total(written)} violation(s), to ${path.relative(UI_ROOT, baselineFile)}`,
    );
    return 0;
  }

  const baseline = loadBaseline(baselineFile);
  const { grew, shrank } = diffCounts(counts, baseline);
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
    console.log(okSummary(noun, counts));
    return 0;
  }
  return 1;
}

/** Wrapper entry point: run the gate and exit with its code (2 on a crash). */
export function main(gate) {
  exitWith(runRatchet(gate));
}
