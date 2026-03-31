/**
 * Renders surrounding code context with the violation line
 * (prefixed by ">>>") highlighted. Falls back to snippet display if no
 * context is available. Shows a scope badge when scope is provided.
 * Large blocks are collapsed with an inline "See more" / "See less" toggle.
 */
import { useState } from 'react';

const COLLAPSED_LINES = 10;

function renderLines(lines) {
  return lines.map((line, i) => {
    const isHighlighted = line.startsWith('>>>');
    const display = isHighlighted ? line.slice(3) : line;
    return (
      <span
        key={i}
        className={isHighlighted ? 'finding-context-line--highlighted' : 'finding-context-line'}
      >{display}{'\n'}</span>
    );
  });
}

export default function ContextBlock({ context, snippet, scope }) {
  const [expanded, setExpanded] = useState(false);
  const scopeLabel = scope ? `Entire ${scope}` : null;

  if (context) {
    const allLines = context.replace(/\\n/g, '\n').split('\n');
    const needsCollapse = allLines.length > COLLAPSED_LINES + 3;
    const visibleLines = (!needsCollapse || expanded) ? allLines : allLines.slice(0, COLLAPSED_LINES);

    return (
      <>
        {scopeLabel && <span className="finding-scope-badge">{scopeLabel}</span>}
        <pre className="finding-context">
          {renderLines(visibleLines)}
          {needsCollapse && !expanded && (
            <span className="finding-context-line finding-context-toggle">
              ... ({allLines.length - COLLAPSED_LINES} more lines){' '}
              <button className="finding-toggle-btn-inline" onClick={() => setExpanded(true)}>See more</button>
            </span>
          )}
          {needsCollapse && expanded && (
            <span className="finding-context-line finding-context-toggle">
              <button className="finding-toggle-btn-inline" onClick={() => setExpanded(false)}>See less</button>
            </span>
          )}
        </pre>
      </>
    );
  }

  if (snippet) {
    const allLines = snippet.replace(/\\n/g, '\n').split('\n');
    const needsCollapse = allLines.length > COLLAPSED_LINES + 3;
    const visibleLines = (!needsCollapse || expanded) ? allLines : allLines.slice(0, COLLAPSED_LINES);

    return (
      <>
        {scopeLabel && <span className="finding-scope-badge">{scopeLabel}</span>}
        <pre className="vlive-snippet">
          {visibleLines.join('\n')}
          {needsCollapse && !expanded && (
            <>
              {'\n'}... ({allLines.length - COLLAPSED_LINES} more lines){' '}
              <button className="finding-toggle-btn-inline" onClick={() => setExpanded(true)}>See more</button>
            </>
          )}
          {needsCollapse && expanded && (
            <>
              {'\n'}
              <button className="finding-toggle-btn-inline" onClick={() => setExpanded(false)}>See less</button>
            </>
          )}
        </pre>
      </>
    );
  }

  return scopeLabel ? <span className="finding-scope-badge">{scopeLabel}</span> : null;
}
