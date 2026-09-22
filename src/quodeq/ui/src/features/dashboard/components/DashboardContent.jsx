import DimensionCard from './DimensionCard.jsx';
import AccumulatedOverviewPanel from './AccumulatedOverviewPanel.jsx';
import RunOverviewPanel from './RunOverviewPanel.jsx';
import EmptyState from '../../../components/EmptyState.jsx';
import { t } from '../../../strings/index.js';

function NoCompletedEvalPanel({ availableRuns = [], onNavigate, selectedSource }) {
  const hasRunning = availableRuns.some((r) => r?.status === 'in_progress');
  if (hasRunning) {
    // First-ever evaluation is still running. There's no prior data to
    // show, but we still avoid claiming the project has "no" evaluations
    // — they just haven't finished yet.
    return (
      <EmptyState
        title={t('overview.firstEvalTitle')}
        description={t('overview.firstEvalDesc')}
        actionLabel={t('overview.openHistory')}
        onAction={() => onNavigate?.('history')}
      />
    );
  }
  // Shared projects are read-only in the app -- evaluations only ever run
  // locally (see api/shared.js's read-only-mirrors note), so the "Start
  // evaluation" CTA has nowhere useful to send a shared-project viewer. Show
  // the same empty shell without the button and with copy that doesn't imply
  // there's an action to take here.
  if (selectedSource === 'shared') {
    return (
      <EmptyState
        title={t('overview.noCompletedEvalTitle')}
        description={t('overview.noCompletedEvalSharedDesc')}
      />
    );
  }
  return (
    <EmptyState
      title={t('overview.noCompletedEvalTitle')}
      description={t('overview.noCompletedEvalDesc')}
      actionLabel={t('overview.startEvaluation')}
      onAction={() => onNavigate?.('evaluate')}
    />
  );
}

function DimensionFocusPanel({ focusedDimension, focusedDimensionData, setFocusedDimension }) {
  return (
    <div className="dimensions-panel">
      <div className="section-header">
        <h3 className="section-title">{focusedDimension}</h3>
        <button type="button" className="btn-secondary" onClick={() => setFocusedDimension(null)}>
          {t('overview.showAll')}
        </button>
      </div>
      <DimensionCard title={focusedDimension} dimension={focusedDimensionData} isSingleFocus={true} />
    </div>
  );
}

function AccumulatedContent({ data, callbacks }) {
  const { dashboard, accumulated, accumulatedDimensions, availableRuns, dailyRuns, overviewRunIndex, selectedRunId, selectedProject, projectInfo, granularity, selectedSource, scoresPending, customFormula } = data;
  const { onRunSelect, onAccumulatedDimensionClick, onNavigate, onGranularityChange } = callbacks;
  return (
    <AccumulatedOverviewPanel
      data={{
        accumulated: accumulated ? { ...accumulated, dimensions: accumulatedDimensions } : accumulated,
        accumulatedDimensions, availableRuns, dailyRuns, overviewRunIndex,
        trend: dashboard?.trend || [], selectedRunId, selectedProject, projectInfo, granularity, selectedSource,
        scoresPending, customFormula,
      }}
      callbacks={{
        onRunClick: onRunSelect, onDimensionClick: onAccumulatedDimensionClick, onNavigate, onGranularityChange,
      }}
    />
  );
}

// ---------------------------------------------------------------------------
// DashboardContent — the ready-state body of DashboardPage (run panel,
// accumulated overview, single-dimension focus, or the no-completed-eval
// empty state). Split out of DashboardPage.jsx to keep that file's
// early-return ladder under the file-size cap; behavior is unchanged.
// ---------------------------------------------------------------------------
export default function DashboardContent({ runMode, data, focus, callbacks }) {
  const { accumulatedDimensions, availableRuns, selectedProject, projectInfo, selectedSource } = data;
  const { dimension: focusedDimension, setDimension: setFocusedDimension, dimensionData: focusedDimensionData } = focus;
  const { onDimensionCardClick, onFileClick, onNavigate } = callbacks;
  // No readiness check here on purpose: the page only mounts this component
  // once contentReady is true (see DashboardPage's return), so there is
  // exactly one place in the whole page that decides whether a loader is
  // shown -- never a render decision split between here and the parent.
  if (runMode) {
    return (
      <RunOverviewPanel
        dashboard={data.dashboard}
        selectedRunId={data.selectedRunId}
        projectName={projectInfo?.displayName || projectInfo?.name || selectedProject}
        onDimensionClick={onDimensionCardClick}
        onFileClick={onFileClick}
        onNavigate={onNavigate}
      />
    );
  }
  if (accumulatedDimensions.length === 0) {
    // Project has runs (otherwise the upstream `!dashboard` empty
    // state would have fired) but none have terminated cleanly yet —
    // first evaluation in progress, or every prior attempt was
    // cancelled/failed. Render a clear waiting-for-results state in
    // place of the empty stat strip and dim cards (the page header
    // above still shows project name, language mix, file count).
    return <NoCompletedEvalPanel availableRuns={availableRuns} onNavigate={onNavigate} selectedSource={selectedSource} />;
  }
  if (focusedDimension) {
    return (
      <DimensionFocusPanel
        focusedDimension={focusedDimension}
        focusedDimensionData={focusedDimensionData}
        setFocusedDimension={setFocusedDimension}
      />
    );
  }
  return <AccumulatedContent data={data} callbacks={callbacks} />;
}
