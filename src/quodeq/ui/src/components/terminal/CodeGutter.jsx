/**
 * CodeGutter — code block with line numbers and optional highlighted lines.
 *
 *   <CodeGutter
 *     code={sourceText}
 *     startLine={1}
 *     highlightLines={[6]}
 *   />
 *
 * Lines in `highlightLines` get a left accent bar using the theme accent.
 *
 * @param {object} props
 * @param {string}   props.code
 * @param {number}   [props.startLine=1]
 * @param {number[]} [props.highlightLines]
 * @param {string}   [props.language]  Optional hint, not used for highlighting here.
 */
export default function CodeGutter({ code, startLine = 1, highlightLines, language }) {
  const lines = code.split('\n');
  const hi = new Set(highlightLines || []);
  const pad = String(startLine + lines.length - 1).length;

  return (
    <pre className="term-code" data-language={language || undefined}>
      {lines.map((line, i) => {
        const n = startLine + i;
        const highlighted = hi.has(n);
        return (
          <div
            key={i}
            className={'term-code__line' + (highlighted ? ' term-code__line--hl' : '')}
          >
            <span className="term-code__num" aria-hidden="true">{String(n).padStart(pad, ' ')}</span>
            <span className="term-code__text">{line || '\u00A0'}</span>
          </div>
        );
      })}
    </pre>
  );
}
