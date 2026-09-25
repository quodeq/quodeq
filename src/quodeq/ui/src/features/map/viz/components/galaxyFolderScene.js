import {
  TAU, scoreRGB, sevRGB,
  seedHash, seededRng, mkBackgroundStars,
  RNG_MIDPOINT, MIN_SEPARATION_PX, REPULSION_PASSES_LARGE,
} from '../core/galaxyCore.js';
import { SEVERITY } from '../../../../vocab/severity.js';
import { SCORE_SCALE_MAX } from '../../../../constants.js';

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
const LARGE_SCENE_STARS = 50;
const MEDIUM_SCENE_STARS = 20;
const REPULSION_PASSES_MEDIUM = 5;
const REPULSION_PASSES_SMALL = 8;
const TARGET_RADIUS_FRACTION = 0.42;
const FOLDER_RADIUS_BASE_PX = 6; // before the sqrt-of-contents growth term
const FILE_RADIUS_BASE_PX = 5;
// The folder gap widens with the star count, up to this many stars.
const FOLDER_GAP_STAR_CAP = 20;
// Base pixel gap folders keep from neighbors before the star-count term.
const FOLDER_GAP_BASE_PX = 10;
// Fit margin, as a multiple of a star's radius (wider with particles).
const FIT_MARGIN_RATIO_WITH_PARTICLES = 3;
const FIT_MARGIN_RATIO_PLAIN = 2;

// Folder-nebula alert blips orbiting a folder star. `orbit*Ratio` are
// multiples of the star radius, speeds radians per time unit, sizes world
// units; `maxPerSeverity` caps how many a single severity contributes.
const FOLDER_ALERT = Object.freeze({
  maxPerSeverity: 3, orbitRadiusRatio: 1.5, orbitJitterRatio: 1,
  speedMin: 0.015, speedRange: 0.03, eccentricityBase: 0.7, eccentricityRange: 0.3,
  sizeCritical: 3.0, sizeCriticalRange: 0.7, sizeMajor: 2.3, sizeMajorRange: 0.5,
  sizeMinor: 1.6, sizeMinorRange: 0.4,
});

// Per-file violation particles: tighter, faster, smaller, less capped.
const FILE_PARTICLE = Object.freeze({
  maxPerSeverity: 10, orbitRadiusRatio: 1.2, orbitJitterRatio: 1.5,
  speedMin: 0.03, speedRange: 0.07, eccentricityBase: 0.65, eccentricityRange: 0.35,
  sizeCritical: 2.2, sizeCriticalRange: 0.5, sizeMajor: 1.8, sizeMajorRange: 0.4,
  sizeMinor: 1.2, sizeMinorRange: 0.3,
});

/* ── Scene builder ── */

export function countDescendants(node) {
  if (!node.children) return 0;
  let n = node.children.length;
  for (const c of node.children) n += countDescendants(c);
  return n;
}

// Severity draw order; changing it re-seeds every particle.
const ORBIT_SEVERITIES = [SEVERITY.CRITICAL, SEVERITY.MAJOR, SEVERITY.MINOR];

/** Violation particles orbiting a star: up to `cfg.maxPerSeverity` blips per
 * severity, seeded by *seedKey* so a star keeps its particles across renders.
 * The rng() call order per particle is part of the output; keep it. */
function _orbitParticles(seedKey, radius, sev, cfg) {
  const rng = seededRng(seedHash(seedKey));
  const sizes = {
    [SEVERITY.CRITICAL]: [cfg.sizeCritical, cfg.sizeCriticalRange],
    [SEVERITY.MAJOR]: [cfg.sizeMajor, cfg.sizeMajorRange],
    [SEVERITY.MINOR]: [cfg.sizeMinor, cfg.sizeMinorRange],
  };
  const particles = [];
  for (const sevName of ORBIT_SEVERITIES) {
    const col = sevRGB(sevName);
    const [sizeBase, sizeRange] = sizes[sevName];
    const count = Math.min(sev[sevName] || 0, cfg.maxPerSeverity);
    for (let j = 0; j < count; j++) {
      particles.push({
        col, sev: sevName,
        or: radius * cfg.orbitRadiusRatio + rng() * radius * cfg.orbitJitterRatio,
        os: (cfg.speedMin + rng() * cfg.speedRange) * (rng() > RNG_MIDPOINT ? 1 : -1),
        op: rng() * TAU,
        sz: sizeBase + rng() * sizeRange,
        ec: cfg.eccentricityBase + rng() * cfg.eccentricityRange,
        tp: rng() * TAU,
      });
    }
  }
  return particles;
}

/** Folder-nebula alert particles (critical/major/minor blips), seeded by path. */
function _buildFolderParticles(c, radius, sev) {
  if (!(sev.critical > 0 || sev.major > 0 || sev.minor > 0)) return [];
  return _orbitParticles((c.path || c.name) + ':fsev', radius, sev, FOLDER_ALERT);
}

/** Per-file violation particles orbiting a flagged file, seeded by path. */
function _buildFileParticles(c, radius) {
  if (!(c.violations > 0)) return [];
  return _orbitParticles((c.path || c.name) + ':fp', radius, c.severity || {}, FILE_PARTICLE);
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
      ? FOLDER_RADIUS_BASE_PX + Math.sqrt(Math.max(desc, 1)) * RADIUS_MULTIPLIER
      : FILE_RADIUS_BASE_PX + Math.sqrt(c.violations || 1) * RADIUS_MULTIPLIER;
    const rate = c.complianceRate || 0;
    const sev = c.severity || { critical: 0, major: 0, minor: 0 };
    const col = scoreRGB(rate * SCORE_SCALE_MAX);

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
  const folderGap = FOLDER_GAP_BASE_PX + Math.min(n, FOLDER_GAP_STAR_CAP) * 1.0;
  const fileGap = 1;
  const repulsionIters = rootStars.length > LARGE_SCENE_STARS ? REPULSION_PASSES_LARGE : rootStars.length > MEDIUM_SCENE_STARS ? REPULSION_PASSES_MEDIUM : REPULSION_PASSES_SMALL;
  for (let iter = 0; iter < repulsionIters; iter++) {
    for (let i = 0; i < rootStars.length; i++) {
      for (let j = i + 1; j < rootStars.length; j++) {
        const a = rootStars[i], b = rootStars[j];
        const dx = b.ox - a.ox, dy = b.oy - a.oy;
        const dist = Math.sqrt(dx * dx + dy * dy) || MIN_SEPARATION_PX;
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
    const margin = s.radius * (s.particles.length > 0 ? FIT_MARGIN_RATIO_WITH_PARTICLES : FIT_MARGIN_RATIO_PLAIN);
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

export function buildFolderScene(node, W, H) {
  const positioned = layoutChildren(node);
  const { rootStars, n } = placeRootStars(positioned, W, H);
  recenterStars(rootStars);
  applyRepulsion(rootStars, n);
  recenterStars(rootStars);
  const _maxExtent = normalizeToFit(rootStars, W, H);
  const lines = buildMST(rootStars);
  const bg = mkBackgroundStars(Math.random); // decorative, not seeded
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
