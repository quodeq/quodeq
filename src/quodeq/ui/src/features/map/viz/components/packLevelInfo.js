import { isDrillableFolder } from '../core/fileTree.js';
import { folderLines } from './levelInfoLines.js';

/** Share of checks that passed, or null when nothing was checked. */
function complianceRate(d) {
  const total = d.violations + d.compliance;
  return total > 0 ? d.compliance / total : null;
}

/** How many direct children there are, folders and files together. */
function childCount(children) {
  const kids = children || [];
  const folders = kids.filter(isDrillableFolder).length;
  const files = kids.filter((c) => c.isFile || !c.children || c.children.length === 0).length;
  return folders + files;
}

/** Level-info panel data for the pack view's focused circle, or null. */
export function computeLevelInfo(focusNode, root, onFileClick) {
  const fn = focusNode;
  if (!fn || !fn.data) return null;
  const d = fn.data;
  const isRoot = fn === root;
  const shortName = d.name?.includes('/') ? d.name.split('/')[0] : d.name;
  return {
    title: isRoot ? (d.name === '/' ? 'Project' : shortName) : shortName,
    lines: folderLines({
      complianceRate: complianceRate(d),
      contents: childCount(d.children),
      violations: d.violations,
      severity: d.severity,
    }),
    detailAction: !isRoot ? () => onFileClick?.(d) : null,
  };
}
