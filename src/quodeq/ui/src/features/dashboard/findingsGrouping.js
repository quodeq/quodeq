/**
 * Pure grouping behind the Overview's "fix first" and "where the findings
 * live" panels: the visible dimensions' findings by requirement and by
 * folder, most severe first.
 */
import { SEVERITY_ORDER } from '../../vocab/severity.js';

const ROOT_FOLDER = '';

function emptyCounts() {
  return { critical: 0, major: 0, minor: 0 };
}

function countSeverities(violations) {
  const counts = emptyCounts();
  for (const v of violations) {
    const sev = String(v.severity || '').toLowerCase();
    if (SEVERITY_ORDER.includes(sev)) counts[sev] += 1;
  }
  return counts;
}

/** A group's severity counts, size and distinct files. */
function summarize(list) {
  return { sev: countSeverities(list), count: list.length, fileCount: new Set(list.map((v) => v.file)).size };
}

/** Critical first, then major, then the most findings. */
function bySeverity(a, b) {
  return b.sev.critical - a.sev.critical || b.sev.major - a.sev.major || b.count - a.count;
}

/** The folder a file sits in, '' for a file at the root. */
export function dirOf(file) {
  const path = String(file || '');
  const idx = path.lastIndexOf('/');
  return idx >= 0 ? path.slice(0, idx) : ROOT_FOLDER;
}

/**
 * The leading folders every path shares, '' when they share none. Never a
 * whole path: each keeps at least its last folder.
 */
export function sharedPrefix(dirs) {
  if (dirs.length === 0) return '';
  const split = dirs.map((d) => d.split('/'));
  const first = split[0];
  const limit = Math.min(...split.map((parts) => parts.length)) - 1;
  let n = 0;
  while (n < limit && split.every((parts) => parts[n] === first[n])) n += 1;
  return first.slice(0, n).join('/');
}

function mostFrequent(values) {
  const counts = new Map();
  for (const v of values) if (v) counts.set(v, (counts.get(v) || 0) + 1);
  let best = null;
  for (const [v, n] of counts) if (best === null || n > counts.get(best)) best = v;
  return best;
}

/**
 * One row per requirement code per dimension. Findings without a code are
 * left out: they have no requirement to fix.
 * @param {Array<{dimension: string, violations?: Array}>} dimensions
 */
export function groupByRequirement(dimensions) {
  const groups = new Map();
  for (const dim of dimensions || []) {
    for (const v of dim.violations || []) {
      if (!v.req) continue;
      const key = `${dim.dimension}\0${v.req}`;
      if (!groups.has(key)) groups.set(key, { dimension: dim.dimension, req: v.req, list: [] });
      groups.get(key).list.push(v);
    }
  }
  return [...groups.values()].map(({ dimension, req, list }) => ({
    dimension,
    req,
    text: mostFrequent(list.map((v) => v.title)) || req,
    principle: mostFrequent(list.map((v) => v.principle || v.practiceId)) || '',
    ...summarize(list),
  })).sort(bySeverity);
}

/**
 * One row per real folder (two folders sharing their last names stay two
 * rows). `label` drops the prefix every finding shares, which the panel
 * shows once instead.
 * @param {Array<{violations?: Array}>} dimensions
 * @returns {{ prefix: string, rows: Array<{dir: string, label: string, sev: Object, count: number, fileCount: number}> }}
 */
export function groupByFolder(dimensions) {
  const groups = new Map();
  for (const dim of dimensions || []) {
    for (const v of dim.violations || []) {
      const dir = dirOf(v.file);
      if (!groups.has(dir)) groups.set(dir, []);
      groups.get(dir).push(v);
    }
  }
  const prefix = sharedPrefix([...groups.keys()]);
  const rows = [...groups.entries()].map(([dir, list]) => ({
    dir,
    label: dir.slice(prefix.length).replace(/^\//, ''),
    ...summarize(list),
  })).sort(bySeverity);
  return { prefix, rows };
}

/** A folder label as its muted lead and its last two folders. */
export function splitFolderLabel(label, tailDepth = 2) {
  const parts = String(label || '').split('/').filter(Boolean);
  const tail = parts.slice(-tailDepth).join('/');
  const lead = parts.length > tailDepth ? `${parts.slice(0, -tailDepth).join('/')}/` : '';
  return { lead, tail: tail ? `${tail}/` : '' };
}

/** The visible dimensions' findings and passing checks in one folder, by dimension. */
export function folderDimensions(dimensions, dir) {
  const inFolder = (item) => dirOf(item.file) === dir;
  return (dimensions || [])
    .map((d) => ({ ...d, violations: (d.violations || []).filter(inFolder), compliance: (d.compliance || []).filter(inFolder) }))
    .filter((d) => d.violations.length > 0);
}
