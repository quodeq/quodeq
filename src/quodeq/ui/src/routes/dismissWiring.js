/**
 * Source gating and dismiss wiring for the detail routes.
 *
 * A shared-repository project is read-only: the routes hide their dismiss
 * affordance rather than wiring a handler that must never fire. Three routes
 * (file, evalprinciple, finding) make that call the same way, and each has to
 * dismiss into the project the finding belongs to rather than the global
 * selection — so the gate, the project lookup and the handler shape live
 * here, once.
 */
import { dismissWithReconcile } from '../features/findings/dismissFlow.js';
import { PROJECT_SOURCE } from '../vocab/projectSource.js';

/**
 * Whether the selection points at the shared repository mirror.
 *
 * @param {string|undefined} selectedSource
 * @returns {boolean}
 */
export function isSharedSource(selectedSource) {
  return selectedSource === PROJECT_SOURCE.SHARED;
}

/**
 * The onDismiss handler a detail route passes down, or undefined for a
 * shared-source project.
 *
 * @param {Object} options Everything dismissWithReconcile needs, plus
 *   `selectedSource` — the source the gate is read from.
 * @returns {Function|undefined}
 */
export function makeDismissHandler({ selectedSource, ...rest }) {
  if (isSharedSource(selectedSource)) return undefined;
  return (violation) => dismissWithReconcile({ violation, ...rest });
}
