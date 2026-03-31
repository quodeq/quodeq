/**
 * Renders surrounding code context with VS Code-style line numbers and
 * highlighted violation lines. Falls back to snippet display if no
 * context is available. Shows a scope badge when scope is provided.
 * The "See more/less" toggle only applies to the highlighted (affected) lines.
 * The surrounding context lines (before/after) are always visible.
 */
import { useState } from 'react';

const MAX_HIGHLIGHTED_COLLAPSED = 10;
const CONTEXT_PADDING = 5;

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

export default function ContextBlock({ context, snippet, scope, line, endLine }) {
  const [expanded, setExpanded] = useState(false);

  if (scope) {
    const codeText = snippet || context || '';
    const codeLines = codeText ? codeText.replace(/\\n/g, '\n').split('\n') : [];
    const hasCode = codeLines.length > 0;
    const startNum = line || 1;
    return (
      <>
        <div
          className={`scope-bar${expanded && hasCode ? ' scope-bar--expanded' : ''}`}
          role={hasCode ? 'button' : undefined}
          tabIndex={hasCode ? 0 : undefined}
          onClick={hasCode ? () => setExpanded(e => !e) : undefined}
          onKeyDown={hasCode ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setExpanded(ex => !ex); } } : undefined}
        >
          <span className={`scope-bar-chevron${expanded ? ' scope-bar-chevron--open' : ''}`}>{'\u25b8'}</span>
          <span className="scope-bar-label">See {scope}{hasCode ? ` \u00b7 ${codeLines.length} lines` : ''}</span>
        </div>
        {expanded && hasCode && (
          <pre className="finding-context scope-bar-code">
            {codeLines.map((text, i) => renderSnippetLine(text, startNum + i))}
          </pre>
        )}
      </>
    );
  }

  if (context) {
    const allLines = context.replace(/\\n/g, '\n').split('\n');
    const startLineNum = Math.max(1, (line || 1) - CONTEXT_PADDING);
    const hasCode = allLines.length > 0;

    // Split into before / highlighted / after sections
    const before = [];
    const highlighted = [];
    const after = [];
    let pastHighlighted = false;
    for (let i = 0; i < allLines.length; i++) {
      const isHl = allLines[i].startsWith('>>>');
      if (isHl) {
        pastHighlighted = true;
        highlighted.push({ raw: allLines[i], lineNum: startLineNum + i, hl: true });
      } else if (!pastHighlighted) {
        before.push({ raw: allLines[i], lineNum: startLineNum + i, hl: false });
      } else {
        after.push({ raw: allLines[i], lineNum: startLineNum + i, hl: false });
      }
    }

    return (
      <>
        <div
          className={`scope-bar${expanded && hasCode ? ' scope-bar--expanded' : ''}`}
          role={hasCode ? 'button' : undefined}
          tabIndex={hasCode ? 0 : undefined}
          onClick={hasCode ? () => setExpanded(e => !e) : undefined}
          onKeyDown={hasCode ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setExpanded(ex => !ex); } } : undefined}
        >
          <span className={`scope-bar-chevron${expanded ? ' scope-bar-chevron--open' : ''}`}>{'\u25b8'}</span>
          <span className="scope-bar-label">See code{hasCode ? ` \u00b7 ${allLines.length} lines` : ''}</span>
        </div>
        {expanded && hasCode && (
          <pre className="finding-context scope-bar-code">
            {before.map(l => renderLine(l.raw, l.lineNum, false))}
            {highlighted.map(l => renderLine(l.raw, l.lineNum, true))}
            {after.map(l => renderLine(l.raw, l.lineNum, false))}
          </pre>
        )}
      </>
    );
  }

  if (snippet) {
    const codeLines = snippet.replace(/\\n/g, '\n').split('\n');
    const hasCode = codeLines.length > 0;
    const startNum = line || 1;
    return (
      <>
        <div
          className={`scope-bar${expanded && hasCode ? ' scope-bar--expanded' : ''}`}
          role={hasCode ? 'button' : undefined}
          tabIndex={hasCode ? 0 : undefined}
          onClick={hasCode ? () => setExpanded(e => !e) : undefined}
          onKeyDown={hasCode ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setExpanded(ex => !ex); } } : undefined}
        >
          <span className={`scope-bar-chevron${expanded ? ' scope-bar-chevron--open' : ''}`}>{'\u25b8'}</span>
          <span className="scope-bar-label">See code{hasCode ? ` \u00b7 ${codeLines.length} lines` : ''}</span>
        </div>
        {expanded && hasCode && (
          <pre className="finding-context scope-bar-code">
            {codeLines.map((text, i) => renderSnippetLine(text, startNum + i))}
          </pre>
        )}
      </>
    );
  }

  return null;
}
