/**
 * Theme-matrix contrast guard.
 *
 * Every shipped theme combination (5 families x light/dark, plus the
 * system-preference dark path) must keep its text tokens legible on every
 * surface token. This exists because only the default pair ever gets
 * eyeballed — the other eight combinations previously shipped with muted
 * and subtle text as low as 1.9:1. A new theme family, or a tweak to any
 * bg/surface/text value, re-runs the whole matrix here.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  auditContrast, themeContexts, parseBlocks, contrastRatio, parseColor, defaultTokensPath,
} from './token_contrast.mjs';

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
  // Each context must actually resolve its own surfaces — an empty context
  // means a selector drifted and the audit below would vacuously pass.
  for (const [name, vars] of Object.entries(themes)) {
    assert.ok(vars['--color-bg'], `${name} resolved no --color-bg`);
    assert.ok(vars['--color-text'], `${name} resolved no --color-text`);
  }
});

test('contrastRatio matches known WCAG reference points', () => {
  const white = parseColor('#ffffff');
  const black = parseColor('#000000');
  assert.equal(Math.round(contrastRatio(white, black)), 21);
  assert.equal(Math.round(contrastRatio(white, white)), 1);
});

test('every text token clears its floor on every surface, in every theme', () => {
  const { results, failures } = auditContrast(css);
  // 12 contexts x 3 text tokens x 3 surfaces — if this shrinks, the parser
  // stopped seeing part of the matrix and the guard is weaker than it looks.
  assert.ok(results.length >= 100, `matrix shrank: only ${results.length} checks ran`);
  const table = failures
    .map((f) => `  ${f.theme}: ${f.textToken} ${f.fg} on ${f.surfaceToken} ${f.bg} = ${f.ratio} (min ${f.min})`)
    .join('\n');
  assert.equal(failures.length, 0, `contrast failures:\n${table}`);
});
