/**
 * Custom-standard id/name business rules -- id auto-tracks name until the
 * user manually diverges it.
 *
 * Extracted from StandardDetail.jsx's name-field handler. Deliberately NOT
 * unified with the other two slugify implementations in this codebase
 * (SidePaneWindow.jsx, violationFixPlanSpec.jsx) -- those slugify filenames,
 * a different domain with different edge cases.
 */

/** Slugify a standard's display name into an id-safe string. */
export function slugify(text) {
  return text.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
}

/**
 * True when the standard's id should keep tracking its (about-to-change)
 * name: it's a brand-new standard whose id still equals the slug of its
 * current name (the user hasn't manually diverged it), or it has no id yet.
 *
 * An existing standard's id is its storage key (the update is sent to
 * `/api/standards/<id>`), so it never follows a rename.
 */
export function shouldSyncIdFromName(standard, isNew) {
  if (!standard.id) return true;
  return Boolean(isNew) && standard.id === slugify(standard.name || '');
}

/**
 * Field updates a name-field edit should apply: always the new name, plus
 * a re-synced id when `shouldSyncIdFromName` says the id hasn't manually
 * diverged. Returns `{ name }` or `{ name, id }`.
 */
export function applyNameChange(standard, name, isNew) {
  const updates = { name };
  if (shouldSyncIdFromName(standard, isNew)) {
    updates.id = slugify(name);
  }
  return updates;
}
