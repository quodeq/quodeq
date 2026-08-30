import ParamSlider from './ParamSlider.jsx';
import CurvePlot from './CurvePlot.jsx';
import GradeBoundaryBar from './GradeBoundaryBar.jsx';
import { t } from '../../strings/index.js';

export function SeverityTab({ draft, update }) {
  const w = draft.severityWeight;
  const setW = (sev) => (v) => update({ severityWeight: { ...w, [sev]: v } });
  const ratio = w.minor > 0 ? Math.round(w.critical / w.minor) : 0;
  return (
    <div>
      <ParamSlider label={t('gradeFormula.weightCritical')} value={w.critical} min={0.05} max={10} step={0.05}
        hint={t('gradeFormula.hintCritical')} onChange={setW('critical')} />
      <ParamSlider label={t('gradeFormula.weightMajor')} value={w.major} min={0.05} max={10} step={0.05}
        hint={t('gradeFormula.hintMajor')} onChange={setW('major')} />
      <ParamSlider label={t('gradeFormula.weightMinor')} value={w.minor} min={0.05} max={10} step={0.05}
        hint={t('gradeFormula.hintMinor')} onChange={setW('minor')} />
      <span className="settings-description">
        {t('gradeFormula.criticalWeighs')} {ratio}{t('gradeFormula.timesMinor')}
      </span>
    </div>
  );
}

export function CurveTab({ draft, update }) {
  return (
    <div style={{ display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap' }}>
      <CurvePlot baseK={draft.baseK} ceilScale={draft.ceilScale} thresholds={draft.gradeThresholds} />
      <div style={{ flex: 1, minWidth: 220 }}>
        <ParamSlider label={t('gradeFormula.strictnessK')} value={draft.baseK} min={0.01} max={1} step={0.01}
          hint={t('gradeFormula.hintStrictness')} onChange={(v) => update({ baseK: v })} />
        <ParamSlider label={t('gradeFormula.liftCompress')} value={draft.liftCompress} min={1} max={4} step={0.1}
          hint={t('gradeFormula.hintLift')} onChange={(v) => update({ liftCompress: v })} />
        <ParamSlider label={t('gradeFormula.ceilScale')} value={draft.ceilScale} min={0} max={2} step={0.05}
          hint={t('gradeFormula.hintCeil')}
          onChange={(v) => update({ ceilScale: v })} />
      </div>
    </div>
  );
}

export function BoundariesTab({ draft, update }) {
  return (
    <div>
      <span className="settings-label">{t('gradeFormula.gradeLabels')}</span>
      <span className="settings-description"> {t('gradeFormula.gradeLabelsDesc')}</span>
      <GradeBoundaryBar
        thresholds={draft.gradeThresholds}
        onChange={(t) => update({ gradeThresholds: t })}
      />
      <div style={{ marginTop: 14 }}>
        <span className="settings-label">{t('gradeFormula.severityFloors')}</span>
        <ParamSlider label={t('gradeFormula.minorOnly')} value={draft.floorMinor} min={0} max={10} step={0.5}
          hint={t('gradeFormula.hintFloorMinor')}
          onChange={(v) => update({ floorMinor: v })} />
        <ParamSlider label={t('gradeFormula.floorMajor')} value={draft.floorMajor} min={0} max={10} step={0.5}
          hint={t('gradeFormula.hintFloorMajor')}
          onChange={(v) => update({ floorMajor: v })} />
        <span className="settings-description">{t('gradeFormula.criticalNoFloor')}</span>
      </div>
    </div>
  );
}

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
