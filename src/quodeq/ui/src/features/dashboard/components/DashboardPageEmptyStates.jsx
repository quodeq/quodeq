import IncompleteSetupCard from './IncompleteSetupCard.jsx';
import LoadingScreen from '../../../components/LoadingScreen.jsx';
import EmptyState from '../../../components/EmptyState.jsx';
import { t } from '../../../strings/index.js';

// These render only the *contents* of DashboardPage's `.dashboard-page` div
// for each early-return branch -- never the `<>{null}<div className=...>`
// wrapper itself. That wrapper must stay a literal, inline Fragment in
// DashboardPage.jsx for every branch: if one branch's wrapper were hidden
// behind a component boundary (e.g. `<SomeState/>`) while another branch
// returns the Fragment directly, switching between them changes the react
// element *type* at DashboardPage's own return position (component vs
// Fragment), which makes React tear down and remount the whole subtree --
// losing the `.dashboard-page` DOM node identity that P3-T2's frame-
// stability tests assert on. The div's children can freely change type
// across branches (that's normal reconciliation); only the div+Fragment
// shell itself must stay put.

export function ProjectsLoadFailedState({ onRetry }) {
  return (
    <EmptyState
      title={t('overview.projectsLoadFailedTitle')}
      description={t('overview.projectsLoadFailedDesc')}
      actionLabel={t('overview.retry')}
      onAction={() => onRetry?.()}
    />
  );
}

export function NoLocalProjectsSharedContent({ onNavigate }) {
  return (
    <EmptyState
      title={t('overview.noLocalProjectsTitle')}
      description={t('overview.noLocalProjectsDesc')}
      actionLabel={t('overview.browseRemote')}
      onAction={() => onNavigate?.('projects')}
    />
  );
}

export function NoProjectsContent({ onNavigate }) {
  return (
    <EmptyState
      title={t('overview.noProjectsTitle')}
      description={t('overview.noProjectsDesc')}
      actionLabel={t('overview.addProject')}
      onAction={() => onNavigate?.('projects')}
    />
  );
}

export function NoProjectSelectedContent({ onNavigate }) {
  return (
    <EmptyState
      title={t('overview.noProjectSelectedTitle')}
      description={t('overview.noProjectSelectedDesc')}
      actionLabel={t('overview.chooseProject')}
      onAction={() => onNavigate?.('projects')}
    />
  );
}

// Shared by both call sites that show the inline loader while a retry is in
// flight: the failed-fetch branch (error set, isFetching true) and the
// runMode empty-response branch (no error, isFetching true). Same markup.
export function LoadingProjectContent({ projectName }) {
  return (
    <LoadingScreen variant="inline" message={projectName ? t('overview.loadingProjectMsg', { name: projectName }) : undefined} />
  );
}

export function LoadProjectFailedContent({ error, onRetry }) {
  return (
    <EmptyState
      title={t('overview.loadProjectFailedTitle')}
      description={error}
      actionLabel={t('overview.retry')}
      onAction={() => onRetry?.()}
    />
  );
}

// Covers both the settled no-runs state and a background refetch of an
// empty project (isFetching true, dashboard still null -- previously a
// visually blank .dashboard-page with no dim and no loader), plus the
// post-eval selectedRun flip while the sticky latch is active (loading
// true, dashboard still null): stay here, dimmed, until the payload lands
// rather than swapping to the full inline loader and back.
export function NoRunsEmptyContent({ projectInfo, onComplete, projectName, onNavigate }) {
  return (
    <>
      <IncompleteSetupCard projectInfo={projectInfo} onComplete={onComplete} />
      <EmptyState
        title={t('overview.noEvalsTitle')}
        description={t('overview.noEvalsDesc', { name: projectName })}
        actionLabel={t('overview.startEvaluation')}
        onAction={() => onNavigate?.('evaluate')}
      />
    </>
  );
}

export function RunLoadFailedContent({ onRetry }) {
  return (
    <EmptyState
      title={t('overview.loadRunFailedTitle')}
      description={t('overview.loadRunFailedDesc')}
      actionLabel={t('overview.retry')}
      onAction={() => onRetry?.()}
    />
  );
}
