/**
 * Renders ~10 lines of surrounding code context with the violation line
 * (prefixed by ">>>") highlighted. Falls back to snippet display if no
 * context is available.
 */
export default function ContextBlock({ context, snippet }) {
  if (context) {
    const lines = context.replace(/\\n/g, '\n').split('\n');
    return (
      <pre className="finding-context">{lines.map((line, i) => {
        const isHighlighted = line.startsWith('>>>');
        const display = isHighlighted ? line.slice(3) : line;
        return (
          <span
            key={i}
            className={isHighlighted ? 'finding-context-line--highlighted' : 'finding-context-line'}
          >{display}{'\n'}</span>
        );
      })}</pre>
    );
  }
  if (snippet) {
    return <pre className="vlive-snippet">{snippet.replace(/\\n/g, '\n')}</pre>;
  }
  return null;
}
