/**
 * Clean + dedupe for ConsoleLogViewer, done incrementally.
 *
 * Log sources hand out `{ logs, firstSeq }`: line i has sequence number
 * `firstSeq + i`, seqs only grow, a front trim or a reset raises firstSeq
 * (utils/logBuffer.js). From two consecutive (firstSeq, length) pairs the
 * pipeline knows exactly which lines were dropped and which were appended,
 * so it cleans and dedupes only the new tail and keeps every surviving row
 * object (and its seq, the React key). Content comparison could not do this:
 * repeated heartbeat lines make "which lines are new" ambiguous.
 *
 * The result always equals dedupeConsecutive(lines.map(cleanLine)); the
 * tests check that after every batch. Pure: prev state is never mutated.
 */

// Real ANSI: \x1b[ ... <letter>. Bare CSI fallback: [0;34m, [0m, etc.
// Digits are required: [m (no digits) would also match SGR reset but would
// incorrectly strip the leading [m from dimension names like [maintainability].
const ANSI_ESC_RE = /\x1b\[[\d;?]*[A-Za-z]/g;
const ANSI_BARE_RE = /\[\d+(?:;\d+)*m/g;

export function cleanLine(text) {
  if (text == null) return '';
  return String(text)
    .replace(ANSI_ESC_RE, '')
    .replace(ANSI_BARE_RE, '')
    // Collapse runs of inner whitespace introduced where escape codes
    // hugged a token (e.g. "[0m   [performance]" -> "   [performance]").
    .replace(/[ \t]{2,}/g, ' ')
    .trimEnd();
}

// Match severity prefixes the runner's logger adds. The same payload often
// arrives twice, once via stdout from the dimension runner, once echoed
// through the logging system with this prefix, so we normalize it away
// for dedup-key purposes (the visible line keeps whichever copy lands first).
const LEVEL_PREFIX_RE = /^\s*\[(?:INFO|WARN|WARNING|ERROR|DEBUG|TRACE)\]\s*/i;

// Heartbeat lines like `  [reliability] 4m50s | 1 active (11 total) | …`
// reprint every 10s, often with identical state. Strip the duration so
// consecutive identical-state heartbeats collapse to a single row in the
// view; the next emitted heartbeat appears as soon as the state actually
// changes.
const HEARTBEAT_DURATION_RE = /(\[[\w-]+\])\s+\d+m\d+s\s+(?=\|)/;

export function normalizeForDedup(line) {
  return line
    .replace(LEVEL_PREFIX_RE, '')
    .replace(HEARTBEAT_DURATION_RE, '$1 ')
    .trim();
}

/** Full recompute. Kept as the reference the incremental path must equal. */
export function dedupeConsecutive(lines) {
  if (!lines || lines.length === 0) return lines;
  const out = [];
  let prev = null;
  for (const line of lines) {
    const key = normalizeForDedup(line);
    if (key && key === prev) continue;
    out.push(line);
    prev = key;
  }
  return out;
}

// Same rule as dedupeConsecutive: an empty key never suppresses.
function pushDeduped(rows, row, prevKey) {
  const key = normalizeForDedup(row.text);
  if (key && key === prevKey) return prevKey;
  rows.push(row);
  return key;
}

/**
 * Clean and dedupe every line from scratch.
 * @returns {{firstSeq: number, endSeq: number, rows: Array<{seq: number, text: string}>, lastKey: string|null}}
 */
export function buildPipeline(lines, firstSeq, clean = cleanLine) {
  const rows = [];
  let lastKey = null;
  for (let i = 0; i < lines.length; i += 1) {
    lastKey = pushDeduped(rows, { seq: firstSeq + i, text: clean(lines[i]) }, lastKey);
  }
  return { firstSeq, endSeq: firstSeq + lines.length, rows, lastKey };
}

// Drop rows older than firstSeq. A full recompute always keeps the first
// line; if the line at firstSeq had been folded into a now-dropped row, put
// it back. The folded lines after it share its key, and the next kept row
// differs from that key, so one insertion restores equivalence.
function dropLeadingRows(prev, firstSeq, headLine, clean) {
  let cut = 0;
  while (cut < prev.rows.length && prev.rows[cut].seq < firstSeq) cut += 1;
  const rows = prev.rows.slice(cut);
  if (rows.length === 0 || rows[0].seq !== firstSeq) {
    rows.unshift({ seq: firstSeq, text: clean(headLine) });
  }
  return rows;
}

function needsFullBuild(prev, firstSeq, endSeq) {
  return !prev
    || firstSeq < prev.firstSeq
    || firstSeq >= prev.endSeq
    || endSeq < prev.endSeq;
}

/**
 * Move the pipeline to the source's current lines, doing work only for the
 * lines that changed. Without a numeric firstSeq (a source that does not
 * track seqs) it recomputes everything, which was the old behaviour.
 */
export function advancePipeline(prev, lines, firstSeq, clean = cleanLine) {
  const list = lines ?? [];
  if (!Number.isInteger(firstSeq)) return buildPipeline(list, 0, clean);
  const endSeq = firstSeq + list.length;
  if (needsFullBuild(prev, firstSeq, endSeq)) return buildPipeline(list, firstSeq, clean);
  if (firstSeq === prev.firstSeq && endSeq === prev.endSeq) return prev;
  const rows = firstSeq > prev.firstSeq
    ? dropLeadingRows(prev, firstSeq, list[0], clean)
    : prev.rows.slice();
  let { lastKey } = prev;
  for (let seq = prev.endSeq; seq < endSeq; seq += 1) {
    lastKey = pushDeduped(rows, { seq, text: clean(list[seq - firstSeq]) }, lastKey);
  }
  return { firstSeq, endSeq, rows, lastKey };
}

/**
 * The cleaned trailer line (the eval log's terminal line), or null when it
 * is absent or would dedupe against the last row, as it did when it was
 * appended to the log array.
 */
export function trailerText(state, trailer) {
  if (trailer == null) return null;
  const text = cleanLine(trailer);
  const key = normalizeForDedup(text);
  return key && key === state.lastKey ? null : text;
}
