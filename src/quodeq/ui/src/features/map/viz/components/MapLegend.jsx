import { LEGEND_ITEMS } from '../core/galaxyCore.js';

/** Bottom-left color-key strip shared by GalaxyView, GalaxyFolderView and
 * ZoomablePackView. */
export default function MapLegend() {
  return (
    <div style={{ position: 'absolute', bottom: 8, left: 12, display: 'flex', gap: 14, fontSize: 11, color: 'var(--color-text-muted)', zIndex: 2 }}>
      {LEGEND_ITEMS.map(({ color, label }) => (
        <span key={label} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: color, display: 'inline-block' }} />{label}
        </span>
      ))}
    </div>
  );
}

/** Fixed-position tooltip anchor shared by GalaxyView and GalaxyFolderView. */
export function VizTooltipAnchor({ tooltipRef }) {
  return (
    <div
      ref={tooltipRef}
      style={{ position: 'fixed', display: 'none', background: 'color-mix(in srgb, var(--color-surface) 92%, transparent)', border: '1px solid var(--color-border)', borderRadius: 8, padding: '10px 14px', pointerEvents: 'none', fontSize: 12, zIndex: 10, boxShadow: '0 4px 20px rgba(0,0,0,0.3)', backdropFilter: 'blur(8px)', minWidth: 140 }}
    />
  );
}
