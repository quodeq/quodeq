/**
 * Renders surrounding code context with VS Code-style line numbers and
 * highlighted violation lines. Falls back to snippet display if no
 * context is available. Shows a scope badge when scope is provided.
 * The "See more/less" toggle only applies to the highlighted (affected) lines.
 * The surrounding context lines (before/after) are always visible.
 *
 * Pretext integration:
 *   The `<pre>` block's height and widest-line width are pre-computed with
 *   `measureText` before paint. With `white-space: pre` the height reduces
 *   to `lines × lineHeight`; pretext is still used for max-line width so the
 *   scrollbar size is known and the collapsed→expanded transition doesn't
 *   snap.
 */
import { useLayoutEffect, useMemo, useRef, useState } from 'react';
import { measureWidth, cssFontFromElement } from '../utils/pretext.js';

const MAX_HIGHLIGHTED_COLLAPSED = 10;
const CONTEXT_PADDING = 5;
const CODE_LINE_HEIGHT = 18; // must match terminal.css .ctx-line line-height
const CODE_PRE_VPAD = 16;    // matches .term-code / .scope-bar-code vertical padding
const DEFAULT_CODE_FONT = '12px "JetBrains Mono", ui-monospace, monospace';

function renderLine(raw, lineNum, isHighlighted) {
  const display = isHighlighted ? raw.slice(3) : raw;
  return (
    <div key={lineNum} className={`ctx-line${isHighlighted ? ' ctx-line--hl' : ''}`}>
      <span className="ctx-gutter">{lineNum}</span>
      <span className="ctx-code">{display}</span>
    </div>
  );
}

function renderSnippetLine(text, lineNum) {
  return (
    <div key={lineNum} className="ctx-line">
      <span className="ctx-gutter">{lineNum}</span>
      <span className="ctx-code">{text}</span>
    </div>
  );
}

/**
 * CodeBlockPre — the `<pre>` wrapper that pre-computes dimensions with pretext.
 *
 * `renderedLines` is an array of React children. `codeLines` is the raw string
 * array we use to measure natural widths (stripping the `>>>` highlight marker
 * so width reflects what the user actually sees).
 */
function CodeBlockPre({ renderedLines, codeLines }) {
  const preRef = useRef(null);
  const [dims, setDims] = useState({ height: 0, maxWidth: 0 });

  useLayoutEffect(() => {
    const el = preRef.current;
    if (!el || codeLines.length === 0) return;
    const font = cssFontFromElement(el) || DEFAULT_CODE_FONT;
    let max = 0;
    for (let i = 0; i < codeLines.length; i++) {
      const raw = codeLines[i] || '';
      const text = raw.startsWith('>>>') ? raw.slice(3) : raw;
      const w = measureWidth(text, font);
      if (w > max) max = w;
    }
    const height = codeLines.length * CODE_LINE_HEIGHT + CODE_PRE_VPAD;
    setDims({ height, maxWidth: Math.ceil(max) });
  }, [codeLines]);

  const style = {};
  if (dims.height) style.height = dims.height;
  return (
    <pre
      ref={preRef}
      className="finding-context scope-bar-code"
      style={style}
      data-pretext-height={dims.height || undefined}
      data-pretext-max-width={dims.maxWidth || undefined}
      data-pretext-lines={codeLines.length || undefined}
    >
      {renderedLines}
    </pre>
  );
}

function ScopeBar({ label, lineCount, expanded, onToggle, children }) {
  const hasCode = lineCount > 0;
  return (
    <>
      <div
        className={`scope-bar${expanded && hasCode ? ' scope-bar--expanded' : ''}`}
        role={hasCode ? 'button' : undefined}
        tabIndex={hasCode ? 0 : undefined}
        onClick={hasCode ? onToggle : undefined}
        onKeyDown={hasCode ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onToggle(); } } : undefined}
      >
        <span className={`scope-bar-chevron${expanded ? ' scope-bar-chevron--open' : ''}`}>{'\u25b8'}</span>
        <span className="scope-bar-label">{label}{hasCode ? ` \u00b7 ${lineCount} lines` : ''}</span>
      </div>
      {expanded && hasCode && children}
    </>
  );
}

function useCodeLayout(raw) {
  return useMemo(() => {
    if (!raw) return { lines: [], highlightedIdx: -1 };
    const normalized = raw.replace(/\\n/g, '\n');
    const lines = normalized.split('\n');
    const highlightedIdx = lines.findIndex((l) => l.startsWith('>>>'));
    return { lines, highlightedIdx };
  }, [raw]);
}

export default function ContextBlock({ context, snippet, scope, line, endLine }) {
  const [expanded, setExpanded] = useState(false);
  const toggle = () => setExpanded((e) => !e);

  const { lines: scopeLines } = useCodeLayout(scope ? (snippet || context || '') : '');
  const { lines: ctxLines } = useCodeLayout(!scope && context ? context : '');
  const { lines: snippetLines } = useCodeLayout(!scope && !context && snippet ? snippet : '');

  if (scope) {
    const startNum = line || 1;
    const rendered = scopeLines.map((text, i) => renderSnippetLine(text, startNum + i));
    return (
      <ScopeBar label={`See ${scope}`} lineCount={scopeLines.length} expanded={expanded} onToggle={toggle}>
        <CodeBlockPre renderedLines={rendered} codeLines={scopeLines} />
      </ScopeBar>
    );
  }

  if (context) {
    const startLineNum = Math.max(1, (line || 1) - CONTEXT_PADDING);
    const before = [];
    const highlighted = [];
    const after = [];
    let pastHighlighted = false;
    for (let i = 0; i < ctxLines.length; i++) {
      const isHl = ctxLines[i].startsWith('>>>');
      const entry = { raw: ctxLines[i], lineNum: startLineNum + i };
      if (isHl) { pastHighlighted = true; highlighted.push(entry); }
      else if (!pastHighlighted) before.push(entry);
      else after.push(entry);
    }
    const rendered = [
      ...before.map((l) => renderLine(l.raw, l.lineNum, false)),
      ...highlighted.map((l) => renderLine(l.raw, l.lineNum, true)),
      ...after.map((l) => renderLine(l.raw, l.lineNum, false)),
    ];
    return (
      <ScopeBar label="See code" lineCount={ctxLines.length} expanded={expanded} onToggle={toggle}>
        <CodeBlockPre renderedLines={rendered} codeLines={ctxLines} />
      </ScopeBar>
    );
  }

  if (snippet) {
    const startNum = line || 1;
    const rendered = snippetLines.map((text, i) => renderSnippetLine(text, startNum + i));
    return (
      <ScopeBar label="See code" lineCount={snippetLines.length} expanded={expanded} onToggle={toggle}>
        <CodeBlockPre renderedLines={rendered} codeLines={snippetLines} />
      </ScopeBar>
    );
  }

  return null;
}
