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

// The boot variant covers the shell's body row. Two properties carry that,
// and both override the base .loading-screen rule, so a careless edit to
// either silently restores the bug they exist to prevent: `position:
// absolute` (fixed gets clipped by .app-shell__main-column's `contain:
// paint`, leaving the sidebar exposed) and `pointer-events: auto` (the base
// rule passes clicks through to chrome the loader is covering).
test('shell loading screen is absolute and swallows clicks', () => {
  const rules = rulesFor(String.raw`\.loading-screen--shell`);
  assert.equal(rules.length, 1, 'expected exactly one .loading-screen--shell rule');
  assert.match(rules[0], /position:\s*absolute/);
  assert.match(rules[0], /pointer-events:\s*auto/);
});

// It must sit below .app-shell__topbar so the top bar keeps painting over it.
test('shell loading screen stacks below the topbar', () => {
  const shellZ = Number(/z-index:\s*(\d+)/.exec(rulesFor(String.raw`\.loading-screen--shell`)[0])[1]);
  const terminalCss = readFileSync(new URL('../src/styles/terminal.css', import.meta.url), 'utf8');
  const topbarRule = /\.app-shell__topbar\s*\{[^}]*\}/.exec(terminalCss)[0];
  const topbarZ = Number(/z-index:\s*(\d+)/.exec(topbarRule)[1]);
  assert.ok(shellZ < topbarZ, `expected shell loader z-index ${shellZ} < topbar ${topbarZ}`);
});

// The overlay is positioned against the body row, not the viewport. Match the
// base rule (the one that lays the grid out) rather than the first hit -- a
// media query overrides .app-shell__body further up the file.
test('app shell body is a containing block for the shell loader', () => {
  const terminalCss = readFileSync(new URL('../src/styles/terminal.css', import.meta.url), 'utf8');
  const rules = terminalCss.match(/\.app-shell__body\s*\{[^}]*\}/g) || [];
  const base = rules.find((rule) => /display:\s*grid/.test(rule));
  assert.ok(base, 'expected a .app-shell__body rule declaring the grid');
  assert.match(base, /position:\s*relative/);
});
