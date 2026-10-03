import ParamSlider from './ParamSlider.jsx';
import { t } from '../../strings/index.js';

/**
 * The per-dimension weights and the toggle that decides whether they apply at
 * all (off means a plain mean across dimensions).
 * @param {object} props.draft - the draft formula being edited.
 * @param {(patch: object) => void} props.update - merges a patch into the draft.
 */
export function DimensionsTab({ draft, update }) {
  const enabled = draft.dimensionWeightsEnabled;
  const weights = draft.dimensionWeights;
  const setDim = (dim) => (v) => update({ dimensionWeights: { ...weights, [dim]: v } });
  return (
    <div>
      <button
        type="button"
        className={`settings-pill${enabled ? ' settings-pill--active' : ''}`}
        aria-pressed={enabled}
        onClick={() => update({ dimensionWeightsEnabled: !enabled })}
      >
        {enabled ? t('gradeFormula.weightsApplied') : t('gradeFormula.applyWeights')}
      </button>
      <span className="settings-description"> {t('gradeFormula.plainMean')}</span>
      <div style={{ marginTop: 10 }}>
        {Object.entries(weights).map(([dim, w]) => (
          <ParamSlider key={dim} label={dim} value={w} min={0.1} max={3} step={0.1}
            disabled={!enabled} onChange={setDim(dim)} />
        ))}
      </div>
    </div>
  );
}
