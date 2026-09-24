/**
 * Compliance detail that /scores defers.
 *
 * /scores sends accumulated compliance items without `reason`, `snippet` and
 * `context` (flagged `detailDeferred`), since those fields were most of its
 * payload. Pages that render compliance cards fetch the detail from
 * /compliance-detail and merge it back by finding identity.
 */

/**
 * Tag each deferred compliance item with where its detail lives. One ref
 * object per dimension, shared by its items. `generation` tells two /scores
 * responses for the same project and asOf apart, so detail cached for an
 * older payload is never merged into a newer one.
 * @param {Object} data Parsed unified scores payload (mutated and returned).
 * @param {string} project
 * @param {string|null} asOf
 * @param {number} generation
 * @returns {Object}
 */
export function attachComplianceDetailRefs(data, project, asOf, generation) {
  for (const dim of data?.accumulated?.dimensions || []) {
    const ref = { project, asOf: asOf || null, dimension: dim.dimension, generation };
    for (const item of dim.compliance || []) {
      if (item?.detailDeferred) item.detailRef = ref;
    }
  }
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
export function groupDeferredCompliance(items) {
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

const identity = (i) => [i.file, i.line, i.endLine, i.principle, i.title].join('\u0000');

/**
 * Fill deferred items with the detail loaded for their ref. Items sharing an
 * identity take their details in server order, which is the order they
 * arrived in. Items with nothing loaded yet are returned as they were.
 * @param {Array} items
 * @param {Array<{ref: Object, items: Array}>} loaded
 * @returns {Array}
 */
export function mergeComplianceDetail(items, loaded) {
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
    return { ...item, reason: detail.reason, snippet: detail.snippet, context: detail.context, detailDeferred: false };
  });
}
