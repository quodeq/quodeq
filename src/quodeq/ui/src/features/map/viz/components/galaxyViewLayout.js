import { TAU, seedHash, seededRng } from '../core/galaxyCore.js';

/**
 * Compute seeded cluster positions for constellation groups.
 * Returns an array of [x, y] pairs normalized around the origin.
 */
export function computeClusterPositions(groupKeys) {
  const n = groupKeys.length;
  if (n === 1) return [[0, 0]];

  const clusterRng = seededRng(seedHash('clusters:' + groupKeys.join(':')));
  const positions = groupKeys.map(() => {
    const angle = clusterRng() * TAU;
    const dist = 0.3 + clusterRng() * 0.5;
    return [Math.cos(angle) * dist, Math.sin(angle) * dist];
  });
  let cx = 0, cy = 0;
  positions.forEach(p => { cx += p[0]; cy += p[1]; });
  cx /= n; cy /= n;
  positions.forEach(p => { p[0] -= cx; p[1] -= cy; });
  return positions;
}

/**
 * Build MST constellation lines connecting all stars in a cluster.
 * @param {Array} clusterStars - Stars in the cluster (must have _ox, _oy)
 * @param {number} startIdx - Global index offset of first star in cluster
 * @returns {Array} lines - Array of { a, b } index pairs
 */
export function buildMSTLines(clusterStars, startIdx) {
  const lines = [];
  if (clusterStars.length < 2) return lines;

  const connected = new Set([0]);
  while (connected.size < clusterStars.length) {
    let bestA = -1, bestB = -1, bestD = Infinity;
    for (const ai of connected) {
      for (let bi = 0; bi < clusterStars.length; bi++) {
        if (connected.has(bi)) continue;
        const dx = clusterStars[ai]._ox - clusterStars[bi]._ox;
        const dy = clusterStars[ai]._oy - clusterStars[bi]._oy;
        const d = dx * dx + dy * dy;
        if (d < bestD) { bestD = d; bestA = ai; bestB = bi; }
      }
    }
    if (bestB >= 0) { lines.push({ a: startIdx + bestA, b: startIdx + bestB }); connected.add(bestB); }
    else break;
  }
  return lines;
}

/**
 * Apply repulsion between stars to enforce a minimum gap, then re-center.
 * Mutates _ox/_oy on each star in place.
 * @param {Array} clusterStars - Stars with _ox, _oy, radius
 * @param {number} [minGap=60] - Minimum distance between star edges
 */
export function applyRepulsionAndRecenter(clusterStars, minGap = 60) {
  const iters = clusterStars.length > 30 ? 3 : 6;
  for (let iter = 0; iter < iters; iter++) {
    for (let a = 0; a < clusterStars.length; a++) {
      for (let b = a + 1; b < clusterStars.length; b++) {
        const sa = clusterStars[a], sb = clusterStars[b];
        const dx = sb._ox - sa._ox, dy = sb._oy - sa._oy;
        const d = Math.sqrt(dx * dx + dy * dy) || 0.1;
        const minD = sa.radius + sb.radius + minGap;
        if (d < minD) {
          const push = (minD - d) / 2;
          const nx = dx / d, ny = dy / d;
          sa._ox -= nx * push; sa._oy -= ny * push;
          sb._ox += nx * push; sb._oy += ny * push;
        }
      }
    }
  }
  // Re-center after repulsion
  if (clusterStars.length > 0) {
    let rcx = 0, rcy = 0;
    clusterStars.forEach(s => { rcx += s._ox; rcy += s._oy; });
    rcx /= clusterStars.length; rcy /= clusterStars.length;
    clusterStars.forEach(s => { s._ox -= rcx; s._oy -= rcy; });
  }
}

/**
 * Build connections between dimensions that share violation files.
 * @param {Array} dimensions - Dimension data array
 * @returns {Array} connections - Array of { a, b, s } (indices and strength)
 */
export function buildSharedFileConnections(dimensions) {
  const dimFiles = dimensions.map(d => new Set((d.violations || []).map(v => v.file).filter(Boolean)));
  const connections = [];
  const fileToDims = new Map();
  dimFiles.forEach((files, idx) => {
    files.forEach(f => {
      if (!fileToDims.has(f)) fileToDims.set(f, []);
      fileToDims.get(f).push(idx);
    });
  });
  const sharedCounts = new Map();
  fileToDims.forEach((dimIdxs) => {
    for (let a = 0; a < dimIdxs.length; a++) {
      for (let b = a + 1; b < dimIdxs.length; b++) {
        const key = dimIdxs[a] < dimIdxs[b] ? `${dimIdxs[a]}-${dimIdxs[b]}` : `${dimIdxs[b]}-${dimIdxs[a]}`;
        sharedCounts.set(key, (sharedCounts.get(key) || 0) + 1);
      }
    }
  });
  sharedCounts.forEach((shared, key) => {
    const [i, j] = key.split('-').map(Number);
    const maxFiles = Math.max(dimFiles[i].size, dimFiles[j].size, 1);
    connections.push({ a: i, b: j, s: Math.min(1, shared / maxFiles) });
  });
  return connections;
}

/**
 * Compute max extent of the scene for fitZoom calculations.
 * @param {Array} stars - Star objects with _clusterCx, _clusterCy, _ox, _oy, radius
 * @param {Array} constellations - Constellation objects with cx, cy, spread
 * @returns {number} maxExtent
 */
export function computeMaxExtent(stars, constellations) {
  let maxX = 0, maxY = 0;
  stars.forEach(s => {
    const ex = Math.abs(s._clusterCx + s._ox) + s.radius * 2;
    const ey = Math.abs(s._clusterCy + s._oy) + s.radius * 2;
    if (ex > maxX) maxX = ex;
    if (ey > maxY) maxY = ey;
  });
  constellations.forEach(con => {
    const ex = Math.abs(con.cx) + con.spread + 40;
    const ey = Math.abs(con.cy) + con.spread + 50;
    if (ex > maxX) maxX = ex;
    if (ey > maxY) maxY = ey;
  });
  return Math.max(maxX, maxY);
}
