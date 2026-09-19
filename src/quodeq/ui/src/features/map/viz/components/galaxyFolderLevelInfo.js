import { t } from '../../../../strings/index.js';

// Most severe first, so the panel reads the same in both branches.
const SEVERITY_LINES = [
  { key: 'critical', label: 'Critical', color: 'var(--color-sev-critical-text)' },
  { key: 'major', label: 'Major', color: 'var(--color-sev-major-text)' },
  { key: 'minor', label: 'Minor', color: 'var(--color-sev-minor-text)' },
];

// One panel line per non-zero severity. The folder branch tints its lines
// with the severity tokens; the zoomed-file branch leaves them plain.
function severityLines(counts, colored) {
  const sev = counts || {};
  return SEVERITY_LINES
    .filter(({ key }) => sev[key] > 0)
    .map(({ key, label, color }) => (
      colored ? { label, value: sev[key], color } : { label, value: sev[key] }
    ));
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
        ...severityLines(sev, false),
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
  if (cn.violations > 0) lines.push(...severityLines(cnSev, true));
  return {
    title: isRoot ? (projectName || 'Project') : cn.name,
    lines,
    hint: folderCount > 0 ? t('map.folderHint') : null,
    detailAction: !isRoot ? () => { if (onFileClick) onFileClick(cn); } : null,
  };
}
