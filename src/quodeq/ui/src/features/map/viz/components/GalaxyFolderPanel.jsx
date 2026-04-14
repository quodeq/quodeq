/**
 * Level-info panel overlay for GalaxyFolderView.
 */
export default function GalaxyFolderPanel({ levelInfo }) {
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
      {levelInfo.hint && (
        <div style={{ marginTop: 8, color: 'var(--color-text-muted)', fontSize: 11, fontStyle: 'italic', opacity: 0.6 }}>{levelInfo.hint}</div>
      )}
      {levelInfo.detailAction && (
        <button
          type="button"
          onClick={levelInfo.detailAction}
          style={{ marginTop: 10, width: '100%', padding: '6px 12px', background: 'color-mix(in srgb, var(--color-accent) 20%, transparent)', border: '1px solid var(--color-border)', borderRadius: 6, color: 'var(--color-text)', fontSize: 11, cursor: 'pointer', transition: 'all 0.2s' }}
          onMouseEnter={e => { e.target.style.background = 'color-mix(in srgb, var(--color-accent) 35%, transparent)'; }}
          onMouseLeave={e => { e.target.style.background = 'color-mix(in srgb, var(--color-accent) 20%, transparent)'; }}
        >View Details</button>
      )}
    </div>
  );
}
