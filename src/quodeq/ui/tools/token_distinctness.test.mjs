/**
 * Theme-matrix distinctness guard.
 *
 * Scope note (2026-08-26): the grade-vs-severity and grade-vs-accent rules
 * are gone on purpose. The user rejected both recolors that enforced them
 * and restored the original v1.9.1 grade palette, which shares the red
 * channel with severity and rides the accent at the top tier. What remains
 * guarded: grade steps stay mutually legible and grade text stays readable
 * at the restored palette's own baseline, and the duel identity colors
 * stay apart from each other and from every grade tier.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  auditDistinctness, themeContexts, parseBlocks, deltaE, parseColor, defaultTokensPath,
} from './token_distinctness.mjs';

const css = readFileSync(defaultTokensPath(), 'utf8');

test('parser sees every shipped theme combination', () => {
  const themes = themeContexts(parseBlocks(css));
  const names = Object.keys(themes);
  for (const expected of [
    'daruma-light', 'daruma-dark-system', 'daruma-dark', 'daruma-light-explicit',
    'neo-light', 'neo-dark', 'galadriel-light', 'galadriel-dark',
    'ifrit-light', 'ifrit-dark', 'deckard-light', 'deckard-dark',
  ]) {
    assert.ok(names.includes(expected), `missing theme context: ${expected}`);
  }
  // Each context must actually resolve grades and severity — an empty
  // context means a selector drifted and the audit would vacuously pass.
  for (const [name, vars] of Object.entries(themes)) {
    assert.ok(vars['--color-grade-top-text'], `${name} resolved no --color-grade-top-text`);
    assert.ok(vars['--color-sev-critical-text'], `${name} resolved no --color-sev-critical-text`);
  }
});

test('deltaE matches known reference points', () => {
  const white = parseColor('#ffffff');
  const black = parseColor('#000000');
  assert.equal(Math.round(deltaE(white, black)), 100);
  assert.equal(Math.round(deltaE(white, white)), 0);
  // The audit's headline finding: grade-bottom and sev-critical were both
  // this exact red in daruma light. Identical colors must measure as such.
  assert.equal(deltaE(parseColor('#b00a14'), parseColor('#b00a14')), 0);
});

test('grade legibility and duel identity hold in every theme', () => {
  const { results, failures } = auditDistinctness(css);
  // 12 contexts x (15 contrast + 10 grade-step + 1 duel sides + 3 duel-b
  // contrast + 5 duel-b-vs-grade) = 408 — if this shrinks, the parser
  // stopped seeing part of the matrix and the guard is weaker than it
  // looks.
  assert.ok(results.length >= 400, `matrix shrank: only ${results.length} checks ran`);
  const table = failures
    .map((f) => `  ${f.theme}: ${f.rule} ${f.a} vs ${f.b} = ${f.value} (min ${f.min} ${f.kind})`)
    .join('\n');
  assert.equal(failures.length, 0, `distinctness failures:\n${table}`);
});
