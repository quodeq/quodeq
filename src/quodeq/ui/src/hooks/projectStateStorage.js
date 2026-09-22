/**
 * useProjectState.js's localStorage read/write helpers and the boot-time
 * selection-resolution logic.
 */
import { PROJECT_SOURCE, DEFAULT_PROJECT_SOURCE } from '../constants.js';
import { writeString } from '../adapters/storage.js';

export const STORAGE_KEY = 'quodeq_selected_project';
export const SOURCE_STORAGE_KEY = 'quodeq_selected_source';
export const DEFAULT_SOURCE = DEFAULT_PROJECT_SOURCE;
export const VALID_SOURCES = Object.values(PROJECT_SOURCE);

/**
 * Set the selected project in React state and mirror it to storage. A storage
 * failure (private browsing) is warned about, not thrown: the in-memory
 * selection still stands for this session.
 */
export function persistProject(setter, name, storage = localStorage) {
  setter(name);
  const ok = writeString(STORAGE_KEY, name, storage);
  if (!ok) console.warn('[projectStateStorage] could not persist project'); // private browsing
}

/**
 * Normalizes and persists the project's source. Always paired with
 * persistProject in the same call so a stored project id is never left
 * alongside a stale/mismatched source after a restart.
 */
export function persistSource(setter, source, storage = localStorage) {
  const value = VALID_SOURCES.includes(source) ? source : DEFAULT_SOURCE;
  setter(value);
  const ok = writeString(SOURCE_STORAGE_KEY, value, storage);
  if (!ok) console.warn('[projectStateStorage] could not persist source'); // private browsing
}

/**
 * The project id selected in the last session, or '' when nothing is stored
 * or storage is unavailable.
 */
export function readStoredProject(storage = localStorage) {
  try {
    return storage.getItem(STORAGE_KEY) || '';
  } catch (err) {
    console.warn('[projectStateStorage] could not read stored project:', err);
    return '';
  }
}

/**
 * The source selected in the last session, falling back to DEFAULT_SOURCE for
 * anything unrecognised so a tampered or outdated value cannot select a source
 * that no longer exists.
 */
export function readStoredSource(storage = localStorage) {
  try {
    const stored = storage.getItem(SOURCE_STORAGE_KEY);
    return VALID_SOURCES.includes(stored) ? stored : DEFAULT_SOURCE;
  } catch (err) {
    console.warn('[projectStateStorage] could not read stored source:', err);
    return DEFAULT_SOURCE;
  }
}

/** Resolve which project to select from a loaded list, migrating stale storage if needed. */
export function resolveInitialProject({ list, currentProject, currentSource, onChangeProject, onNoProjects, storage }) {
  const current = currentProject || readStoredProject(storage);
  // `list` here is always the *local* project list (loadProjects only ever
  // calls the local listProjects API). A restored shared selection can't be
  // validated against it, so it must not be treated as "missing" and reset
  // to a local project + source 'local', which would silently undo the
  // user's shared selection on every restart. Leave it as restored; the
  // shared clone itself is fetched and validated by the shared-project data
  // hooks (useSharedProjects).
  if (currentSource === PROJECT_SOURCE.SHARED && current) return;
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
