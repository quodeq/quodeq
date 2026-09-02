import { t } from '../../../../strings/index.js';

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
    hint: folderCount > 0 ? t('map.folderHint') : null,
    detailAction: !isRoot ? () => { if (onFileClick) onFileClick(cn); } : null,
  };
}
