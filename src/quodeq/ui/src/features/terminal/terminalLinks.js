// Path detection for clickable terminal links. Pure (no xterm, no DOM) so it is
// unit-testable with `node --test`. TerminalPane wires the results into an
// xterm link provider; the backend verifies existence before anything lights up.

// A candidate path token plus its half-open column span [start, end) within the
// line (0-based), and an optional line:col parsed from a trailing `:N` / `:N:M`.
// The span covers ONLY the path (never the :line:col suffix) so the underline
// and click target match what the user reads as the filename.

// Matches:
//   ./rel/path.js            relative with a leading ./ or ../
//   src/pkg/mod.py:12:3      relative with at least one slash + optional :line:col
//   /abs/path.rs             absolute
//   ~/notes.md               home-relative
// A bare word like `README` (no slash, no dot-slash) is deliberately NOT matched
// — too many false positives; the backend existence check is the second gate,
// but we keep the regex conservative so we rarely even ask.
const PATH_RE =
  /(?<![\w./~-])((?:\.{1,2}\/|~\/|\/)?[\w.-]+(?:\/[\w.-]+)+|\.{1,2}\/[\w.-]+|~\/[\w.-]+)(?::(\d+)(?::(\d+))?)?/g;

// Trailing punctuation that commonly hugs a path in prose/tool output but is not
// part of it: `see src/a.js.` or `(src/a.js)` or `src/a.js,`.
const TRAILING = /[).,:;'"\]}>]+$/;

// http/https URLs. Kept as its own provider (rather than pulling in
// @xterm/addon-web-links) so URLs and file paths share the exact same
// cmd-click gating and there is no xterm peer-dependency to track.
const URL_RE = /\bhttps?:\/\/[^\s'"`()<>[\]{}]+/g;

export function extractUrlCandidates(line) {
  if (!line) return [];
  const out = [];
  for (const m of line.matchAll(URL_RE)) {
    const stripped = m[0].replace(TRAILING, '');
    if (!stripped) continue;
    out.push({ text: stripped, start: m.index, end: m.index + stripped.length });
  }
  return out;
}

export function extractPathCandidates(line) {
  if (!line) return [];
  const out = [];
  for (const m of line.matchAll(PATH_RE)) {
    const text = m[1];
    const matchStart = m.index;
    // Strip trailing punctuation from the path span, shrinking end accordingly.
    const stripped = text.replace(TRAILING, '');
    if (!stripped) continue;
    const start = matchStart;
    const end = start + stripped.length;
    const line1 = m[2] ? Number(m[2]) : undefined;
    const col1 = m[3] ? Number(m[3]) : undefined;
    out.push({ text: stripped, start, end, line: line1, col: col1 });
  }
  return out;
}

// Build an xterm ILink. Columns are 1-based: a candidate span [start, end)
// (0-based, end exclusive) maps to start.x = start+1, end.x = end. Activation is
// gated on the platform modifier (cmd on macOS, ctrl elsewhere) so a plain click
// still selects text, matching iTerm / VS Code.
function makeLink(y, cand, activate) {
  return {
    text: cand.text,
    range: { start: { x: cand.start + 1, y }, end: { x: cand.end, y } },
    activate: (event) => {
      if (event && (event.metaKey || event.ctrlKey)) activate();
    },
  };
}

// URL link provider (synchronous). `readLine(y)` returns the text of buffer line
// y; `openUrl(url)` opens it in the system browser.
export function createUrlLinkProvider({ readLine, openUrl }) {
  return {
    provideLinks(y, callback) {
      const cands = extractUrlCandidates(readLine(y));
      callback(cands.length ? cands.map((c) => makeLink(y, c, () => openUrl(c.text))) : undefined);
    },
  };
}

// File-path link provider (async). Extracts candidates, asks `resolvePaths` which
// exist, and only makes the existing ones clickable. `openFile(abs, line, col)`
// opens the resolved absolute path in the editor.
export function createFileLinkProvider({ readLine, resolvePaths, openFile }) {
  return {
    provideLinks(y, callback) {
      const cands = extractPathCandidates(readLine(y));
      if (!cands.length) {
        callback(undefined);
        return;
      }
      Promise.resolve(resolvePaths(cands.map((c) => c.text)))
        .then((resolved) => {
          const byInput = new Map((resolved || []).map((r) => [r.input, r]));
          const links = [];
          for (const c of cands) {
            const r = byInput.get(c.text);
            if (r && r.exists) {
              links.push(makeLink(y, c, () => openFile(r.abs, c.line, c.col)));
            }
          }
          callback(links.length ? links : undefined);
        })
        .catch(() => callback(undefined));
    },
  };
}
