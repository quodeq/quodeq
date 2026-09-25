import { useMemo } from 'react';
import { LevelInfoPanel } from './galaxyViewInfo.jsx';
import { PERCENT } from '../../../../constants.js';

/** Compliance rate as a whole percentage, or a dash when nothing was checked. */
function complianceRate(d) {
  const total = d.violations + d.compliance;
  return total > 0 ? Math.round((d.compliance / total) * PERCENT) + '%' : '—';
}

/** How many direct children are folders and how many are files. */
function childCounts(children) {
  const kids = children || [];
  return {
    folders: kids.filter(c => !c.isFile && c.children?.length > 0).length,
    files: kids.filter(c => c.isFile || !c.children || c.children.length === 0).length,
  };
}

/** Breakdown lines for the severities that are actually present. */
function severityLines(sev) {
  const lines = [];
  if (sev.critical > 0) lines.push({ label: 'Critical', value: sev.critical, color: 'var(--color-sev-critical-text)' });
  if (sev.major > 0) lines.push({ label: 'Major', value: sev.major, color: 'var(--color-sev-major-text)' });
  if (sev.minor > 0) lines.push({ label: 'Minor', value: sev.minor, color: 'var(--color-sev-minor-text)' });
  return lines;
}

function computeLevelInfo(focusNode, root, onFileClick) {
  const fn = focusNode;
  if (!fn || !fn.data) return null;
  const d = fn.data;
  const isRoot = fn === root;
  const { folders, files } = childCounts(d.children);
  const lines = [
    { label: 'Compliance', value: complianceRate(d) },
    { label: 'Contents', value: folders + files },
    { label: 'Violations', value: d.violations },
  ];
  if (d.violations > 0) lines.push(...severityLines(d.severity || {}));
  const shortName = d.name?.includes('/') ? d.name.split('/')[0] : d.name;
  return {
    title: isRoot ? (d.name === '/' ? 'Project' : shortName) : shortName,
    lines,
    detailAction: !isRoot ? () => onFileClick?.(d) : null,
  };
}

export default function PackInfoPanel({ focusNode, root, onFileClick }) {
  const levelInfo = useMemo(() => computeLevelInfo(focusNode, root, onFileClick), [focusNode, root, onFileClick]);
  return <LevelInfoPanel levelInfo={levelInfo} />;
}
