import { useState } from 'react';
import { TermHeader } from '../../components/terminal/index.js';
import useGradeFormula from './useGradeFormula.js';
import PreviewStrip from './PreviewStrip.jsx';
import {
  SeverityTab, CurveTab, BoundariesTab, DimensionsTab,
} from './tabs.jsx';
import { t } from '../../strings/index.js';

const TABS = [
  { id: 'severity', label: 'SEVERITY', Body: SeverityTab },
  { id: 'curve', label: 'CURVE', Body: CurveTab },
  { id: 'boundaries', label: 'BOUNDARIES', Body: BoundariesTab },
  { id: 'dimensions', label: 'DIMENSIONS', Body: DimensionsTab },
];

export default function GradeFormulaPage({ navigation }) {
  const projectId = navigation?.selectedProject || null;
  const [tab, setTab] = useState('severity');
  const {
    draft, isCustom, isDirty, preview, busy, error, partialNotice, update, apply, resetToDefaults,
  } = useGradeFormula(projectId);

  const onApply = async () => {
    const ok = window.confirm(
      t('gradeFormula.confirmApply'),
    );
    if (ok) await apply();
  };

  const onReset = async () => {
    const ok = window.confirm(
      t('gradeFormula.confirmReset'),
    );
    if (ok) await resetToDefaults();
  };

  if (!draft) {
    return (
      <div className="settings-page settings-page--terminal">
        <TermHeader name="grade formula" sub="loading" />
        {error ? <p className="settings-description">{error}</p> : null}
      </div>
    );
  }

  const ActiveBody = TABS.find((t) => t.id === tab).Body;
  return (
    <div className="settings-page settings-page--terminal">
      <TermHeader
        name="grade formula"
        sub={projectId ? t('gradeFormula.previewOf', { project: projectId }) : t('gradeFormula.noPreviewProject')}
      />
      <div className="gf-tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`gf-tab${tab === t.id ? ' gf-tab--active' : ''}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>
      {/* Native fieldset disable cascades to every slider/button in the tab
          body, closing the mid-flight-edit window while an Apply/Reset is in
          progress (the hook captures `draft` at callback creation). The
          gf-tab-body class supplies the border/radius/padding; the inline
          reset only clears the browser fieldset's default margin and
          min-inline-size so it lays out like the plain div it replaces.
          NOTE: fieldset[disabled] only disables form controls, not custom
          div-based sliders. GradeBoundaryBar.startDrag guards against
          fieldset[disabled] in JS, and base.css adds pointer-events:none
          on .gf-tab-body:disabled .gf-boundary-divider as a CSS companion. */}
      <fieldset
        className="gf-tab-body"
        disabled={busy}
        style={{ margin: 0, minInlineSize: 'auto' }}
      >
        <ActiveBody draft={draft} update={update} />
      </fieldset>
      <PreviewStrip
        preview={preview}
        emptyHint={projectId
          ? t('gradeFormula.noEventLog')
          : t('gradeFormula.selectForPreview')}
      />
      <div className="gf-actions">
        <button
          type="button"
          className="settings-pill settings-pill--active"
          disabled={!isDirty || busy}
          onClick={onApply}
        >
          {t('gradeFormula.apply')}
        </button>
        <button type="button" className="settings-pill" disabled={busy} onClick={onReset}>
          {t('gradeFormula.resetQ')}
        </button>
        <span className="gf-dirty-hint">
          {isDirty ? t('gradeFormula.unsavedHint')
            : isCustom ? t('gradeFormula.customActive') : t('gradeFormula.defaultsActive')}
        </span>
        {error ? <span className="gf-dirty-hint">{error}</span> : null}
        {partialNotice ? <span className="gf-dirty-hint" role="alert">{partialNotice}</span> : null}
      </div>
      <p className="settings-description" style={{ marginTop: 8 }}>
        {t('gradeFormula.insufficientNote')}
      </p>
    </div>
  );
}
