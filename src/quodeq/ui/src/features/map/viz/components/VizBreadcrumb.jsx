/**
 * Shared breadcrumb for all map visualizations.
 * Renders absolute-positioned top-left, matching Galaxy style.
 *
 * @param {{ items: Array<{ label: string, onClick?: () => void }> }} props
 *   Last item is the current location (no click). Earlier items are clickable ancestors.
 */
export default function VizBreadcrumb({ items }) {
  if (!items || items.length === 0) return null;
  return (
    <div style={{ position: 'absolute', top: 8, left: 12, display: 'flex', gap: 4, alignItems: 'center', fontSize: 12, zIndex: 2 }}>
      {items.map((item, i) => {
        const isLast = i === items.length - 1;
        const clickable = !isLast && !!item.onClick;
        return (
          <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            {i > 0 && <span style={{ color: 'var(--color-border)' }}>{'\u203A'}</span>}
            <span
              style={{ color: isLast ? 'var(--color-text)' : 'var(--color-text-muted)', cursor: clickable ? 'pointer' : 'default', padding: '3px 8px', borderRadius: 4, transition: 'all 0.2s' }}
              onClick={clickable ? item.onClick : undefined}
              onMouseEnter={clickable ? (e) => { e.target.style.background = 'color-mix(in srgb, var(--color-accent) 15%, transparent)'; e.target.style.color = 'var(--color-text)'; } : undefined}
              onMouseLeave={clickable ? (e) => { e.target.style.background = 'transparent'; e.target.style.color = 'var(--color-text-muted)'; } : undefined}
            >{item.label}</span>
          </span>
        );
      })}
    </div>
  );
}
