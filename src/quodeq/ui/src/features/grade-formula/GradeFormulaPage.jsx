import { useState } from 'react';
import { TermHeader } from '../../components/terminal/index.js';
import useGradeFormula from './useGradeFormula.js';
import PreviewStrip from './PreviewStrip.jsx';
import {
  SeverityTab, CurveTab, BoundariesTab, DimensionsTab,
} from './tabs.jsx';
import { t } from '../../strings/index.js';

// labelKey, not label: the catalog is read at render so the tab strip picks
// up the active locale like every other visible string on the page.
const TABS = [
  { id: 'severity', labelKey: 'gradeFormula.tabSeverity', Body: SeverityTab },
  { id: 'curve', labelKey: 'gradeFormula.tabCurve', Body: CurveTab },
  { id: 'boundaries', labelKey: 'gradeFormula.tabBoundaries', Body: BoundariesTab },
  { id: 'dimensions', labelKey: 'gradeFormula.tabDimensions', Body: DimensionsTab },
];

// The tab `tab` state falls back to when it matches no TABS entry.
const DEFAULT_TAB_ID = TABS[0].id;

// A single panel is rendered at a time (swapped by active tab), so every tab
// button controls the same panel id; the panel in turn is labelled by
// whichever tab button is currently active.
const TAB_PANEL_ID = 'gf-tabpanel';

function tabButtonId(tabId) {
  return `gf-tab-${tabId}`;
}

function TabButtons({ tab, setTab }) {
  return (
    <div className="gf-tabs" role="tablist" aria-label={t('gradeFormula.tabsAria')}>
      {TABS.map((tabDef) => (
        <button
          key={tabDef.id}
          id={tabButtonId(tabDef.id)}
          type="button"
          role="tab"
          aria-selected={tab === tabDef.id}
          aria-controls={TAB_PANEL_ID}
          className={`gf-tab${tab === tabDef.id ? ' gf-tab--active' : ''}`}
          onClick={() => setTab(tabDef.id)}
        >
          {t(tabDef.labelKey)}
        </button>
      ))}
    </div>
  );
}

// Native fieldset disable cascades to every slider/button in the tab
// body, closing the mid-flight-edit window while an Apply/Reset is in
// progress (the hook captures `draft` at callback creation). The
// gf-tab-body class supplies the border/radius/padding; the inline
// reset only clears the browser fieldset's default margin and
// min-inline-size so it lays out like the plain div it replaces.
// NOTE: fieldset[disabled] only disables form controls, not custom
// div-based sliders. GradeBoundaryBar.startDrag guards against
// fieldset[disabled] in JS, and base.css adds pointer-events:none
// on .gf-tab-body:disabled .gf-boundary-divider as a CSS companion.
function TabBody({ busy, ActiveBody, draft, update, activeTabId }) {
  return (
    <fieldset
      id={TAB_PANEL_ID}
      className="gf-tab-body"
      role="tabpanel"
      aria-labelledby={tabButtonId(activeTabId)}
      disabled={busy}
      style={{ margin: 0, minInlineSize: 'auto' }}
    >
      <ActiveBody draft={draft} update={update} />
    </fieldset>
  );
}

function FormulaActions({ isDirty, busy, isCustom, error, partialNotice, onApply, onReset }) {
  return (
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
  );
}

// Both formula actions rescore every run, so each asks first and does
// nothing when the user declines.
function confirmThen(messageKey, action) {
  return async () => {
    if (window.confirm(t(messageKey))) await action();
  };
}

function makeOnApply(apply) {
  return confirmThen('gradeFormula.confirmApply', apply);
}

function makeOnReset(resetToDefaults) {
  return confirmThen('gradeFormula.confirmReset', resetToDefaults);
}

export default function GradeFormulaPage({ navigation }) {
  const projectId = navigation?.selectedProject || null;
  const [tab, setTab] = useState(DEFAULT_TAB_ID);
  const {
    draft, isCustom, isDirty, preview, busy, error, partialNotice, update, apply, resetToDefaults,
  } = useGradeFormula(projectId);

  const onApply = makeOnApply(apply);
  const onReset = makeOnReset(resetToDefaults);

  if (!draft) {
    return (
      <div className="settings-page settings-page--terminal">
        <TermHeader name={t('gradeFormula.headerName')} sub={t('gradeFormula.headerLoading')} />
        {error ? <p className="settings-description">{error}</p> : null}
      </div>
    );
  }

  // Fall back to the first tab rather than indexing into undefined if `tab`
  // ever holds a value that doesn't match any TABS entry.
  const ActiveBody = (TABS.find((t) => t.id === tab) ?? TABS[0]).Body;
  return (
    <div className="settings-page settings-page--terminal">
      <TermHeader
        name={t('gradeFormula.headerName')}
        sub={projectId ? t('gradeFormula.previewOf', { project: projectId }) : t('gradeFormula.noPreviewProject')}
      />
      <TabButtons tab={tab} setTab={setTab} />
      <TabBody busy={busy} ActiveBody={ActiveBody} draft={draft} update={update} activeTabId={tab} />
      <PreviewStrip
        preview={preview}
        emptyHint={projectId
          ? t('gradeFormula.noEventLog')
          : t('gradeFormula.selectForPreview')}
      />
      <FormulaActions
        isDirty={isDirty} busy={busy} isCustom={isCustom} error={error} partialNotice={partialNotice}
        onApply={onApply} onReset={onReset}
      />
      <p className="settings-description" style={{ marginTop: 8 }}>
        {t('gradeFormula.insufficientNote')}
      </p>
    </div>
  );
}
