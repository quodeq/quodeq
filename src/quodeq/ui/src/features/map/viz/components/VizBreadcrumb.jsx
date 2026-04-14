/**
 * Shared breadcrumb for all map visualizations.
 * Renders absolute-positioned top-left, matching Galaxy style.
 *
 * @param {{ items: Array<{ label: string, onClick?: () => void }> }} props
 *   Last item is the current location (no click). Earlier items are clickable ancestors.
 */

const BREADCRUMB_TOP = 8;
const BREADCRUMB_LEFT = 12;
const BREADCRUMB_GAP = 4;
const BREADCRUMB_FONT_SIZE = 12;
const BREADCRUMB_Z_INDEX = 2;
const BREADCRUMB_ITEM_PADDING = '3px 8px';
const BREADCRUMB_BORDER_RADIUS = 4;

export default function VizBreadcrumb({ items }) {
  if (!items || items.length === 0) return null;
  return (
    <div style={{ position: 'absolute', top: BREADCRUMB_TOP, left: BREADCRUMB_LEFT, display: 'flex', gap: BREADCRUMB_GAP, alignItems: 'center', fontSize: BREADCRUMB_FONT_SIZE, zIndex: BREADCRUMB_Z_INDEX }}>
      {items.map((item, i) => {
        const isLast = i === items.length - 1;
        const clickable = !isLast && !!item.onClick;
        return (
          <span key={i} style={{ display: 'flex', alignItems: 'center', gap: BREADCRUMB_GAP }}>
            {i > 0 && <span style={{ color: 'var(--color-border)' }}>{'\u203A'}</span>}
            <span
              style={{ color: isLast ? 'var(--color-text)' : 'var(--color-text-muted)', cursor: clickable ? 'pointer' : 'default', padding: BREADCRUMB_ITEM_PADDING, borderRadius: BREADCRUMB_BORDER_RADIUS, transition: 'all 0.2s' }}
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
