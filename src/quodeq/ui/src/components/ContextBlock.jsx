/**
 * Renders surrounding code context with VS Code-style line numbers and
 * highlighted violation lines. Falls back to snippet display if no
 * context is available. Shows a scope badge when scope is provided.
 * Large blocks are collapsed with an inline "See more" / "See less" toggle.
 */
import { useState } from 'react';

const COLLAPSED_LINES = 10;
const CONTEXT_PADDING = 5;

function renderContextLines(lines, startLineNum) {
  return lines.map((raw, i) => {
    const isHighlighted = raw.startsWith('>>>');
    const display = isHighlighted ? raw.slice(3) : raw;
    const lineNum = startLineNum + i;
    return (
      <div key={i} className={`ctx-line${isHighlighted ? ' ctx-line--hl' : ''}`}>
        <span className="ctx-gutter">{lineNum}</span>
        <span className="ctx-code">{display}</span>
      </div>
    );
  });
}

function renderSnippetLines(lines, startLineNum) {
  return lines.map((text, i) => {
    const lineNum = startLineNum + i;
    return (
      <div key={i} className="ctx-line">
        <span className="ctx-gutter">{lineNum}</span>
        <span className="ctx-code">{text}</span>
      </div>
    );
  });
}

export default function ContextBlock({ context, snippet, scope, line, endLine }) {
  const [expanded, setExpanded] = useState(false);
  const scopeLabel = scope ? `Entire ${scope}` : null;

  if (context) {
    const allLines = context.replace(/\\n/g, '\n').split('\n');
    const needsCollapse = allLines.length > COLLAPSED_LINES + 3;
    const visibleLines = (!needsCollapse || expanded) ? allLines : allLines.slice(0, COLLAPSED_LINES);
    // Compute the starting line number from the finding's line
    const startLineNum = Math.max(1, (line || 1) - CONTEXT_PADDING);

    return (
      <>
        {scopeLabel && <span className="finding-scope-badge">{scopeLabel}</span>}
        <pre className="finding-context">
          {renderContextLines(visibleLines, startLineNum)}
          {needsCollapse && !expanded && (
            <div className="ctx-line ctx-line--toggle">
              <span className="ctx-gutter"></span>
              <span className="ctx-code">
                ... ({allLines.length - COLLAPSED_LINES} more lines){' '}
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
      </>
    );
  }

  if (snippet) {
    const allLines = snippet.replace(/\\n/g, '\n').split('\n');
    const needsCollapse = allLines.length > COLLAPSED_LINES + 3;
    const visibleLines = (!needsCollapse || expanded) ? allLines : allLines.slice(0, COLLAPSED_LINES);
    const startLineNum = line || 1;

    return (
      <>
        {scopeLabel && <span className="finding-scope-badge">{scopeLabel}</span>}
        <pre className="finding-context">
          {renderSnippetLines(visibleLines, startLineNum)}
          {needsCollapse && !expanded && (
            <div className="ctx-line ctx-line--toggle">
              <span className="ctx-gutter"></span>
              <span className="ctx-code">
                ... ({allLines.length - COLLAPSED_LINES} more lines){' '}
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
      </>
    );
  }

  return scopeLabel ? <span className="finding-scope-badge">{scopeLabel}</span> : null;
}
