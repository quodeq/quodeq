/**
 * Finding detail that /scores, /scores/<run> and a run's dimension eval defer.
 *
 * All three send violation and compliance items without `reason`, `snippet`,
 * `context` and `reqRefs` (flagged `detailDeferred`), since those fields are
 * most of their payload. Pages that render finding cards fetch the detail
 * from /compliance-detail (per kind; `?asOf=` for accumulated items, `?run=`
 * for one run's) and merge it back by identity.
 */
import { FINDING_TYPE } from '../vocab/findingType.js';
import { DEFAULT_PROJECT_SOURCE } from '../vocab/projectSource.js';

// The accumulated list each kind lives in.
const LIST_BY_KIND = Object.freeze({ [FINDING_TYPE.VIOLATION]: 'violations', [FINDING_TYPE.COMPLIANCE]: 'compliance' });

/**
 * Tag each deferred item with where its detail lives. One ref object per
 * dimension and kind, shared by its items. `generation` tells two /scores
 * responses for the same project and asOf apart, so detail cached for an
 * older payload is never merged into a newer one.
 * @param {Object} data Parsed unified scores payload (mutated and returned).
 * @param {string} project
 * @param {string|null} asOf
 * @param {number} generation
 * @returns {Object}
 */
export function attachFindingDetailRefs(data, project, asOf, generation) {
  for (const dim of data?.accumulated?.dimensions || []) {
    for (const [kind, list] of Object.entries(LIST_BY_KIND)) {
      const ref = { project, asOf: asOf || null, dimension: dim.dimension, generation, kind };
      for (const item of dim[list] || []) {
        if (item?.detailDeferred) item.detailRef = ref;
      }
    }
  }
  return data;
}

/** `attachFindingDetailRefs` under its pre-kind name. */
export const attachComplianceDetailRefs = attachFindingDetailRefs;

// Numbers each /scores/<run> and eval response (both sources), see attachFindingDetailRefs.
let runScoresGeneration = 0;

function attachRunRefs(node, project, run, source) {
  for (const [kind, list] of Object.entries(LIST_BY_KIND)) {
    const ref = { project, run, dimension: node.dimension, generation: runScoresGeneration, kind, source };
    for (const item of node[list] || []) {
      if (item?.detailDeferred) item.detailRef = ref;
    }
  }
}

/**
 * `attachFindingDetailRefs` for a run-scores payload: its items' detail
 * lives at `/compliance-detail?run=`, on the source the payload came from.
 * @param {Object} data Parsed run scores payload (mutated and returned).
 * @param {string} project
 * @param {string} run
 * @param {string} [source] PROJECT_SOURCE value.
 * @returns {Object}
 */
export function attachRunFindingDetailRefs(data, project, run, source = DEFAULT_PROJECT_SOURCE) {
  runScoresGeneration += 1;
  for (const dim of data?.dimensions || []) attachRunRefs(dim, project, run, source);
  return data;
}

/**
 * `attachRunFindingDetailRefs` for one dimension's eval payload: its flat
 * lists live at `/compliance-detail?run=` for the eval's run and dimension.
 * @param {Object} data Parsed dimension eval (mutated and returned).
 * @param {string} project
 * @param {string} run
 * @param {string} [source] PROJECT_SOURCE value.
 * @returns {Object}
 */
export function attachEvalFindingDetailRefs(data, project, run, source = DEFAULT_PROJECT_SOURCE) {
  if (!data?.dimension) return data;
  runScoresGeneration += 1;
  attachRunRefs(data, project, run, source);
  return data;
}

function commonPrefix(strings) {
  if (strings.length === 0) return '';
  let prefix = strings[0];
  for (const s of strings) {
    while (!s.startsWith(prefix)) prefix = prefix.slice(0, -1);
    if (!prefix) break;
  }
  return prefix;
}

/**
 * Group the deferred items by detail ref, each with the narrowest filter
 * that still covers them: their principle when they share one, and the
 * common prefix of their file paths.
 * @param {Array} items
 * @returns {Array<{ref: Object, scope: {principle: string|undefined, pathPrefix: string|undefined}}>}
 */
export function groupDeferredFindings(items) {
  const byRef = new Map();
  for (const item of items || []) {
    if (!item?.detailDeferred || !item.detailRef) continue;
    const group = byRef.get(item.detailRef) ?? [];
    group.push(item);
    byRef.set(item.detailRef, group);
  }
  return [...byRef].map(([ref, group]) => {
    const principles = new Set(group.map((i) => i.principle));
    const prefix = commonPrefix(group.map((i) => i.file || ''));
    return {
      ref,
      scope: {
        principle: principles.size === 1 ? [...principles][0] ?? undefined : undefined,
        pathPrefix: prefix || undefined,
      },
    };
  });
}

/** `groupDeferredFindings` under its pre-kind name. */
export const groupDeferredCompliance = groupDeferredFindings;

const identity = (i) => [i.file, i.line, i.endLine, i.principle, i.title].join('\u0000');

/**
 * Fill deferred items with the detail loaded for their ref. Items sharing an
 * identity take their details in server order, which is the order they
 * arrived in. Items with nothing loaded yet are returned as they were.
 * @param {Array} items
 * @param {Array<{ref: Object, items: Array}>} loaded
 * @returns {Array}
 */
export function mergeFindingDetail(items, loaded) {
  if (!loaded.length) return items;
  const queues = new Map();
  for (const { ref, items: details } of loaded) {
    const byIdentity = new Map();
    for (const d of details) {
      const key = identity(d);
      const same = byIdentity.get(key) ?? [];
      same.push(d);
      byIdentity.set(key, same);
    }
    queues.set(ref, byIdentity);
  }
  return items.map((item) => {
    const detail = item?.detailDeferred && queues.get(item.detailRef)?.get(identity(item))?.shift();
    if (!detail) return item;
    return { ...item, reason: detail.reason, snippet: detail.snippet, context: detail.context, reqRefs: detail.reqRefs, detailDeferred: false };
  });
}

/**
 * Flag deferred items whose detail fetch failed. They leave the deferred
 * state (so nothing reads them as still loading) and carry
 * `detailUnavailable`, which the cards turn into a note.
 * @param {Array} items
 * @param {Array<Object>} failedRefs Detail refs whose fetch errored.
 * @returns {Array}
 */
export function markDetailUnavailable(items, failedRefs) {
  if (!failedRefs.length) return items;
  return items.map((item) => (
    item?.detailDeferred && failedRefs.includes(item.detailRef)
      ? { ...item, detailDeferred: false, detailUnavailable: true }
      : item
  ));
}

/** `mergeFindingDetail` under its pre-kind name. */
export const mergeComplianceDetail = mergeFindingDetail;
