import { t } from '../../../../strings/index.js';
import { folderLines, severityLines } from './levelInfoLines.js';

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
        ...severityLines(s.severity, { colored: false }),
      ],
      hint: null,
      detailAction: () => { if (onFileClick) onFileClick(s._node); },
    };
  }
  const cn = currentNode;
  let folderCount = 0;
  for (const s of scene.rootStars) if (s.isFolder) folderCount += 1;
  const isRoot = navRef.current.path.length <= 1;
  return {
    title: isRoot ? (projectName || 'Project') : cn.name,
    lines: folderLines({
      complianceRate: cn.complianceRate,
      contents: scene.rootStars.length,
      violations: cn.violations,
      severity: cn.severity,
    }),
    hint: folderCount > 0 ? t('map.folderHint') : null,
    detailAction: !isRoot ? () => { if (onFileClick) onFileClick(cn); } : null,
  };
}
