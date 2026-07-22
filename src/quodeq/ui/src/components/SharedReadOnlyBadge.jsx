import Badge from './Badge.jsx';

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
      <Badge variant="tag" tone="info" title="Remote projects are read-only in this app">
        remote · read-only
      </Badge>
      {publishedBy && (
        <span className="badge-shared-readonly-pub">published by {publishedBy}</span>
      )}
    </span>
  );
}
