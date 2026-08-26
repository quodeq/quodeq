// The startup hold (App.jsx linger) keeps the fullscreen loader up while
// real content commits beneath it. Without an opaque background the logo
// floats over the half-built page it exists to cover — invisible in the
// old flow, where the page beneath was empty until the loader dropped.
// The inline variant overlays already-rendered pages by design and must
// stay transparent.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const css = readFileSync(new URL('../src/styles/base.css', import.meta.url), 'utf8');

function rulesFor(selectorRe) {
  return css.match(new RegExp(`${selectorRe}\\s*\\{[^}]*\\}`, 'g')) || [];
}

test('fullscreen loading screen declares the opaque page background', () => {
  const rules = rulesFor(String.raw`\.loading-screen:not\(\.loading-screen--inline\)`);
  assert.ok(
    rules.some((rule) => /background:\s*var\(--color-bg\)/.test(rule)),
    'expected a .loading-screen:not(.loading-screen--inline) rule with background: var(--color-bg)',
  );
});

test('inline loading screen stays transparent', () => {
  const rules = rulesFor(String.raw`\.loading-screen--inline`);
  assert.ok(
    rules.every((rule) => !/background/.test(rule)),
    'the inline variant must not gain a background',
  );
});
