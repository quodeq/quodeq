/**
 * One scoring stage of the grade-formula editor: its number, its knobs on the
 * left, and the picked principle's numbers for that stage on the right.
 * @param {number} props.index - 1-based stage number
 * @param {string} props.title
 * @param {string} props.meaning - one line on what the stage does
 * @param {{lines: Array<{label: string, value: string, final?: boolean, was?: string|null}>|null, note: string|null}} props.live
 */
export default function StageRow({ index, title, meaning, live, children }) {
  return (
    <div className="gf-stage">
      <span className="gf-stage__n" aria-hidden="true">{index}</span>
      <div className="gf-stage__knobs">
        <h3 className="gf-stage__title">{title}</h3>
        <p className="gf-stage__meaning">{meaning}</p>
        {children}
      </div>
      <div className="gf-stage__live">
        {live.lines ? live.lines.map((line) => <LiveLine key={line.label} line={line} />) : <span className="gf-stage__note">{live.note}</span>}
      </div>
    </div>
  );
}

function LiveLine({ line }) {
  return (
    <div className="gf-stage__line">
      <span className="gf-stage__line-label">{line.label}</span>
      {' '}
      <b className={line.final ? 'gf-stage__final' : undefined}>{line.value}</b>
      {line.was ? <> {' '}<span className="gf-stage__was">{line.was}</span></> : null}
    </div>
  );
}
