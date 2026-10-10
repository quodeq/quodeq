/**
 * The Dismissed tab's list in the query cache, patched from a dismiss.
 *
 * A dismiss POST answers with `dismissedEntry`, the item the listing would
 * show for the finding. Prepending it here puts the finding in the tab the
 * moment the dismiss succeeds; the reconcile that follows every suppression
 * mutation refetches the list, so the server's own order wins shortly after.
 */
import { projectKeys } from './queryKeys.js';

/** One identity per listed entry: the recorded fingerprint, else the line. */
export function dismissedEntryId(entry) {
  return `${entry.req}|${entry.file}|${entry.fingerprint || `line:${entry.line}`}`;
}

/**
 * Prepend `entry` to the cached list of `project` when a list is cached and
 * the entry is not in it yet. With nothing cached the first open of the tab
 * fetches the list, entry included, so there is nothing to patch.
 */
export function recordDismissedEntry(queryClient, project, source, entry) {
  if (!project || !entry) return;
  const queryKey = projectKeys.dismissed(project, source);
  const current = queryClient.getQueryData(queryKey);
  if (!Array.isArray(current)) return;
  const id = dismissedEntryId(entry);
  if (current.some((d) => dismissedEntryId(d) === id)) return;
  queryClient.setQueryData(queryKey, [entry, ...current]);
}
