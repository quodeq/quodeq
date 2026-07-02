import ParamSlider from './ParamSlider.jsx';
import CurvePlot from './CurvePlot.jsx';
import GradeBoundaryBar from './GradeBoundaryBar.jsx';

export function SeverityTab({ draft, update }) {
  const w = draft.severityWeight;
  const setW = (sev) => (v) => update({ severityWeight: { ...w, [sev]: v } });
  const ratio = w.minor > 0 ? Math.round(w.critical / w.minor) : 0;
  return (
    <div>
      <ParamSlider label="critical" value={w.critical} min={0.05} max={10} step={0.05}
        hint="weight of each distinct critical violation type" onChange={setW('critical')} />
      <ParamSlider label="major" value={w.major} min={0.05} max={10} step={0.05}
        hint="weight of each distinct major violation type" onChange={setW('major')} />
      <ParamSlider label="minor" value={w.minor} min={0.05} max={10} step={0.05}
        hint="weight of each distinct minor violation type" onChange={setW('minor')} />
      <span className="settings-description">
        a critical finding currently weighs {ratio}x a minor one
      </span>
    </div>
  );
}

export function CurveTab({ draft, update }) {
  return (
    <div style={{ display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap' }}>
      <CurvePlot baseK={draft.baseK} ceilScale={draft.ceilScale} thresholds={draft.gradeThresholds} />
      <div style={{ flex: 1, minWidth: 220 }}>
        <ParamSlider label="strictness K" value={draft.baseK} min={0.01} max={1} step={0.01}
          hint="steeper means violations hurt sooner" onChange={(v) => update({ baseK: v })} />
        <ParamSlider label="lift compress" value={draft.liftCompress} min={1} max={4} step={0.1}
          hint="higher means compliance lifts less" onChange={(v) => update({ liftCompress: v })} />
        <ParamSlider label="ceiling scale" value={draft.ceilScale} min={0} max={2} step={0.05}
          hint="higher means a lower max score under violation load"
          onChange={(v) => update({ ceilScale: v })} />
      </div>
    </div>
  );
}

export function BoundariesTab({ draft, update }) {
  return (
    <div>
      <span className="settings-label">GRADE LABELS</span>
      <span className="settings-description"> drag the dividers, or focus one and use the arrow keys. These labels drive every gauge and badge in the app.</span>
      <GradeBoundaryBar
        thresholds={draft.gradeThresholds}
        onChange={(t) => update({ gradeThresholds: t })}
      />
      <div style={{ marginTop: 14 }}>
        <span className="settings-label">SEVERITY FLOORS</span>
        <ParamSlider label="minor only" value={draft.floorMinor} min={0} max={10} step={0.5}
          hint="worst score when only minor violations exist"
          onChange={(v) => update({ floorMinor: Math.max(v, draft.floorMajor) })} />
        <ParamSlider label="major" value={draft.floorMajor} min={0} max={10} step={0.5}
          hint="worst score when majors but no criticals exist"
          onChange={(v) => update({ floorMajor: Math.min(v, draft.floorMinor) })} />
        <span className="settings-description">critical: no floor (fixed at 0)</span>
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
        {enabled ? 'weights applied' : 'apply dimension weights'}
      </button>
      <span className="settings-description"> when off, the overall grade is a plain mean across dimensions</span>
      <div style={{ marginTop: 10 }}>
        {Object.entries(weights).map(([dim, w]) => (
          <ParamSlider key={dim} label={dim} value={w} min={0.1} max={3} step={0.1}
            disabled={!enabled} onChange={setDim(dim)} />
        ))}
      </div>
    </div>
  );
}
