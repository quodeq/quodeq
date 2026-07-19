/**
 * SharedReadOnlyBadge — "shared · read-only" chip shown on a shared
 * project's page header, plus (when known) a "published by <name>" sub
 * line. Shared projects have no mutation routes on the backend (dismiss/
 * restore/delete/evaluate are local-only by design), so this is purely
 * informational: it tells the user why the action buttons they'd normally
 * see are gone.
 */
export default function SharedReadOnlyBadge({ publishedBy }) {
  return (
    <span className="badge-shared-readonly-group">
      <span className="badge-shared-readonly" title="Shared projects are read-only in this app">
        shared · read-only
      </span>
      {publishedBy && (
        <span className="badge-shared-readonly-pub">published by {publishedBy}</span>
      )}
    </span>
  );
}
