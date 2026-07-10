import test from 'node:test';
import assert from 'node:assert/strict';
import { HIGHLIGHT_MARKER, isHighlightedLine, stripHighlightMarker } from './codeMarker.js';

// The analysis backend (src/quodeq/analysis/mcp/enrichment.py) prefixes
// highlighted context lines with ">>> " — the ">>>" marker plus a single
// space separator. The separator is presentation, not source: stripping it
// must recover the original line with its indentation byte-for-byte, or the
// highlighted line renders one space too far to the right in the code widget.

test('marker is ">>> " (three chevrons + one separator space)', () => {
  assert.equal(HIGHLIGHT_MARKER, '>>> ');
});

test('strips the marker AND its separator space, preserving indentation', () => {
  // Real line has 4 spaces of indentation; backend emits ">>>" + " " + line.
  assert.equal(stripHighlightMarker('>>>     print("hello")'), '    print("hello")');
});

test('a highlighted line aligns with the same unmarked line', () => {
  const source = '    print("hello")';
  assert.equal(stripHighlightMarker(`${HIGHLIGHT_MARKER}${source}`), source);
});

test('zero-indent highlighted line has no leading space', () => {
  assert.equal(stripHighlightMarker('>>> def hello():'), 'def hello():');
});

test('empty highlighted line (">>> ") becomes empty', () => {
  assert.equal(stripHighlightMarker('>>> '), '');
});

test('unmarked lines are returned unchanged', () => {
  assert.equal(stripHighlightMarker('    return x'), '    return x');
  assert.equal(stripHighlightMarker('def hello():'), 'def hello():');
});

test('defensive: bare ">>>" with no separator drops only the marker', () => {
  assert.equal(stripHighlightMarker('>>>x'), 'x');
});

test('isHighlightedLine detects the marker', () => {
  assert.equal(isHighlightedLine('>>> foo'), true);
  assert.equal(isHighlightedLine('    foo'), false);
  assert.equal(isHighlightedLine(''), false);
});
