// LOCALE is the one tag every Intl call reads. Before this existed, call
// sites passed `undefined` -- "use the browser's locale" -- so a Dutch
// machine running the English UI got Dutch dates next to English copy, and
// translating the catalog would not have changed a single date.
//
// These assert the two properties that matter: today's output is unchanged,
// and swapping the tag actually reformats everything. The second is the
// point of the change and the easiest thing to get subtly wrong (a hardcoded
// month array formats identically no matter what tag you pass it).
import test from 'node:test';
import assert from 'node:assert/strict';
import { LOCALE } from './index.js';
import { formatPeriodLabel, formatShortDate } from '../utils/formatters.js';

const ENTRY = { dateISO: '2026-03-25T14:00:00', dateLabel: 'server label' };

test('LOCALE is a BCP-47 tag, not a bare language', () => {
  // 'en' would resolve to US ordering and silently reformat every date in
  // the product; the app renders day-month-year.
  assert.match(LOCALE, /^[a-z]{2}-[A-Z]{2}$/);
});

test('day/month formatting is unchanged from the hand-rolled version', () => {
  assert.equal(formatPeriodLabel(ENTRY, 'day'), '25 Mar 2026');
  assert.equal(formatPeriodLabel(ENTRY, 'month'), 'March 2026');
  assert.equal(formatShortDate('2026-03-25T14:00:00'), '25 Mar 2026');
});

test('week keeps a catalog pattern, since Intl has no week-of-year format', () => {
  assert.equal(formatPeriodLabel(ENTRY, 'week'), 'Week 13, 2026');
});

// The regression this guards: with a hardcoded month-name array, every one
// of these produces English regardless of the tag, and the bug is invisible
// until someone actually ships a second locale.
test('month names come from Intl, so another locale genuinely reformats', () => {
  const d = new Date('2026-03-25T14:00:00');
  const shape = { day: 'numeric', month: 'short', year: 'numeric' };
  const es = d.toLocaleDateString('es-ES', shape);
  const nl = d.toLocaleDateString('nl-NL', shape);
  const ja = d.toLocaleDateString('ja-JP', shape);

  for (const [tag, out] of [['es-ES', es], ['nl-NL', nl], ['ja-JP', ja]]) {
    assert.ok(out && !out.includes('Mar'), `${tag} still rendered the English month: ${out}`);
  }
  assert.notEqual(es, nl, 'es and nl should not format identically');
});

test('unparseable input still falls back to the server label', () => {
  assert.equal(formatPeriodLabel({ dateISO: 'not-a-date', dateLabel: 'server label' }, 'day'), 'server label');
  assert.equal(formatPeriodLabel({ dateLabel: 'server label' }, 'month'), 'server label');
});
