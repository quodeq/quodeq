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
  const all = [...folders, ...files];
  const rng = seededRng(seedHash(fingerprint(node)));
  return all.map(child => ({
    child,
    isFolder: folders.includes(child),
    angle: rng() * TAU,
    dist: rng(),
  }));
}

/* ── Scene builder ── */

export function countDescendants(node) {
  if (!node.children) return 0;
  let n = node.children.length;
  for (const c of node.children) n += countDescendants(c);
  return n;
}

export function buildFolderScene(node, W, H) {
  const positioned = layoutChildren(node);

  const rootStars = [];
  const n = positioned.length;
  const baseFactor = 0.25 + Math.sqrt(n) * 0.2;
  const spread = Math.min(W, H) * baseFactor;

  positioned.forEach((ip, i) => {
    const c = ip.child;
    const desc = ip.isFolder ? countDescendants(c) : 0;
    const radius = ip.isFolder
      ? 6 + Math.sqrt(Math.max(desc, 1)) * 1.2
      : 5 + Math.sqrt(c.violations || 1) * 1.2;
    const rate = c.complianceRate || 0;
    const sev = c.severity || { critical: 0, major: 0, minor: 0 };
    const col = scoreRGB(rate * 10);

    const distFactor = ip.isFolder ? (0.35 + ip.dist * 0.65) : (0.2 + ip.dist * 0.5);
    const dist = positioned.length === 1 ? 0 : spread * distFactor;
    const ox = Math.cos(ip.angle) * dist;
    const oy = Math.sin(ip.angle) * dist;

    let particles = [];
    if (ip.isFolder) {
      if (sev.critical > 0 || sev.major > 0 || sev.minor > 0) {
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
      }
    } else if (c.violations > 0) {
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
    }

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

  // Centroid correction
  if (rootStars.length > 0) {
    let cx = 0, cy = 0;
    rootStars.forEach(s => { cx += s.ox; cy += s.oy; });
    cx /= rootStars.length; cy /= rootStars.length;
    rootStars.forEach(s => { s.ox -= cx; s.oy -= cy; });
  }

  // Repulsion pass
  const folderGap = 10 + Math.min(n, 20) * 1.0;
  const fileGap = 1;
  const repulsionIters = rootStars.length > 50 ? 3 : rootStars.length > 20 ? 5 : 8;
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
  // Re-center after repulsion
  if (rootStars.length > 0) {
    let cx2 = 0, cy2 = 0;
    rootStars.forEach(s => { cx2 += s.ox; cy2 += s.oy; });
    cx2 /= rootStars.length; cy2 /= rootStars.length;
    rootStars.forEach(s => { s.ox -= cx2; s.oy -= cy2; });
  }

  // Normalize to fit
  const targetR = Math.min(W, H) * 0.42;
  let _maxExtent = 0;
  rootStars.forEach(s => {
    const margin = s.particles.length > 0 ? s.radius * 3 : s.radius * 2;
    const ext = Math.max(Math.abs(s.ox) + margin, Math.abs(s.oy) + margin);
    if (ext > _maxExtent) _maxExtent = ext;
  });
  if (_maxExtent > targetR && _maxExtent > 0) {
    const scale = targetR / _maxExtent;
    rootStars.forEach(s => { s.ox *= scale; s.oy *= scale; });
    _maxExtent = targetR;
  }

  // Minimum spanning tree
  const lines = [];
  if (rootStars.length >= 2) {
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
  }

  // Background
  const bg = Array.from({ length: 120 }, () => ({
    x: Math.random(), y: Math.random(),
    sz: Math.random() * 1.2,
    tw: Math.random() * TAU,
    sp: 0.3 + Math.random() * 0.7,
  }));

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

/**
 * Build the level-info panel data object for the current view state.
 */
export function buildLevelInfo({ scene, currentNode, zoomedFileRef, navRef, projectName, onFileClick }) {
  if (!scene) return null;
  const zf = zoomedFileRef.current;
  if (zf && zf.data) {
    const s = zf.data;
    const sev = s.severity || {};
    return {
      title: s.name,
      lines: [
        { label: 'Violations', value: s.violations },
        { label: 'Compliance', value: s.compliance },
        ...(sev.critical ? [{ label: 'Critical', value: sev.critical }] : []),
        ...(sev.major ? [{ label: 'Major', value: sev.major }] : []),
        ...(sev.minor ? [{ label: 'Minor', value: sev.minor }] : []),
      ],
      hint: null,
      detailAction: () => { if (onFileClick) onFileClick(s._node); },
    };
  }
  const cn = currentNode;
  const folderCount = scene.rootStars.filter(s => s.isFolder).length;
  const fileCount = scene.rootStars.filter(s => !s.isFolder).length;
  const rate = cn.complianceRate;
  const cnSev = cn.severity || {};
  const isRoot = navRef.current.path.length <= 1;
  const lines = [
    { label: 'Compliance', value: (rate * 100).toFixed(0) + '%' },
    { label: 'Contents', value: folderCount + fileCount },
    { label: 'Violations', value: cn.violations },
  ];
  if (cn.violations > 0) {
    if (cnSev.critical > 0) lines.push({ label: 'Critical', value: cnSev.critical, color: 'var(--color-sev-critical-text)' });
    if (cnSev.major > 0) lines.push({ label: 'Major', value: cnSev.major, color: 'var(--color-sev-major-text)' });
    if (cnSev.minor > 0) lines.push({ label: 'Minor', value: cnSev.minor, color: 'var(--color-sev-minor-text)' });
  }
  return {
    title: isRoot ? (projectName || 'Project') : cn.name,
    lines,
    hint: folderCount > 0 ? 'Click a folder to zoom in, click again to enter' : null,
    detailAction: !isRoot ? () => { if (onFileClick) onFileClick(cn); } : null,
  };
}
