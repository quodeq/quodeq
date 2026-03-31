/**
 * Renders ~10 lines of surrounding code context with the violation line
 * (prefixed by ">>>") highlighted. Falls back to snippet display if no
 * context is available. Shows a scope badge when scope is provided.
 */
export default function ContextBlock({ context, snippet, scope }) {
  const scopeLabel = scope ? `Entire ${scope}` : null;
  return (
    <>
      {scopeLabel && <span className="finding-scope-badge">{scopeLabel}</span>}
      {context ? (
        <pre className="finding-context">{context.replace(/\\n/g, '\n').split('\n').map((line, i) => {
          const isHighlighted = line.startsWith('>>>');
          const display = isHighlighted ? line.slice(3) : line;
          return (
            <span
              key={i}
              className={isHighlighted ? 'finding-context-line--highlighted' : 'finding-context-line'}
            >{display}{'\n'}</span>
          );
        })}</pre>
      ) : snippet ? (
        <pre className="vlive-snippet">{snippet.replace(/\\n/g, '\n')}</pre>
      ) : null}
    </>
  );
}
