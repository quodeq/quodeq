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
          <span className="scope-bar-label">Entire {scope}{hasCode ? ` \u00b7 ${codeLines.length} lines` : ''}</span>
          {hasCode && <span className="scope-bar-action">{expanded ? 'Hide \u25be' : 'View \u25b8'}</span>}
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

    const needsCollapse = highlighted.length > MAX_HIGHLIGHTED_COLLAPSED + 3;
    const visibleHighlighted = (!needsCollapse || expanded)
      ? highlighted
      : highlighted.slice(0, MAX_HIGHLIGHTED_COLLAPSED);
    const omitted = highlighted.length - MAX_HIGHLIGHTED_COLLAPSED;

    return (
      <pre className="finding-context">
        {before.map(l => renderLine(l.raw, l.lineNum, false))}
        {visibleHighlighted.map(l => renderLine(l.raw, l.lineNum, true))}
        {needsCollapse && !expanded && (
          <div className="ctx-line ctx-line--toggle">
            <span className="ctx-gutter"></span>
            <span className="ctx-code">
              ... ({omitted} more lines){' '}
              <button className="finding-toggle-btn-inline" onClick={() => setExpanded(true)}>See more</button>
            </span>
          </div>
        )}
        {needsCollapse && expanded && (
          <div className="ctx-line ctx-line--toggle">
            <span className="ctx-gutter"></span>
            <span className="ctx-code">
              <button className="finding-toggle-btn-inline" onClick={() => setExpanded(false)}>See less</button>
            </span>
          </div>
        )}
        {after.map(l => renderLine(l.raw, l.lineNum, false))}
      </pre>
    );
  }

  if (snippet) {
    const allLines = snippet.replace(/\\n/g, '\n').split('\n');
    const needsCollapse = allLines.length > MAX_HIGHLIGHTED_COLLAPSED + 3;
    const visibleLines = (!needsCollapse || expanded) ? allLines : allLines.slice(0, MAX_HIGHLIGHTED_COLLAPSED);
    const startLineNum = line || 1;

    return (
      <pre className="finding-context">
        {visibleLines.map((text, i) => renderSnippetLine(text, startLineNum + i))}
        {needsCollapse && !expanded && (
          <div className="ctx-line ctx-line--toggle">
            <span className="ctx-gutter"></span>
            <span className="ctx-code">
              ... ({allLines.length - MAX_HIGHLIGHTED_COLLAPSED} more lines){' '}
              <button className="finding-toggle-btn-inline" onClick={() => setExpanded(true)}>See more</button>
            </span>
          </div>
        )}
        {needsCollapse && expanded && (
          <div className="ctx-line ctx-line--toggle">
            <span className="ctx-gutter"></span>
            <span className="ctx-code">
              <button className="finding-toggle-btn-inline" onClick={() => setExpanded(false)}>See less</button>
            </span>
          </div>
        )}
      </pre>
    );
  }

  return null;
}
