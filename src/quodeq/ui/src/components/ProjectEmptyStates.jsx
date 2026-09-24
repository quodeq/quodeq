import EmptyState from './EmptyState.jsx';
import { t } from '../strings/index.js';

/**
 * Project-level empty states the overview and history pages both show.
 * Each page keeps its own branch order and frame; only the content is shared.
 */

export function NoProjectsEmptyState({ onNavigate }) {
  return (
    <EmptyState
      title={t('overview.noProjectsTitle')}
      description={t('overview.noProjectsDesc')}
      actionLabel={t('overview.addProject')}
      onAction={() => onNavigate?.('projects')}
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

export function NoEvalsEmptyState({ projectName, onNavigate }) {
  return (
    <EmptyState
      title={t('overview.noEvalsTitle')}
      description={t('overview.noEvalsDesc', { name: projectName })}
      actionLabel={t('overview.startEvaluation')}
      onAction={() => onNavigate?.('evaluate')}
    />
  );
}
