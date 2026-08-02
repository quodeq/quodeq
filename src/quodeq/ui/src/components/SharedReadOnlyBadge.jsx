import Badge from './Badge.jsx';
import { t } from '../strings/index.js';

/**
 * SharedReadOnlyBadge — "remote · read-only" tag shown on a remote (team
 * repo) project's page headers, plus (when known) a "published by <name>"
 * sub line. Remote projects have no mutation routes on the backend
 * (dismiss/restore/delete/evaluate are local-only by design), so this is
 * purely informational: it tells the user why the action buttons they'd
 * normally see are gone. Display text says "remote"; the internal source
 * key stays 'shared'.
 */
export default function SharedReadOnlyBadge({ publishedBy }) {
  return (
    <span className="badge-shared-readonly-group">
      <Badge variant="tag" tone="info" title={t('common.remoteReadOnlyTitle')}>
        {t('common.remoteReadOnly')}
      </Badge>
      {publishedBy && (
        <span className="badge-shared-readonly-pub">{t('common.publishedBy')} {publishedBy}</span>
      )}
    </span>
  );
}
