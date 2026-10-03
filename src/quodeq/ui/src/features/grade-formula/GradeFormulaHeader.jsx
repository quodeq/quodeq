import { TermHeader } from '../../components/terminal/index.js';
import { t } from '../../strings/index.js';

function Picker({ label, value, options, onChange }) {
  if (options.length === 0) return null;
  return (
    <select className="gf-picker" aria-label={label} value={value || ''} onChange={(e) => onChange(e.target.value)}>
      {options.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
    </select>
  );
}

function headerSub(scope, runLabel) {
  if (runLabel) return t('gradeFormula.yourRun', { date: runLabel });
  return scope.project ? t('gradeFormula.previewOf', { project: scope.project }) : t('gradeFormula.noPreviewProject');
}

/**
 * The editor's header: name, which run the numbers come from, and the
 * dimension and principle pickers for the worked example.
 * @param {{project: string|null, runId: string|null, dimensions: string[]}} props.scope
 * @param {string|null} props.runLabel - the run's date, when there is a run
 */
export default function GradeFormulaHeader({
  scope, dimension, setDimension, principleId, setPrincipleId, principles, runLabel,
}) {
  const pickers = scope.runId ? (
    <span className="gf-pickers">
      <Picker label={t('gradeFormula.pickDimension')} value={dimension} options={scope.dimensions} onChange={setDimension} />
      <Picker label={t('gradeFormula.pickPrinciple')} value={principleId} options={principles.map((p) => p.principleId)} onChange={setPrincipleId} />
    </span>
  ) : null;
  return <TermHeader name={t('gradeFormula.headerName')} sub={headerSub(scope, runLabel)} badge={pickers} />;
}
