import {
  TAU, scoreRGB, sevRGB,
  seedHash, seededRng,
} from '../core/galaxyCore.js';

/* ── Position consistency engine ── */

export function fingerprint(node) {
  const ch = node.children || [];
  return node.name + '|' + ch.map(c =>
    c.name + (c.violations || 0) + (c.isFile ? 'F' : 'D') + (c.complianceRate || 0).toFixed(1)
  ).join(':');
}

// Unwrap single-child folder chains that end in a file
export function unwrapLeaf(node) {
  let n = node;
  while (!n.isFile && n.children && n.children.length === 1) {
    const only = n.children[0];
    if (only.isFile || !only.children || only.children.length === 0) {
      return only;
    }
    n = only;
  }
  return node;
}

export function layoutChildren(node) {
  const ch = node.children || [];
  const resolved = ch.map(c => unwrapLeaf(c));
  const folders = resolved.filter(c => !c.isFile && c.children && c.children.length > 0);
  const files = resolved.filter(c => c.isFile || !c.children || c.children.length === 0);
  const folderSet = new Set(folders);
  const all = [...folders, ...files];
  const rng = seededRng(seedHash(fingerprint(node)));
  return all.map(child => ({
    child,
    isFolder: folderSet.has(child),
    angle: rng() * TAU,
    dist: rng(),
  }));
}

/* ── Physics / layout constants ── */

const BASE_FACTOR_MIN = 0.25;
const BASE_FACTOR_SCALE = 0.2;
const RADIUS_MULTIPLIER = 1.2;
const FOLDER_DIST_MIN = 0.35;
const FOLDER_DIST_MAX = 0.65;
const FILE_DIST_MIN = 0.2;
const FILE_DIST_MAX = 0.5;
const REPULSION_ITERATIONS = 50;
const REPULSION_RADIUS = 3;
const REPULSION_STRENGTH = 5;
const REPULSION_DECAY = 8;
const TARGET_RADIUS_FRACTION = 0.42;
const BG_STAR_COUNT = 120;

/* ── Scene builder ── */

export function countDescendants(node) {
  if (!node.children) return 0;
  let n = node.children.length;
  for (const c of node.children) n += countDescendants(c);
  return n;
}

/** Folder-nebula alert particles (critical/major/minor blips), seeded by path. */
function _buildFolderParticles(c, radius, sev) {
  const particles = [];
  if (!(sev.critical > 0 || sev.major > 0 || sev.minor > 0)) return particles;
  const fRng = seededRng(seedHash((c.path || c.name) + ':fsev'));
  const addAlert = (count, sevName) => {
    const sevCol = sevRGB(sevName);
    const pn = Math.min(count, 3);
    for (let j = 0; j < pn; j++) {
      particles.push({
        col: sevCol, sev: sevName,
        or: radius * 1.5 + fRng() * radius * 1.0,
        os: (0.015 + fRng() * 0.03) * (fRng() > 0.5 ? 1 : -1),
        op: fRng() * TAU,
        sz: sevName === 'critical' ? 3.0 + fRng() * 0.7 : sevName === 'major' ? 2.3 + fRng() * 0.5 : 1.6 + fRng() * 0.4,
        ec: 0.7 + fRng() * 0.3,
        tp: fRng() * TAU,
      });
    }
  };
  if (sev.critical > 0) addAlert(sev.critical, 'critical');
  if (sev.major > 0) addAlert(sev.major, 'major');
  if (sev.minor > 0) addAlert(sev.minor, 'minor');
  return particles;
}

/** Per-file violation particles orbiting a flagged file, seeded by path. */
function _buildFileParticles(c, radius) {
  const particles = [];
  if (!(c.violations > 0)) return particles;
  const sev = c.severity || { critical: 0, major: 0, minor: 0 };
  const rng2 = seededRng(seedHash((c.path || c.name) + ':fp'));
  const addP = (count, sevName) => {
    const pcol = sevRGB(sevName);
    for (let j = 0; j < Math.min(count, 10); j++) {
      particles.push({
        col: pcol, sev: sevName,
        or: radius * 1.2 + rng2() * radius * 1.5,
        os: (0.03 + rng2() * 0.07) * (rng2() > 0.5 ? 1 : -1),
        op: rng2() * TAU,
        sz: sevName === 'critical' ? 2.2 + rng2() * 0.5 : sevName === 'major' ? 1.8 + rng2() * 0.4 : 1.2 + rng2() * 0.3,
        ec: 0.65 + rng2() * 0.35,
        tp: rng2() * TAU,
      });
    }
  };
  addP(sev.critical || 0, 'critical');
  addP(sev.major || 0, 'major');
  addP(sev.minor || 0, 'minor');
  return particles;
}

/** Every root star's position/radius/color/particles, before repulsion. Returns `{ rootStars, n }`. */
function placeRootStars(positioned, W, H) {
  const rootStars = [];
  const n = positioned.length;
  const baseFactor = BASE_FACTOR_MIN + Math.sqrt(n) * BASE_FACTOR_SCALE;
  const spread = Math.min(W, H) * baseFactor;

  positioned.forEach((ip) => {
    const c = ip.child;
    const desc = ip.isFolder ? countDescendants(c) : 0;
    const radius = ip.isFolder
      ? 6 + Math.sqrt(Math.max(desc, 1)) * RADIUS_MULTIPLIER
      : 5 + Math.sqrt(c.violations || 1) * RADIUS_MULTIPLIER;
    const rate = c.complianceRate || 0;
    const sev = c.severity || { critical: 0, major: 0, minor: 0 };
    const col = scoreRGB(rate * 10);

    const distFactor = ip.isFolder ? (FOLDER_DIST_MIN + ip.dist * FOLDER_DIST_MAX) : (FILE_DIST_MIN + ip.dist * FILE_DIST_MAX);
    const dist = positioned.length === 1 ? 0 : spread * distFactor;
    const ox = Math.cos(ip.angle) * dist;
    const oy = Math.sin(ip.angle) * dist;

    const particles = ip.isFolder ? _buildFolderParticles(c, radius, sev) : _buildFileParticles(c, radius);

    rootStars.push({
      name: c.name,
      path: c.path,
      isFolder: ip.isFolder,
      violations: c.violations || 0,
      compliance: c.compliance || 0,
      complianceRate: rate,
      severity: sev,
      col, radius,
      ox, oy,
      pp: ip.angle,
      x: 0, y: 0,
      _node: c,
      particles,
    });
  });

  return { rootStars, n };
}

/** Shift every star so the group's centroid sits at the origin. */
function recenterStars(rootStars) {
  if (rootStars.length === 0) return;
  let cx = 0, cy = 0;
  rootStars.forEach(s => { cx += s.ox; cy += s.oy; });
  cx /= rootStars.length; cy /= rootStars.length;
  rootStars.forEach(s => { s.ox -= cx; s.oy -= cy; });
}

/** Push overlapping stars apart until every pair clears its gap (folders need more room than files). */
function applyRepulsion(rootStars, n) {
  const folderGap = 10 + Math.min(n, 20) * 1.0;
  const fileGap = 1;
  const repulsionIters = rootStars.length > REPULSION_ITERATIONS ? REPULSION_RADIUS : rootStars.length > 20 ? REPULSION_STRENGTH : REPULSION_DECAY;
  for (let iter = 0; iter < repulsionIters; iter++) {
    for (let i = 0; i < rootStars.length; i++) {
      for (let j = i + 1; j < rootStars.length; j++) {
        const a = rootStars[i], b = rootStars[j];
        const dx = b.ox - a.ox, dy = b.oy - a.oy;
        const dist = Math.sqrt(dx * dx + dy * dy) || 0.1;
        const gap = (!a.isFolder && !b.isFolder) ? fileGap : folderGap;
        const minDist = a.radius + b.radius + gap;
        if (dist < minDist) {
          const push = (minDist - dist) / 2;
          const nx = dx / dist, ny = dy / dist;
          a.ox -= nx * push;
          a.oy -= ny * push;
          b.ox += nx * push;
          b.oy += ny * push;
        }
      }
    }
  }
}

/** Scale the layout down (never up) to fit the target radius; returns the resulting max extent. */
function normalizeToFit(rootStars, W, H) {
  const targetR = Math.min(W, H) * TARGET_RADIUS_FRACTION;
  let maxExtent = 0;
  rootStars.forEach(s => {
    const margin = s.particles.length > 0 ? s.radius * 3 : s.radius * 2;
    const ext = Math.max(Math.abs(s.ox) + margin, Math.abs(s.oy) + margin);
    if (ext > maxExtent) maxExtent = ext;
  });
  if (maxExtent > targetR && maxExtent > 0) {
    const scale = targetR / maxExtent;
    rootStars.forEach(s => { s.ox *= scale; s.oy *= scale; });
    maxExtent = targetR;
  }
  return maxExtent;
}

/** Minimum spanning tree over the star positions, for the constellation lines. */
function buildMST(rootStars) {
  const lines = [];
  if (rootStars.length < 2) return lines;
  const connected = new Set([0]);
  while (connected.size < rootStars.length) {
    let bestA = -1, bestB = -1, bestD = Infinity;
    for (const ai of connected) {
      for (let bi = 0; bi < rootStars.length; bi++) {
        if (connected.has(bi)) continue;
        const dx = rootStars[ai].ox - rootStars[bi].ox;
        const dy = rootStars[ai].oy - rootStars[bi].oy;
        const d = dx * dx + dy * dy;
        if (d < bestD) { bestD = d; bestA = ai; bestB = bi; }
      }
    }
    if (bestB >= 0) {
      lines.push({ a: bestA, b: bestB });
      connected.add(bestB);
    } else break;
  }
  return lines;
}

/** Background starfield — decorative only, not part of the seeded layout. */
function buildBackgroundStars() {
  return Array.from({ length: BG_STAR_COUNT }, () => ({
    x: Math.random(), y: Math.random(),
    sz: Math.random() * 1.2,
    tw: Math.random() * TAU,
    sp: 0.3 + Math.random() * 0.7,
  }));
}

export function buildFolderScene(node, W, H) {
  const positioned = layoutChildren(node);
  const { rootStars, n } = placeRootStars(positioned, W, H);
  recenterStars(rootStars);
  applyRepulsion(rootStars, n);
  recenterStars(rootStars);
  const _maxExtent = normalizeToFit(rootStars, W, H);
  const lines = buildMST(rootStars);
  const bg = buildBackgroundStars();
  return { rootStars, lines, bg, _maxExtent };
}

export function buildNavPath(root, targetPath) {
  const path = [root];
  if (targetPath) {
    let cur = root;
    while (cur && cur.path !== targetPath) {
      const child = (cur.children || []).find(c => targetPath === c.path || targetPath.startsWith(c.path + '/'));
      if (!child) break;
      path.push(child);
      cur = child;
    }
  }
  return path;
}

// Level-info panel builder split out to galaxyFolderLevelInfo.js (self-
// contained; shares nothing with the layout math above) — re-exported so
// GalaxyFolderView.jsx keeps one import path.
export { buildLevelInfo } from './galaxyFolderLevelInfo.js';
