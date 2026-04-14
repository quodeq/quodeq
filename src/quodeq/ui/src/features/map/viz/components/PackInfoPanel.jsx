import { useMemo } from 'react';

export default function PackInfoPanel({ focusNode, root, onFileClick }) {
  const levelInfo = useMemo(() => {
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
  }, [focusNode, root, onFileClick]);

  if (!levelInfo) return null;

  return (
    <div style={{ position: 'absolute', top: 12, right: 16, background: 'color-mix(in srgb, var(--color-surface) 88%, transparent)', border: '1px solid var(--color-border)', borderRadius: 10, padding: '12px 18px', fontSize: 12, zIndex: 2, backdropFilter: 'blur(8px)', minWidth: 160 }}>
      <div style={{ fontWeight: 600, color: 'var(--color-text)', marginBottom: 8, fontSize: 13 }}>{levelInfo.title}</div>
      {levelInfo.lines.map((l, i) => (
        <div key={i} style={{ display: 'flex', justifyContent: 'space-between', gap: 16, margin: '3px 0', color: l.color || 'var(--color-text-muted)' }}>
          <span>{l.label}</span>
          <span style={{ color: l.color || 'var(--color-text)', fontWeight: 500 }}>{l.value}</span>
        </div>
      ))}
      {levelInfo.detailAction && (
        <button type="button" onClick={levelInfo.detailAction}
          style={{ marginTop: 10, width: '100%', padding: '6px 12px', background: 'color-mix(in srgb, var(--color-accent) 20%, transparent)', border: '1px solid var(--color-border)', borderRadius: 6, color: 'var(--color-text)', fontSize: 11, cursor: 'pointer', transition: 'all 0.2s' }}
          onMouseEnter={e => { e.target.style.background = 'color-mix(in srgb, var(--color-accent) 35%, transparent)'; }}
          onMouseLeave={e => { e.target.style.background = 'color-mix(in srgb, var(--color-accent) 20%, transparent)'; }}
        >View Details</button>
      )}
    </div>
  );
}
