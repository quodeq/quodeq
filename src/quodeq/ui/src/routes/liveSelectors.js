/**
 * Selectors that let the File and Principle pages render the LIVE payload.
 *
 * The Violations tab's navigation used to hand those pages an object built
 * from the /scores payload the client held at click time (a dimension's
 * findings aggregated into a synthetic file, a principle with its lists).
 * That snapshot lived in the nav params and never changed, while the
 * finding detail is fetched from the server's current state; a finding
 * re-reported since (new title, shifted lines) then had no detail row and
 * its card showed only a title. The navigation now also leaves a small
 * selector, and the renderers rebuild the object from the live payload when
 * one is present, so a refreshed /scores reaches the page. The snapshot
 * stays as the fallback for callers that pass none.
 */
import { buildProjectRootFile } from '../utils/explorerUtils.js';
import { typeFile } from '../features/violations/byTypeModel.js';
import { folderDimensions } from '../features/dashboard/findingsGrouping.js';

/**
 * What a `fileSelector` points at: a whole dimension, one requirement code of
 * it, or one folder across the dimensions on show.
 */
export const FILE_SELECTOR_KIND = Object.freeze({ DIMENSION: 'dimension', TYPE: 'type', FOLDER: 'folder' });

/**
 * The accumulated payload the routes render from: the latest one when the
 * app holds it, else the selected run's.
 * @param {Object} props route props (`props.dashboardData`)
 * @returns {Object|null}
 */
export function liveAccumulated(props) {
  return props?.dashboardData?.latestAccumulated || props?.dashboardData?.accumulated || null;
}

function dimensionNamed(accumulated, name) {
  return (accumulated?.dimensions || []).find((d) => d.dimension === name) || null;
}

/**
 * The evalPrincipal object the Principle page renders, from a principle row
 * and its grade. Exported so unit tests can pin the runId-threading
 * contract without mounting the whole App: callers from the Violations page
 * must pass the dimension's `fromRunId`, see `makeNavigateToPrinciple` in
 * routes/violationsRoute.jsx for the regression history.
 * @param {{ principle: string, dimension?: string, violations?: Array, compliance?: Array }} principleObj
 * @param {{ score?: number, grade?: string }|undefined} principleGrade
 * @param {string|undefined} runId
 * @returns {Object}
 */
export function buildEvalPrincipal(principleObj, principleGrade, runId) {
  const violations = principleObj.violations || [];
  const compliance = principleObj.compliance || [];
  return {
    principle: principleObj.principle,
    score: principleGrade?.score ?? null,
    grade: principleGrade?.grade || null,
    confidence: principleGrade?.confidence,
    dimension: principleObj.dimension || '',
    runId: runId || '',
    principleData: {
      name: principleObj.principle,
      grade: principleGrade?.grade || null,
      violations,
      compliance,
    },
    dimViolations: violations,
    dimCompliance: compliance,
  };
}

/**
 * One folder's findings across the selector's dimensions, or null when the
 * payload is missing or the folder no longer has any.
 */
function liveFolderFile(selector, accumulated) {
  if (!accumulated) return null;
  const wanted = new Set(selector.dimensions || []);
  const dims = (accumulated.dimensions || []).filter((d) => wanted.has(d.dimension));
  const parts = folderDimensions(dims, selector.dir);
  return parts.length ? buildProjectRootFile(parts, selector.label || selector.dir) : null;
}

/**
 * The File page's file rebuilt from the live payload, or null when the nav
 * params carry no selector, there is no payload, or the dimension is gone
 * (the caller then renders the snapshot).
 * @param {{ fileSelector?: { kind: string, dimension?: string, req?: string, text?: string, dir?: string, dimensions?: string[], label?: string } }} params
 * @param {Object|null} accumulated
 * @returns {Object|null}
 */
export function liveFileFor(params, accumulated) {
  const selector = params?.fileSelector;
  if (selector?.kind === FILE_SELECTOR_KIND.FOLDER) return liveFolderFile(selector, accumulated);
  const dim = selector ? dimensionNamed(accumulated, selector.dimension) : null;
  if (!dim) return null;
  if (selector.kind === FILE_SELECTOR_KIND.TYPE) {
    const violations = (dim.violations || []).filter((v) => v.req === selector.req);
    return typeFile({ violations }, dim, `${selector.req} · ${selector.text || dim.dimension}`);
  }
  return buildProjectRootFile([dim], dim.dimension);
}

/**
 * The Principle page's evalPrincipal rebuilt from the live payload, or null
 * when the nav params carry no selector or the principle is gone from the
 * dimension (no grade and no findings).
 * @param {{ principleSelector?: { dimension: string, principle: string } }} params
 * @param {Object|null} accumulated
 * @returns {Object|null}
 */
export function liveEvalPrincipalFor(params, accumulated) {
  const selector = params?.principleSelector;
  const dim = selector ? dimensionNamed(accumulated, selector.dimension) : null;
  if (!dim) return null;
  const { principle } = selector;
  const grade = (dim.principles || []).find((p) => (p.name ?? p.principle) === principle);
  const violations = (dim.violations || []).filter((v) => v.principle === principle);
  const compliance = (dim.compliance || []).filter((c) => c.principle === principle);
  if (!grade && !violations.length && !compliance.length) return null;
  return buildEvalPrincipal({ principle, dimension: dim.dimension, violations, compliance }, grade, dim.fromRunId);
}
