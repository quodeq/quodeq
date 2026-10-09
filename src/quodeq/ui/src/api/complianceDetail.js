/**
 * Finding detail that /scores, /scores/<run> and a run's dimension eval defer.
 *
 * All three send violation and compliance items without `reason`, `snippet`,
 * `context` and `reqRefs` (flagged `detailDeferred`): those fields are most
 * of their payload, and only the File, Principle and Finding pages and the
 * reports render them. Those pages ask /compliance-detail for the rows they
 * show (per dimension and kind; `?asOf=` for accumulated items, `?run=` for
 * one run's) and the answer REPLACES the deferred items: the list payload
 * says what to ask for, the detail answer is what the page renders. Nothing
 * is matched back by identity, so a finding the server re-reported under a
 * new title or at a shifted line shows as it is now.
 */
import { FINDING_TYPE } from '../vocab/findingType.js';
import { DEFAULT_PROJECT_SOURCE } from '../vocab/projectSource.js';

// The accumulated list each kind lives in.
const LIST_BY_KIND = Object.freeze({ [FINDING_TYPE.VIOLATION]: 'violations', [FINDING_TYPE.COMPLIANCE]: 'compliance' });

/**
 * Tag each deferred item with where its detail lives: one ref object per
 * dimension and kind, shared by its items. A ref names content (project,
 * as-of run, dimension, kind), never the response it came from, so the
 * detail fetched for one /scores response serves the next one too.
 * @param {Object} data Parsed unified scores payload (mutated and returned).
 * @param {string} project
 * @param {string|null} asOf
 * @returns {Object}
 */
export function attachFindingDetailRefs(data, project, asOf) {
  for (const dim of data?.accumulated?.dimensions || []) {
    for (const [kind, list] of Object.entries(LIST_BY_KIND)) {
      const ref = { project, asOf: asOf || null, dimension: dim.dimension, kind };
      for (const item of dim[list] || []) {
        if (item?.detailDeferred) item.detailRef = ref;
      }
    }
  }
  return data;
}

/** `attachFindingDetailRefs` under its pre-kind name. */
export const attachComplianceDetailRefs = attachFindingDetailRefs;

function attachRunRefs(node, project, run, source) {
  for (const [kind, list] of Object.entries(LIST_BY_KIND)) {
    const ref = { project, run, dimension: node.dimension, kind, source };
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
  attachRunRefs(data, project, run, source);
  return data;
}

/**
 * What a detail ref names, as a map key. Refs are matched by content, never
 * by identity: every /scores payload builds its own ref objects
 * (attachFindingDetailRefs), and react-query's structural sharing hands the
 * hydration hook the previous payload's objects back whenever the new ones
 * say the same thing. Matched by identity, an unchanged group's deferred
 * items stayed deferred after a refetch until the page was reopened.
 * @param {Object} ref
 * @returns {string}
 */
export function detailRefKey(ref) {
  return [ref.project, ref.source ?? '', ref.run ?? '', ref.asOf ?? '', ref.dimension, ref.kind].join('\u0000');
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
 * @returns {Array<{ref: Object, scope: {principle: string|undefined, pathPrefix: string|undefined}, items: Array}>}
 */
export function groupDeferredFindings(items) {
  const byKey = new Map();
  for (const item of items || []) {
    if (!item?.detailDeferred || !item.detailRef) continue;
    const key = detailRefKey(item.detailRef);
    const group = byKey.get(key) ?? { ref: item.detailRef, items: [] };
    group.items.push(item);
    byKey.set(key, group);
  }
  return [...byKey.values()].map(({ ref, items: group }) => {
    const principles = new Set(group.map((i) => i.principle));
    const prefix = commonPrefix(group.map((i) => i.file || ''));
    return {
      ref,
      scope: {
        principle: principles.size === 1 ? [...principles][0] ?? undefined : undefined,
        pathPrefix: prefix || undefined,
      },
      items: group,
    };
  });
}

/** `groupDeferredFindings` under its pre-kind name. */
export const groupDeferredCompliance = groupDeferredFindings;

// The fields a page's items can agree on. A row the server sends belongs on
// the page when it matches every field the page's items are unanimous about:
// one file (the File page), one principle (the Principle page), one type or
// requirement code (a by-type file), one folder (a folder's synthetic file).
// A dimension's synthetic file agrees on none and takes the dimension whole.
const folderOf = (row) => {
  const file = row?.file;
  if (typeof file !== 'string') return null;
  const idx = file.lastIndexOf('/');
  return idx >= 0 ? file.slice(0, idx) : '';
};
const SELECTION_FIELDS = [
  ['file', (row) => row?.file],
  ['principle', (row) => row?.principle],
  ['violationType', (row) => row?.violationType],
  ['req', (row) => row?.req],
  ['folder', folderOf],
];

/**
 * The predicate that picks, among the rows the server sends for *items*'
 * groups, the ones that belong on the page holding *items*.
 * @param {Array} items
 * @returns {(row: Object) => boolean}
 */
export function pageSelector(items) {
  const wanted = [];
  for (const [, read] of SELECTION_FIELDS) {
    const values = new Set((items || []).map((i) => read(i) ?? null));
    if (values.size === 1 && !values.has(null)) wanted.push([read, [...values][0]]);
  }
  if (!wanted.length) return () => true;
  return (row) => wanted.every(([read, value]) => read(row) === value);
}

function selectedRows(loaded, select) {
  const byKey = new Map();
  for (const { ref, items: rows } of loaded) {
    byKey.set(detailRefKey(ref), (rows || []).filter(select).map((row) => ({ ...row, detailRef: ref, detailDeferred: false })));
  }
  return byKey;
}

const deferredKey = (item) => (item?.detailDeferred && item.detailRef ? detailRefKey(item.detailRef) : null);

/**
 * *items* with each loaded group's deferred items replaced, in the group's
 * first position, by the rows the server sent for it that *select* keeps.
 * Groups still loading keep their deferred items; failed groups are the
 * caller's business (see markDetailUnavailable).
 * @param {Array} items
 * @param {Array<{ref: Object, items: Array}>} loaded
 * @param {(row: Object) => boolean} select
 * @returns {Array}
 */
export function replaceWithDetail(items, loaded, select) {
  if (!loaded.length) return items;
  const rowsByKey = selectedRows(loaded, select);
  const placed = new Set();
  const out = [];
  for (const item of items) {
    const key = deferredKey(item);
    if (key === null || !rowsByKey.has(key)) {
      out.push(item);
    } else if (!placed.has(key)) {
      placed.add(key);
      out.push(...rowsByKey.get(key));
    }
  }
  return out;
}

const place = (i) => `${i.file}\u0000${i.line}`;

/**
 * True when a loaded group has no row at the file and line of one of its
 * deferred items: the list payload the page was built from names a finding
 * the server no longer has there (re-reported, moved or suppressed since).
 * @param {Array} items
 * @param {Array<{ref: Object, items: Array}>} loaded
 * @param {(row: Object) => boolean} select
 * @returns {boolean}
 */
export function missingFromDetail(items, loaded, select) {
  if (!loaded.length) return false;
  const rowsByKey = selectedRows(loaded, select);
  const placesByKey = new Map([...rowsByKey].map(([key, rows]) => [key, new Set(rows.map(place))]));
  return items.some((item) => {
    const key = deferredKey(item);
    const places = key === null ? undefined : placesByKey.get(key);
    return places !== undefined && !places.has(place(item));
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
  const failed = new Set(failedRefs.map(detailRefKey));
  return items.map((item) => (
    failed.has(deferredKey(item))
      ? { ...item, detailDeferred: false, detailUnavailable: true }
      : item
  ));
}
