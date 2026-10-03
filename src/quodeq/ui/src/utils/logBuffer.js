/**
 * Rolling log buffer shared by the log-stream hooks (job log SSE, provider
 * log SSE, server log poll).
 *
 * The buffer carries `firstSeq`, the sequence number of `lines[0]`: line i
 * has seq `firstSeq + i`, and seqs only grow for the life of a hook. A front
 * trim adds the dropped count, a reset adds the old length. ConsoleLogViewer
 * uses it to tell appended lines from trimmed ones in O(1), which content
 * comparison cannot do when lines repeat (heartbeats).
 *
 * Pure functions, safe as React state updaters.
 */

// Lines a log viewer keeps: the panels are viewers, not archives, and an
// unbounded array would grow without limit on a chatty stream. Shared by the
// three log hooks, which each used to declare the same 5000.
export const LOG_BUFFER_MAX_LINES = 5000;

/** The starting buffer. Never mutated: updates always return a new object. */
export const EMPTY_LOG_BUFFER = Object.freeze({ lines: Object.freeze([]), firstSeq: 0 });

/**
 * Append a batch and keep only the newest `maxLines` lines.
 * @param {{lines: string[], firstSeq: number}} prev
 * @param {string[]} batch
 * @param {number} maxLines
 * @returns {{lines: string[], firstSeq: number}} `prev` itself for an empty batch
 */
export function appendLines(prev, batch, maxLines) {
  if (batch.length === 0) return prev;
  const merged = prev.lines.length === 0 ? batch.slice() : prev.lines.concat(batch);
  const drop = Math.max(0, merged.length - maxLines);
  return {
    lines: drop > 0 ? merged.slice(drop) : merged,
    firstSeq: prev.firstSeq + drop,
  };
}

/**
 * Empty the buffer. The next line gets the seq after the last old one, so a
 * reset reads as "every old line was dropped".
 * @param {{lines: string[], firstSeq: number}} prev
 * @returns {{lines: string[], firstSeq: number}}
 */
export function clearLines(prev) {
  if (prev.lines.length === 0) return prev;
  return { lines: [], firstSeq: prev.firstSeq + prev.lines.length };
}
