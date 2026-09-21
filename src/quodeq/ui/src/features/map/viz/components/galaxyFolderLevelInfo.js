import { t } from '../../../../strings/index.js';

// Most severe first, so the panel reads the same in both branches. Labels
// are resolved per build, not here, so a locale change is picked up.
const SEVERITY_LINES = [
  { key: 'critical', labelKey: 'map.critical', color: 'var(--color-sev-critical-text)' },
  { key: 'major', labelKey: 'map.major', color: 'var(--color-sev-major-text)' },
  { key: 'minor', labelKey: 'map.minor', color: 'var(--color-sev-minor-text)' },
];

// One panel line per non-zero severity. The folder branch tints its lines
// with the severity tokens; the zoomed-file branch leaves them plain.
function severityLines(counts, colored) {
  const sev = counts || {};
  return SEVERITY_LINES
    .filter(({ key }) => sev[key] > 0)
    .map(({ key, labelKey, color }) => {
      const label = t(labelKey);
      return colored ? { label, value: sev[key], color } : { label, value: sev[key] };
    });
}

/**
 * Build the level-info panel data object for the current view state.
 */
export function buildLevelInfo({ scene, currentNode, zoomedFileRef, navRef, projectName, onFileClick }) {
  if (!scene) return null;
  const zf = zoomedFileRef.current;
  if (zf && zf.data) {
    const s = zf.data;
    return {
      title: s.name,
      lines: [
        { label: t('map.violations'), value: s.violations },
        { label: t('map.compliance'), value: s.compliance },
        ...severityLines(s.severity, false),
      ],
      hint: null,
      detailAction: () => { if (onFileClick) onFileClick(s._node); },
    };
  }
  const cn = currentNode;
  const folderCount = scene.rootStars.filter(s => s.isFolder).length;
  const fileCount = scene.rootStars.filter(s => !s.isFolder).length;
  const rate = cn.complianceRate;
  const isRoot = navRef.current.path.length <= 1;
  const lines = [
    { label: t('map.compliance'), value: (rate * 100).toFixed(0) + '%' },
    { label: t('map.contents'), value: folderCount + fileCount },
    { label: t('map.violations'), value: cn.violations },
  ];
  if (cn.violations > 0) lines.push(...severityLines(cn.severity, true));
  return {
    title: isRoot ? (projectName || 'Project') : cn.name,
    lines,
    hint: folderCount > 0 ? t('map.folderHint') : null,
    detailAction: !isRoot ? () => { if (onFileClick) onFileClick(cn); } : null,
  };
}
