/**
 * Theme-matrix distinctness guard.
 *
 * The design-system UX audit found the grade ramp and the severity ramp
 * colliding (an F-grade file and a critical finding shared the same red),
 * and several dark themes resolving accent, compliance, and grade-top to
 * one identical color. This suite keeps every shipped theme combination
 * honest: grade colors must stay perceptually apart from severity colors
 * and the accent, grade steps must stay mutually legible, and grade text
 * must clear the WCAG UI-component contrast floor on every surface.
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

test('grades, severity, accent, and compliance stay apart in every theme', () => {
  const { results, failures } = auditDistinctness(css);
  // 12 contexts x (15 grade-vs-sev + 5 grade-vs-accent + 15 contrast +
  // 10 grade-step + 1 compliance) — if this shrinks, the parser stopped
  // seeing part of the matrix and the guard is weaker than it looks.
  assert.ok(results.length >= 500, `matrix shrank: only ${results.length} checks ran`);
  const table = failures
    .map((f) => `  ${f.theme}: ${f.rule} ${f.a} vs ${f.b} = ${f.value} (min ${f.min} ${f.kind})`)
    .join('\n');
  assert.equal(failures.length, 0, `distinctness failures:\n${table}`);
});
