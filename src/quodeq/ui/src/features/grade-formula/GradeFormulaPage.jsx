import { useState } from 'react';
import { TermHeader } from '../../components/terminal/index.js';
import useGradeFormula from './useGradeFormula.js';
import { useStageExplain } from './hooks/useStageExplain.js';
import { useTypesRows } from './hooks/useTypesRows.js';
import { useFullRunDimensions } from './hooks/useFullRunDimensions.js';
import { liveStages, pickPrincipleId } from './stages/liveStages.js';
import PreviewStrip from './PreviewStrip.jsx';
import FormulaTab from './FormulaTab.jsx';
import TypesTab from './TypesTab.jsx';
import GradeFormulaHeader from './GradeFormulaHeader.jsx';
import { FormulaActions, makeOnApply, makeOnReset } from './formulaActions.jsx';
import { DimensionsTab } from './tabs.jsx';
import { PROJECT_SOURCE } from '../../vocab/projectSource.js';
import { t } from '../../strings/index.js';

// labelKey, not label: the catalog is read at render so the tab strip picks
// up the active locale like every other visible string on the page.
const TABS = [
  { id: 'formula', labelKey: 'gradeFormula.tabFormula', Body: FormulaTab },
  { id: 'types', labelKey: 'gradeFormula.tabTypes', Body: TypesTab },
  { id: 'dimensions', labelKey: 'gradeFormula.tabDimensions', Body: DimensionsTab },
];

// The tab `tab` state falls back to when it matches no TABS entry.
const DEFAULT_TAB_ID = TABS[0].id;

// A single panel is rendered at a time (swapped by active tab), so every tab
// button controls the same panel id; the panel in turn is labelled by
// whichever tab button is currently active.
const TAB_PANEL_ID = 'gf-tabpanel';

/** What the page knows about the reader's project when it opens outside a run. */
export const EMPTY_SCOPE = Object.freeze({
  project: null, runId: null, dimensions: [], dimension: null, runDimensions: [], selectedSource: null,
});

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
// The fieldset is disabled only while the PUT/DELETE request itself is
// in flight, not while the background rescore pass runs after it lands:
// sliders stay usable and a second Apply restarts the pass.
function TabBody({ busy, ActiveBody, activeTabId, bodyProps }) {
  return (
    <fieldset
      id={TAB_PANEL_ID}
      className="gf-tab-body"
      role="tabpanel"
      aria-labelledby={tabButtonId(activeTabId)}
      disabled={busy}
      style={{ margin: 0, minInlineSize: 'auto' }}
    >
      <ActiveBody {...bodyProps} />
    </fieldset>
  );
}

// The dimension the worked example shows: the one the caller asked for when
// the run has it, else the run's first.
function knownDimension(scope, picked) {
  const wanted = picked || scope.dimension;
  if (wanted && scope.dimensions.includes(wanted)) return wanted;
  return scope.dimensions[0] || null;
}

// The worked example beside the sliders: the picked dimension and principle
// of the reader's run, with the stages under the saved and the draft formula.
function useWorkedExample(scope, draft) {
  const [pickedDimension, setDimension] = useState(null);
  const [pickedPrinciple, setPrincipleId] = useState(null);
  const dimension = knownDimension(scope, pickedDimension);
  // Shared repositories have no explain route: the sliders work, the column says so.
  const shared = scope.selectedSource === PROJECT_SOURCE.SHARED;
  const explain = useStageExplain({
    project: scope.project, runId: scope.runId, dimension, draft, enabled: Boolean(scope.runId) && !shared,
  });
  const principleId = pickPrincipleId(explain.principles, pickedPrinciple);
  return {
    dimension, setDimension, principleId, setPrincipleId,
    principles: explain.principles, stages: liveStages(explain, principleId, { shared }),
  };
}

// The TYPES tab's rows for the reader's run, and the dimension it is
// narrowed to.
function useTypesTab(scope, draft) {
  const [dimensionFilter, setDimensionFilter] = useState(null);
  // The root dashboard is the overview shape (no bodies) off run pages; the
  // TYPES rows count violations, so they read the full dashboard for the run.
  const runDimensions = useFullRunDimensions({
    project: scope.project, runId: scope.runId, source: scope.selectedSource, dimensions: scope.runDimensions,
  });
  const { rows, loading } = useTypesRows({
    project: scope.project, runId: scope.runId, dimensions: runDimensions,
    selectedSource: scope.selectedSource, draft,
  });
  return { rows, loading, dimensionFilter, setDimensionFilter, dimensions: scope.dimensions, noRun: !scope.runId };
}

function LoadingPage({ error }) {
  return (
    <div className="settings-page settings-page--terminal">
      <TermHeader name={t('gradeFormula.headerName')} sub={t('gradeFormula.headerLoading')} />
      {error ? <p className="settings-description">{error}</p> : null}
    </div>
  );
}

/**
 * Settings › Grade formula: the four scoring stages with the reader's own
 * numbers, the types table, the dimension weights, and APPLY / RESET.
 * @param {object} props.navigation - the app's navigation state (selectedProject)
 * @param {{project: string|null, runId: string|null, dimensions: string[], dimension: string|null, runDimensions: Array, selectedSource: string|null}} props.scope
 *   `dimensions` are names; `runDimensions` the dashboard's run dimensions with their findings.
 * @param {string|null} props.runLabel - the run's date for the header, when there is a run
 */
export default function GradeFormulaPage({ navigation, scope = EMPTY_SCOPE, runLabel = null }) {
  const projectId = navigation?.selectedProject || null;
  const [tab, setTab] = useState(DEFAULT_TAB_ID);
  const {
    draft, isCustom, isDirty, preview, busy, error, partialNotice, rescoreProgress,
    update, apply, resetToDefaults,
  } = useGradeFormula(projectId);
  const example = useWorkedExample(scope, draft);
  const types = useTypesTab(scope, draft);

  if (!draft) return <LoadingPage error={error} />;

  // Fall back to the first tab rather than indexing into undefined if `tab`
  // ever holds a value that doesn't match any TABS entry.
  const ActiveBody = (TABS.find((entry) => entry.id === tab) ?? TABS[0]).Body;
  return (
    <div className="settings-page settings-page--terminal">
      <GradeFormulaHeader
        scope={scope} runLabel={runLabel}
        dimension={example.dimension} setDimension={example.setDimension}
        principleId={example.principleId} setPrincipleId={example.setPrincipleId}
        principles={example.principles}
      />
      <TabButtons tab={tab} setTab={setTab} />
      <TabBody busy={busy} ActiveBody={ActiveBody} activeTabId={tab} bodyProps={{ draft, update, stages: example.stages, ...types }} />
      <PreviewStrip
        preview={preview}
        emptyHint={projectId
          ? t('gradeFormula.noEventLog')
          : t('gradeFormula.selectForPreview')}
      />
      <FormulaActions
        isDirty={isDirty} busy={busy} isCustom={isCustom} error={error} partialNotice={partialNotice}
        rescoreProgress={rescoreProgress} onApply={makeOnApply(apply)} onReset={makeOnReset(resetToDefaults)}
      />
      <p className="settings-description" style={{ marginTop: 8 }}>
        {t('gradeFormula.insufficientNote')}
      </p>
    </div>
  );
}
