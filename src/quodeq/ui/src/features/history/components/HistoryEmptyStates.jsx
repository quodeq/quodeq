import EmptyState from '../../../components/EmptyState.jsx';
import HistorySkeleton from './HistorySkeleton.jsx';
import { TermHeader } from '../../../components/terminal/index.js';
import { t } from '../../../strings/index.js';
import { NAV_TAB } from '../../../vocab/navTab.js';

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

export function NoProjectSelectedEmptyContent({ onNavigate }) {
  return (
    <EmptyState
      title={t('overview.noProjectSelectedTitle')}
      description={t('history.noProjectSelectedDesc')}
      actionLabel={t('overview.chooseProject')}
      onAction={() => onNavigate?.(NAV_TAB.PROJECTS)}
    />
  );
}

export function LoadingEmptyContent() {
  return <HistorySkeleton />;
}

export function SharedNoEvalsEmptyContent() {
  return (
    <EmptyState
      title={t('overview.noCompletedEvalTitle')}
      description={t('overview.noCompletedEvalSharedDesc')}
    />
  );
}
