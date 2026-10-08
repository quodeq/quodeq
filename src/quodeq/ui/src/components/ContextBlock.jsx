/**
 * Renders surrounding code context with VS Code-style line numbers and
 * highlighted violation lines. Falls back to snippet display if no
 * context is available. Shows a scope badge when scope is provided.
 * An editor-tab strip on top of the code collapses the whole block: it names
 * the file (or reads "See code" / "See <scope>" when the finding has none),
 * the line range and the line count, so the location shows while collapsed.
 * Nothing below the strip renders until it's expanded.
 *
 * Pretext integration:
 *   The `<pre>` block's height and widest-line width are pre-computed with
 *   `measureText` before paint. With `white-space: pre` the height reduces
 *   to `lines × lineHeight`; pretext is still used for max-line width so the
 *   scrollbar size is known and the collapsed→expanded transition doesn't
 *   snap.
 */
import { useLayoutEffect, useMemo, useRef, useState } from 'react';
import { CopyIcon, COPY_FEEDBACK_MS } from './CopyButton.jsx';
import { measureWidth, cssFontFromElement } from '../utils/pretext.js';
import { isHighlightedLine, stripHighlightMarker } from '../utils/codeMarker.js';
import { copyToClipboard } from '../utils/clipboard.js';
import { parseFileRef } from '../utils/textFormatting.js';
import { t } from '../strings/index.js';

const CONTEXT_PADDING = 5;
const CODE_LINE_HEIGHT = 18; // must match terminal.css .ctx-line line-height
const CODE_PRE_VPAD = 16;    // matches .term-code / .scope-bar-code vertical padding
const DEFAULT_CODE_FONT = '12px "JetBrains Mono", ui-monospace, monospace';

function renderLine(raw, lineNum, isHighlighted) {
  const display = isHighlighted ? stripHighlightMarker(raw) : raw;
  return (
    <div key={lineNum} className={`ctx-line${isHighlighted ? ' ctx-line--hl' : ''}`}>
      <span className="ctx-gutter">
        {isHighlighted && <span className="sr-only">{t('context.violationLineMarker')}</span>}
        <span aria-hidden="true" className="context-line__marker">{isHighlighted ? '▸' : ''}</span>
        {lineNum}
      </span>
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
 * array we use to measure natural widths (stripping the highlight marker so
 * width reflects what the user actually sees).
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
      const text = stripHighlightMarker(raw);
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

/** The file a finding points at, split for display: muted directory, file name, line. */
function TabPath({ filePath, line }) {
  const cut = filePath.lastIndexOf('/') + 1;
  return (
    <span className="code-tab-path" title={filePath}>
      {cut > 0 && <span className="code-tab-dir">{filePath.slice(0, cut)}</span>}
      <span className="code-tab-file">{filePath.slice(cut)}</span>
      {line != null && <span className="code-tab-line">:{line}</span>}
    </span>
  );
}

/**
 * Copies `path:line`. Lives beside the toggle rather than inside it so the
 * strip never nests one button in another.
 */
function CopyPathBtn({ text }) {
  const [copied, setCopied] = useState(false);
  const onCopy = (e) => {
    // Same reason as FileCopyBtn: a finding row may toggle on click.
    e.stopPropagation();
    copyToClipboard(text)
      .then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), COPY_FEEDBACK_MS);
      })
      .catch((err) => console.warn('Clipboard copy failed:', err?.message || err));
  };
  const label = copied ? t('common.copied') : t('context.copyPath');
  return (
    <button type="button" className="code-tab-copy" onClick={onCopy} title={label} aria-label={label}>
      <CopyIcon />
    </button>
  );
}

function CodeTab({ label, file, line, firstLine, lineCount, expanded, onToggle, children }) {
  const hasCode = lineCount > 0;
  const open = expanded && hasCode;
  // `file` may carry its own ":line" suffix (parseFileRef); the line prop wins.
  const { filePath, line: fileLine } = parseFileRef(file, line);
  const lastLine = firstLine + lineCount - 1;
  const range = lineCount > 1 ? t('context.lineRange', { from: firstLine, to: lastLine }) : t('context.lineSingle', { line: firstLine });
  return (
    <div className={`code-tab${open ? ' code-tab--open' : ''}`}>
      <div className="code-tab-head">
        <button
          type="button"
          className="code-tab-toggle"
          aria-expanded={hasCode ? open : undefined}
          disabled={!hasCode}
          onClick={onToggle}
        >
          <span aria-hidden="true" className="code-tab-chevron">{'\u25b8'}</span>
          {filePath ? <TabPath filePath={filePath} line={fileLine} /> : <span className="code-tab-label">{label}</span>}
          {hasCode && (
            <span className="code-tab-meta">{range} · {lineCount === 1 ? t('context.lineCountOne') : t('context.lineCount', { count: lineCount })}</span>
          )}
        </button>
        {filePath && <CopyPathBtn text={fileLine != null ? `${filePath}:${fileLine}` : filePath} />}
      </div>
      {open && children}
    </div>
  );
}

function useCodeLayout(raw) {
  return useMemo(() => {
    if (!raw) return { lines: [], highlightedIdx: -1 };
    const normalized = raw.replace(/\\n/g, '\n');
    const lines = normalized.split('\n');
    const highlightedIdx = lines.findIndex(isHighlightedLine);
    return { lines, highlightedIdx };
  }, [raw]);
}

function splitContextLines(ctxLines, startLineNum) {
  const before = [];
  const highlighted = [];
  const after = [];
  let pastHighlighted = false;
  for (let i = 0; i < ctxLines.length; i++) {
    const isHl = isHighlightedLine(ctxLines[i]);
    const entry = { raw: ctxLines[i], lineNum: startLineNum + i };
    if (isHl) { pastHighlighted = true; highlighted.push(entry); }
    else if (!pastHighlighted) before.push(entry);
    else after.push(entry);
  }
  return { before, highlighted, after };
}

function contextStartLine(line) {
  return Math.max(1, (line || 1) - CONTEXT_PADDING);
}

function renderContextLines(ctxLines, line) {
  const startLineNum = contextStartLine(line);
  const { before, highlighted, after } = splitContextLines(ctxLines, startLineNum);
  return [
    ...before.map((l) => renderLine(l.raw, l.lineNum, false)),
    ...highlighted.map((l) => renderLine(l.raw, l.lineNum, true)),
    ...after.map((l) => renderLine(l.raw, l.lineNum, false)),
  ];
}

export default function ContextBlock({ context, snippet, scope, line, file }) {
  const [expanded, setExpanded] = useState(false);
  const toggle = () => setExpanded((e) => !e);

  const { lines: scopeLines } = useCodeLayout(scope ? (snippet || context || '') : '');
  const { lines: ctxLines } = useCodeLayout(!scope && context ? context : '');
  const { lines: snippetLines } = useCodeLayout(!scope && !context && snippet ? snippet : '');

  if (scope) {
    const startNum = line || 1;
    const rendered = scopeLines.map((text, i) => renderSnippetLine(text, startNum + i));
    return (
      <CodeTab label={t('context.seeScope', { scope })} file={file} line={line} firstLine={startNum} lineCount={scopeLines.length} expanded={expanded} onToggle={toggle}>
        <CodeBlockPre renderedLines={rendered} codeLines={scopeLines} />
      </CodeTab>
    );
  }

  if (context) {
    const rendered = renderContextLines(ctxLines, line);
    return (
      <CodeTab label={t('context.seeCode')} file={file} line={line} firstLine={contextStartLine(line)} lineCount={ctxLines.length} expanded={expanded} onToggle={toggle}>
        <CodeBlockPre renderedLines={rendered} codeLines={ctxLines} />
      </CodeTab>
    );
  }

  if (snippet) {
    const startNum = line || 1;
    const rendered = snippetLines.map((text, i) => renderSnippetLine(text, startNum + i));
    return (
      <CodeTab label={t('context.seeCode')} file={file} line={line} firstLine={startNum} lineCount={snippetLines.length} expanded={expanded} onToggle={toggle}>
        <CodeBlockPre renderedLines={rendered} codeLines={snippetLines} />
      </CodeTab>
    );
  }

  return null;
}
