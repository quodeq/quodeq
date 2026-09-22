import EmptyState from '../../../components/EmptyState.jsx';
import HistorySkeleton from './HistorySkeleton.jsx';
import { TermHeader } from '../../../components/terminal/index.js';
import { t } from '../../../strings/index.js';

/**
 * HistoryPage.jsx's empty-state content pieces, extracted verbatim. The
 * conditional dispatch (which branch applies, in what order) stays in
 * HistoryPage.jsx itself -- only the per-branch content moved, matching the
 * DashboardPageEmptyStates.jsx precedent.
 */
export function HistoryEmptyShell({ sub, children, refreshing }) {
  return (
    <div className={`history-page history-page--terminal${refreshing ? ' dashboard-refreshing' : ''}`}>
      <TermHeader name={t('history.termName')} sub={sub} />
      {children}
    </div>
  );
}

export function NoProjectsEmptyContent({ onNavigate }) {
  return (
    <EmptyState
      title={t('overview.noProjectsTitle')}
      description={t('overview.noProjectsDesc')}
      actionLabel={t('overview.addProject')}
      onAction={() => onNavigate?.('projects')}
    />
  );
}

export function NoProjectSelectedEmptyContent({ onNavigate }) {
  return (
    <EmptyState
      title={t('overview.noProjectSelectedTitle')}
      description={t('history.noProjectSelectedDesc')}
      actionLabel={t('overview.chooseProject')}
      onAction={() => onNavigate?.('projects')}
    />
  );
}

export function LoadingEmptyContent() {
  return <HistorySkeleton />;
}

export function ErrorEmptyContent({ error, onRetry }) {
  return (
    <EmptyState
      title={t('overview.loadProjectFailedTitle')}
      description={error}
      actionLabel={t('overview.retry')}
      onAction={() => onRetry?.()}
    />
  );
}

export function SharedNoEvalsEmptyContent() {
  return (
    <EmptyState
      title={t('overview.noCompletedEvalTitle')}
      description={t('overview.noCompletedEvalSharedDesc')}
    />
  );
}

export function NoEvalsEmptyContent({ projectName, onNavigate }) {
  return (
    <EmptyState
      title={t('overview.noEvalsTitle')}
      description={t('overview.noEvalsDesc', { name: projectName })}
      actionLabel={t('overview.startEvaluation')}
      onAction={() => onNavigate?.('evaluate')}
    />
  );
}
