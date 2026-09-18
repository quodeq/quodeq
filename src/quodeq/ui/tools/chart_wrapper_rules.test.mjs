// `.chart-with-kbd` wraps the Recharts container inside .run-history-panel, a
// flex column. The chart fills that column through
// `.run-history-panel .recharts-responsive-container { flex: 1 }` -- but that
// only works while the wrapper passes the growth through. When the wrapper was
// introduced (a11y sweep, keyboard controls) it was `position: relative` only,
// so it sized to content: ResponsiveContainer's height="100%" resolved against
// an auto-height parent, fell back to its minHeight, and every score-history
// panel showed a short chart with dead space beneath it.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const base = readFileSync(new URL('../src/styles/base.css', import.meta.url), 'utf8');
const dashboard = readFileSync(new URL('../src/styles/dashboard.css', import.meta.url), 'utf8');

function rule(css, selectorRe) {
  const match = new RegExp(`${selectorRe}\\s*\\{[^}]*\\}`).exec(css);
  assert.ok(match, `expected a rule for ${selectorRe}`);
  return match[0];
}

test('chart-with-kbd passes the panel height through to the chart', () => {
  const wrapper = rule(base, String.raw`\.chart-with-kbd`);
  assert.match(wrapper, /flex:\s*1/, 'wrapper must grow inside the flex-column panel');
  assert.match(wrapper, /display:\s*flex/, 'wrapper must be a flex container so the chart can grow inside it');
  assert.match(wrapper, /flex-direction:\s*column/);
  assert.match(wrapper, /min-height:\s*0/, 'without this the wrapper cannot shrink below its content');
});

// The wrapper stays a positioning context for .chart-kbd-controls, which is
// `position: absolute; inset: 0` over the chart.
test('chart-with-kbd stays the positioning context for the keyboard controls', () => {
  assert.match(rule(base, String.raw`\.chart-with-kbd`), /position:\s*relative/);
  assert.match(rule(base, String.raw`\.chart-kbd-controls`), /position:\s*absolute/);
});

// The other half of the chain: the chart itself must claim the space the
// wrapper now hands it.
test('the recharts container still grows inside the panel', () => {
  const chart = rule(dashboard, String.raw`\.run-history-panel \.recharts-responsive-container[^{]*`);
  assert.match(chart, /flex:\s*1/);
});
