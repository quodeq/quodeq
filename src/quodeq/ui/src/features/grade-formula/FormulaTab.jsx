import ParamSlider from './ParamSlider.jsx';
import CurvePlot from './CurvePlot.jsx';
import GradeBoundaryBar from './GradeBoundaryBar.jsx';
import StageRow from './StageRow.jsx';
import { t } from '../../strings/index.js';
import { SCORE_SCALE_MAX } from '../../constants.js';

// Bounds shared by the three severity-weight sliders.
const SEVERITY_WEIGHT_MIN = 0.05;
const SEVERITY_WEIGHT_MAX = 10;
const SEVERITY_WEIGHT_STEP = 0.05;

// The stageRows key of the final line: it alone carries a "was".
const FINAL_KEY = 'final';
// Which stage rows (by stageRows key) each stage shows on its right.
const STAGE_KEYS = [['types'], ['base'], ['lift', 'raw'], ['ceiling', 'floor', FINAL_KEY]];
const STAGE_TYPES = 0;
const STAGE_BASE = 1;
const STAGE_LIFT = 2;
const STAGE_CEILING = 3;

function rowsByKey(rows) {
  return rows ? Object.fromEntries(rows.map((r) => [r.key, r])) : null;
}

// The lines of one stage: the live rows when the draft has been computed,
// else the stored rows; the final line says what the saved formula gave
// when the draft moves it.
function stageLines(keys, stored, live) {
  const shown = live || stored;
  if (!shown) return null;
  return keys.map((key) => {
    const row = shown[key];
    const isFinal = key === FINAL_KEY;
    const was = isFinal && live && stored && stored[FINAL_KEY].value !== row.value
      ? t('gradeFormula.liveWas', { score: stored[FINAL_KEY].value }) : null;
    return { label: row.label, value: row.value, final: isFinal, was };
  });
}

function SeverityKnobs({ draft, update }) {
  const w = draft.severityWeight;
  const setW = (sev) => (v) => update({ severityWeight: { ...w, [sev]: v } });
  const ratio = w.minor > 0 ? Math.round(w.critical / w.minor) : 0;
  return (
    <>
      <ParamSlider label={t('gradeFormula.weightCritical')} value={w.critical} min={SEVERITY_WEIGHT_MIN} max={SEVERITY_WEIGHT_MAX} step={SEVERITY_WEIGHT_STEP}
        hint={t('gradeFormula.hintCritical')} onChange={setW('critical')} />
      <ParamSlider label={t('gradeFormula.weightMajor')} value={w.major} min={SEVERITY_WEIGHT_MIN} max={SEVERITY_WEIGHT_MAX} step={SEVERITY_WEIGHT_STEP}
        hint={t('gradeFormula.hintMajor')} onChange={setW('major')} />
      <ParamSlider label={t('gradeFormula.weightMinor')} value={w.minor} min={SEVERITY_WEIGHT_MIN} max={SEVERITY_WEIGHT_MAX} step={SEVERITY_WEIGHT_STEP}
        hint={t('gradeFormula.hintMinor')} onChange={setW('minor')} />
      <span className="settings-description">
        {t('gradeFormula.criticalWeighs')} {ratio}{t('gradeFormula.timesMinor')}
      </span>
    </>
  );
}

function CeilingKnobs({ draft, update }) {
  return (
    <>
      <ParamSlider label={t('gradeFormula.ceilScale')} value={draft.ceilScale} min={0} max={2} step={0.05}
        hint={t('gradeFormula.hintCeil')} onChange={(v) => update({ ceilScale: v })} />
      <span className="settings-label">{t('gradeFormula.severityFloors')}</span>
      <ParamSlider label={t('gradeFormula.minorOnly')} value={draft.floorMinor} min={0} max={SCORE_SCALE_MAX} step={0.5}
        hint={t('gradeFormula.hintFloorMinor')} onChange={(v) => update({ floorMinor: v })} />
      <ParamSlider label={t('gradeFormula.floorMajor')} value={draft.floorMajor} min={0} max={SCORE_SCALE_MAX} step={0.5}
        hint={t('gradeFormula.hintFloorMajor')} onChange={(v) => update({ floorMajor: v })} />
      <span className="settings-description">{t('gradeFormula.criticalNoFloor')}</span>
    </>
  );
}

function GradeLabels({ draft, update }) {
  return (
    <div className="gf-labels">
      <span className="settings-label">{t('gradeFormula.gradeLabels')}</span>
      <span className="settings-description"> {t('gradeFormula.gradeLabelsDesc')}</span>
      <GradeBoundaryBar thresholds={draft.gradeThresholds} onChange={(next) => update({ gradeThresholds: next })} />
    </div>
  );
}

/**
 * The four scoring stages, each with its sliders and the picked principle's
 * numbers, then the grade labels.
 * @param {object} props.draft - the draft formula being edited
 * @param {(patch: object) => void} props.update - merges a patch into the draft
 * @param {{stored: Array|null, live: Array|null, note: string|null}} props.stages - liveStages() output
 */
export default function FormulaTab({ draft, update, stages }) {
  const stored = rowsByKey(stages.stored);
  const live = rowsByKey(stages.live);
  const liveOf = (n) => ({ lines: stageLines(STAGE_KEYS[n], stored, live), note: stages.note });
  return (
    <div className="gf-stages" aria-label={t('gradeFormula.stagesAria')}>
      <StageRow index={1} title={t('gradeFormula.stage1Title')} meaning={t('gradeFormula.stage1Meaning')} live={liveOf(STAGE_TYPES)}>
        <SeverityKnobs draft={draft} update={update} />
      </StageRow>
      <StageRow index={2} title={t('gradeFormula.stage2Title')} meaning={t('gradeFormula.stage2Meaning')} live={liveOf(STAGE_BASE)}>
        <ParamSlider label={t('gradeFormula.strictnessK')} value={draft.baseK} min={0.01} max={1} step={0.01}
          hint={t('gradeFormula.hintStrictness')} onChange={(v) => update({ baseK: v })} />
        <CurvePlot baseK={draft.baseK} ceilScale={draft.ceilScale} thresholds={draft.gradeThresholds} />
      </StageRow>
      <StageRow index={3} title={t('gradeFormula.stage3Title')} meaning={t('gradeFormula.stage3Meaning')} live={liveOf(STAGE_LIFT)}>
        <ParamSlider label={t('gradeFormula.liftCompress')} value={draft.liftCompress} min={1} max={4} step={0.1}
          hint={t('gradeFormula.hintLift')} onChange={(v) => update({ liftCompress: v })} />
      </StageRow>
      <StageRow index={4} title={t('gradeFormula.stage4Title')} meaning={t('gradeFormula.stage4Meaning')} live={liveOf(STAGE_CEILING)}>
        <CeilingKnobs draft={draft} update={update} />
      </StageRow>
      <GradeLabels draft={draft} update={update} />
    </div>
  );
}
