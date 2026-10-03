/**
 * Pure row-building for the By type view: one row per requirement code per
 * dimension, with the baseline count (from the run diff), the current count
 * (from the dimension's active findings) and the standard's text.
 */
import { buildProjectRootFile } from '../../utils/explorerUtils.js';

export const TYPE_GROUP = Object.freeze({ DIMENSION: 'dimension', PRINCIPLE: 'principle', TYPE: 'type' });

/** @returns {Map<string, {principle: string, text: string}>} */
export function requirementIndex(standard) {
  const index = new Map();
  for (const p of standard?.principles || []) {
    for (const r of p.requirements || []) {
      if (r?.id) index.set(r.id, { principle: p.name || '', text: r.text || '' });
    }
  }
  return index;
}

function diffEntry(diffsByRun, dim) {
  const entry = diffsByRun?.[dim.fromRunId]?.dimensions;
  if (!entry) return null;
  const key = Object.keys(entry).find((k) => k.toLowerCase() === String(dim.dimension).toLowerCase());
  return key ? entry[key] : null;
}

function currentByReq(violations) {
  const byReq = new Map();
  for (const v of violations || []) {
    if (!v.req) continue;
    const list = byReq.get(v.req) || [];
    list.push(v);
    byReq.set(v.req, list);
  }
  return byReq;
}

function baselineOf(perReq, req, hasBaseline) {
  if (!hasBaseline) return null;
  return perReq[req] ? perReq[req][0] : 0;
}

function rowFor({ dim, req, current, perReq, hasBaseline, index }) {
  const now = current.length;
  const baseline = baselineOf(perReq, req, hasBaseline);
  const fromStandard = index.get(req);
  return {
    key: `${dim.dimension}|${req}`,
    dimension: dim.dimension,
    principle: current[0]?.principle || fromStandard?.principle || '',
    req,
    text: fromStandard?.text || '',
    baseline,
    now,
    delta: baseline === null ? null : now - baseline,
    closed: baseline !== null && baseline > 0 && now === 0,
    violations: current,
    runId: dim.fromRunId,
    dateLabel: dim.fromDateLabel,
  };
}

function compareRows(a, b) {
  if (a.closed !== b.closed) return a.closed ? 1 : -1;
  if (b.now !== a.now) return b.now - a.now;
  return a.req.localeCompare(b.req);
}

/**
 * @param {{dimensions: Array, diffsByRun: Object, standardsByDim: Object}} input
 * @returns {Array<Object>} rows, sorted now desc, closed last, req asc
 */
export function buildTypeRows({ dimensions, diffsByRun, standardsByDim }) {
  const rows = [];
  for (const dim of dimensions || []) {
    const entry = diffEntry(diffsByRun, dim);
    const perReq = entry?.types?.perReq || {};
    const hasBaseline = Boolean(entry?.againstRunId);
    const index = requirementIndex(standardsByDim?.[dim.dimension]);
    const current = currentByReq(dim.violations);
    const reqs = new Set([...current.keys(), ...(hasBaseline ? Object.keys(perReq) : [])]);
    reqs.delete('');
    for (const req of reqs) {
      rows.push(rowFor({ dim, req, current: current.get(req) || [], perReq, hasBaseline, index }));
    }
  }
  return rows.sort(compareRows);
}

/** The synthetic file the file page opens for one type row. */
export function typeFile(row, dim, label) {
  return buildProjectRootFile([{ ...dim, violations: row.violations }], label);
}

function header(type, name, rows) {
  return {
    type,
    name,
    openTypes: rows.filter((r) => !r.closed).length,
    closedTypes: rows.filter((r) => r.closed).length,
  };
}

function groupBy(rows, pick) {
  const groups = new Map();
  for (const r of rows) {
    const k = pick(r);
    const list = groups.get(k) || [];
    list.push(r);
    groups.set(k, list);
  }
  return groups;
}

/** Rows with dimension and principle header entries in front of their groups. */
export function groupRows(rows) {
  const out = [];
  for (const [dimension, dimRows] of groupBy(rows, (r) => r.dimension)) {
    out.push(header(TYPE_GROUP.DIMENSION, dimension, dimRows));
    for (const [principle, pRows] of groupBy(dimRows, (r) => r.principle)) {
      out.push(header(TYPE_GROUP.PRINCIPLE, principle, pRows));
      for (const r of pRows) out.push({ type: TYPE_GROUP.TYPE, ...r });
    }
  }
  return out;
}
