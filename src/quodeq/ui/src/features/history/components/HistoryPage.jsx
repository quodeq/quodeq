import { useMemo } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import { useRunningRunsRefresh } from '../../../hooks/useRunningRunsRefresh.js';
import { useRunNavigator } from '../../../hooks/useRunNavigator.js';
import { usePrefetchRun } from '../../dashboard/hooks/usePrefetchRun.js';
import { readVisibleStandardIds } from '../../../utils/visibleStandards.js';
import { filterTrendByVisibleStandards } from '../../../utils/scoreFiltering.js';
import LoadingScreen from '../../../components/LoadingScreen.jsx';
import { t, LOCALE } from '../../../strings/index.js';
import { useHistoryDeleteRun } from '../hooks/useHistoryDeleteRun.js';
import { HistoryContent } from './HistoryContent.jsx';
import {
  HistoryEmptyShell, NoProjectsEmptyContent, NoProjectSelectedEmptyContent,
  LoadingEmptyContent, ErrorEmptyContent, SharedNoEvalsEmptyContent, NoEvalsEmptyContent,
} from './HistoryEmptyStates.jsx';
import { assembleHistoryRows, visibleHistoryRows } from './historyRowAssembly.js';

export { assembleHistoryRows, visibleHistoryRows };

function useHistoryRunNavLabel(trend, currentOverviewRun) {
  return useMemo(() => {
    const entry = (trend || []).find((r) => r.runId === currentOverviewRun);
    if (entry?.dateISO) {
      try {
        const d = new Date(entry.dateISO);
        return d.toLocaleDateString(LOCALE, { day: 'numeric', month: 'long', year: 'numeric' }) + ' ' + d.toLocaleTimeString(LOCALE, { hour: '2-digit', minute: '2-digit' });
      } catch { return entry.dateISO || ''; }
    }
    return entry?.dateLabel || currentOverviewRun;
  }, [trend, currentOverviewRun]);
}

function useHistoryLanguageSub(projectInfo) {
  return useMemo(() => {
    const stats = projectInfo?.languageStats;
    if (!stats) return null;
    const sorted = Object.entries(stats).sort(([, a], [, b]) => b - a).slice(0, 5);
    if (sorted.length === 0) return null;
    return sorted.map(([lang, count]) => `${count} ${lang.toLowerCase()}`).join('  ');
  }, [projectInfo]);
}

// The "no rows to show" branch of the empty-state dispatch (loading / error /
// shared-no-evals / generic-no-evals), split out of renderHistoryEmptyState
// purely to fit the size ratchet's per-function line cap -- same logic,
// same order, same conditions.
function renderNoRowsEmptyState({
  selectedSource, loading, error, isFetching, isRefreshing, projectInfo, selectedProject, onNavigate, onRetry,
}) {
  if (loading) {
    return <HistoryEmptyShell sub={t('overview.loading')}><LoadingEmptyContent /></HistoryEmptyShell>;
  }
  // A failed fetch with nothing to show must render as an error, not the
  // "no evaluations yet" empty state -- otherwise a 404/500/timeout tells
  // the user their existing evaluations are gone. While a retry is in
  // flight (error still set, isFetching true), show the loader instead so
  // clicking Retry visibly does something.
  if (error) {
    if (isFetching) {
      return <HistoryEmptyShell sub={t('overview.loading')}><LoadingEmptyContent /></HistoryEmptyShell>;
    }
    return (
      <HistoryEmptyShell sub={t('violations.subError')}>
        <ErrorEmptyContent error={error} onRetry={onRetry} />
      </HistoryEmptyShell>
    );
  }
  // Shared projects are read-only in the app -- evaluations only ever run
  // locally, so "Start evaluation" has nowhere useful to send a
  // shared-project viewer (see DashboardPage's NoCompletedEvalPanel, the
  // precedent this mirrors).
  if (selectedSource === 'shared') {
    return (
      <HistoryEmptyShell sub={t('violations.subNoEvals')} refreshing={isRefreshing}>
        <SharedNoEvalsEmptyContent />
      </HistoryEmptyShell>
    );
  }
  const projectName = projectInfo?.displayName || projectInfo?.name || selectedProject;
  return (
    <HistoryEmptyShell sub={t('violations.subNoEvals')} refreshing={isRefreshing}>
      <NoEvalsEmptyContent projectName={projectName} onNavigate={onNavigate} />
    </HistoryEmptyShell>
  );
}

// Empty-state dispatch: which branch applies, and in what order. Mirrors
// the original inline conditional chain 1:1 -- only the per-branch content
// moved, into HistoryEmptyStates.jsx (see that file's header comment).
function renderHistoryEmptyState({
  projectsLoaded, projects, selectedSource, selectedProject, onNavigate,
  availableRuns, trend, loading, error, isFetching, isRefreshing, projectInfo, onRetry,
}) {
  if (!projectsLoaded) return <LoadingScreen />;
  // The LOCAL projects list can legitimately be empty while a teammate is
  // viewing a shared project (they may have never added a local project of
  // their own) -- gate this wall on the local list only for local selections,
  // so a shared selection falls through to the normal shared data flow below.
  if (projects.length === 0 && selectedSource !== 'shared') {
    return (
      <HistoryEmptyShell sub={t('violations.subNoProjects')}>
        <NoProjectsEmptyContent onNavigate={onNavigate} />
      </HistoryEmptyShell>
    );
  }
  if (!selectedProject) {
    return (
      <HistoryEmptyShell sub={t('violations.subNoProjectSelected')}>
        <NoProjectSelectedEmptyContent onNavigate={onNavigate} />
      </HistoryEmptyShell>
    );
  }
  // Guard on the rows the table will actually show (trend + cancelled +
  // in-progress, minus hidden failures), not just `trend`. A project whose
  // only runs are cancelled has an empty trend but real rows to list, and
  // its scores already show on the Overview.
  if (visibleHistoryRows(availableRuns, trend).length === 0) {
    return renderNoRowsEmptyState({
      selectedSource, loading, error, isFetching, isRefreshing, projectInfo, selectedProject, onNavigate, onRetry,
    });
  }
  return null;
}

export default function HistoryPage({ trend: rawTrend, selection, availableRuns, dimensions, callbacks, projectInfo, projects = [], projectsLoaded, selectedProject, selectedSource = 'local', loading, isFetching, error, onRetry }) {
  const { selectedRunId } = selection;
  const { onRunClick, onDimensionClick, onNavigate, onRunChange, onRunDeleted } = callbacks;
  const { deleteEvaluation } = useApi();
  // Background refresh while a run is alive so the running row flips
  // to "complete" without the user manually reloading. Scoped to this
  // page only — other tabs don't poll.
  useRunningRunsRefresh({ selectedProject, selectedSource, availableRuns });
  // Warm the run-detail cache on row hover so clicking through is instant.
  const { prefetchRun, cancelPrefetch } = usePrefetchRun(selectedProject, selectedSource);
  const visibleSet = useMemo(() => new Set(readVisibleStandardIds()), []);
  const trend = useMemo(() => filterTrendByVisibleStandards(rawTrend || [], visibleSet), [rawTrend, visibleSet]);

  const handleDeleteRun = useHistoryDeleteRun({ selectedSource, deleteEvaluation, onRunDeleted });

  const { overviewRunIndex, currentOverviewRun, handleRunPrev, handleRunNext, handleRunLatest } = useRunNavigator({
    selectedRun: selectedRunId || 'latest',
    availableRuns: availableRuns || [],
    onRunChange: onRunChange || (() => {}),
    onNavigate: onNavigate || (() => {}),
  });

  const runNavLabel = useHistoryRunNavLabel(trend, currentOverviewRun);
  const languageSub = useHistoryLanguageSub(projectInfo);

  const isRefreshing = isFetching && !loading;
  const emptyState = renderHistoryEmptyState({
    projectsLoaded, projects, selectedSource, selectedProject, onNavigate,
    availableRuns, trend, loading, error, isFetching, isRefreshing, projectInfo, onRetry,
  });
  if (emptyState) return emptyState;

  return (
    <HistoryContent
      data={{ trend, selectedRunId, availableRuns }}
      isRefreshing={isRefreshing}
      callbacks={{
        onRunClick, onRunHover: prefetchRun, onRunHoverEnd: cancelPrefetch, onRunChange,
        // Shared-repo runs have no delete route on the backend (mutation is
        // local-only by design). Passing undefined here — rather than always
        // handleDeleteRun — is what makes the row's delete button vanish,
        // since HistoryRow already gates on `{onDelete && ...}`.
        onDeleteRun: selectedSource === 'local' ? handleDeleteRun : undefined,
      }}
      runNav={{ runNavLabel, overviewRunIndex, currentOverviewRun, handleRunPrev, handleRunNext, handleRunLatest }}
      languageSub={languageSub}
      selectedSource={selectedSource}
    />
  );
}
