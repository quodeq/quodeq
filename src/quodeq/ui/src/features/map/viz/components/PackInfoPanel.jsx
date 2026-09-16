import { useMemo } from 'react';
import { LevelInfoPanel } from './galaxyViewInfo.jsx';

function computeLevelInfo(focusNode, root, onFileClick) {
  const fn = focusNode;
  if (!fn || !fn.data) return null;
  const d = fn.data;
  const isRoot = fn === root;
  const sev = d.severity || {};
  const rate = (d.violations + d.compliance) > 0
    ? Math.round((d.compliance / (d.violations + d.compliance)) * 100) + '%'
    : '—';
  const childFolders = (d.children || []).filter(c => !c.isFile && c.children?.length > 0).length;
  const childFiles = (d.children || []).filter(c => c.isFile || !c.children || c.children.length === 0).length;
  const lines = [
    { label: 'Compliance', value: rate },
    { label: 'Contents', value: childFolders + childFiles },
    { label: 'Violations', value: d.violations },
  ];
  if (d.violations > 0) {
    if (sev.critical > 0) lines.push({ label: 'Critical', value: sev.critical, color: 'var(--color-sev-critical-text)' });
    if (sev.major > 0) lines.push({ label: 'Major', value: sev.major, color: 'var(--color-sev-major-text)' });
    if (sev.minor > 0) lines.push({ label: 'Minor', value: sev.minor, color: 'var(--color-sev-minor-text)' });
  }
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
