export const STORAGE_KEY = 'quodeq_selected_project';
export const SOURCE_STORAGE_KEY = 'quodeq_selected_source';
export const DEFAULT_SOURCE = 'local';
export const VALID_SOURCES = ['local', 'shared'];

/**
 * useProjectState.js's localStorage read/write helpers and the boot-time
 * selection-resolution logic. Extracted verbatim.
 */
export function persistProject(setter, name, storage = localStorage) {
  setter(name);
  try { storage.setItem(STORAGE_KEY, name); } catch { /* private browsing */ }
}

// Normalizes and persists the project's source. Always paired with
// persistProject in the same call so a stored project id is never left
// alongside a stale/mismatched source after a restart.
export function persistSource(setter, source, storage = localStorage) {
  const value = VALID_SOURCES.includes(source) ? source : DEFAULT_SOURCE;
  setter(value);
  try { storage.setItem(SOURCE_STORAGE_KEY, value); } catch { /* private browsing */ }
}

export function readStoredProject(storage = localStorage) {
  try { return storage.getItem(STORAGE_KEY) || ''; } catch { return ''; }
}

export function readStoredSource(storage = localStorage) {
  try {
    const stored = storage.getItem(SOURCE_STORAGE_KEY);
    return VALID_SOURCES.includes(stored) ? stored : DEFAULT_SOURCE;
  } catch { return DEFAULT_SOURCE; }
}

/** Resolve which project to select from a loaded list, migrating stale storage if needed. */
export function resolveInitialProject(list, currentProject, currentSource, onChangeProject, onNoProjects, storage) {
  const current = currentProject || readStoredProject(storage);
  // `list` here is always the *local* project list (loadProjects only ever
  // calls the local listProjects API). A restored shared selection can't be
  // validated against it, so it must not be treated as "missing" and reset
  // to a local project + source 'local' — that would silently undo the
  // user's shared selection on every restart. Leave it as restored; the
  // shared clone itself is fetched/validated by Task 17's data hooks.
  if (currentSource === 'shared' && current) return;
  if (list.length === 0) {
    if (onNoProjects) onNoProjects();
    return;
  }
  const match = current && list.find((p) => (p.id || p.name) === current);
  if (!match) {
    const pick = list[0].id || list[0].name || list[0];
    onChangeProject(pick);
  }
}
