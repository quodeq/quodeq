import EmptyState from './EmptyState.jsx';
import { t } from '../strings/index.js';
import { NAV_TAB } from '../vocab/navTab.js';

/**
 * Project-level empty states the overview, history and violations pages show.
 * Each page keeps its own branch order and frame; only the content is shared.
 */

export function NoProjectsEmptyState({ onNavigate }) {
  return (
    <EmptyState
      title={t('overview.noProjectsTitle')}
      description={t('overview.noProjectsDesc')}
      actionLabel={t('overview.addProject')}
      onAction={() => onNavigate?.(NAV_TAB.PROJECTS)}
    />
  );
}

export function LoadProjectFailedEmptyState({ error, onRetry }) {
  return (
    <EmptyState
      title={t('overview.loadProjectFailedTitle')}
      description={error}
      actionLabel={t('overview.retry')}
      onAction={() => onRetry?.()}
    />
  );
}

/**
 * A shared project with no completed evaluation. Shared projects are read-only
 * in the app (evaluations only run locally), so there is no call to action.
 */
export function SharedNoCompletedEvalEmptyState() {
  return (
    <EmptyState
      title={t('overview.noCompletedEvalTitle')}
      description={t('overview.noCompletedEvalSharedDesc')}
    />
  );
}

export function NoEvalsEmptyState({ projectName, onNavigate }) {
  return (
    <EmptyState
      title={t('overview.noEvalsTitle')}
      description={t('overview.noEvalsDesc', { name: projectName })}
      actionLabel={t('overview.startEvaluation')}
      onAction={() => onNavigate?.(NAV_TAB.EVALUATE)}
    />
  );
}
