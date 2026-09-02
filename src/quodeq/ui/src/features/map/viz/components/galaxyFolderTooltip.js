import { rgb } from '../core/galaxyCore.js';
import { escapeHtml } from '../../../../utils/escapeHtml.js';
import { countDescendants } from './galaxyFolderScene.js';
import { t } from '../../../../strings/index.js';

/**
 * Build the tooltip-update function bound to `refs`. Returns
 * `updateTooltip(cx, cy)`, which reads the currently hovered star (or
 * clears the tooltip if none/animating) and writes the HTML + position.
 */
export function createTooltipUpdater(refs) {
  return function updateTooltip(cx, cy) {
    const el = refs.tooltipRef.current;
    if (!el) return;
    const h = refs.hoveredRef.current;
    if (!h || refs.animRef.current) { el.style.display = 'none'; return; }
    const d = h.data;
    const row = (label, value, color) => `<div style="display:flex;justify-content:space-between;gap:12px;color:${color || 'var(--color-text-muted)'}"><span>${label}</span><span style="color:${color || 'var(--color-text)'};font-weight:500">${value}</span></div>`;
    const rows = [];
    const sev = d.severity || {};
    if (h.type === 'folder') {
      rows.push(row(t('map.compliance'), (d.complianceRate * 100).toFixed(0) + '%'));
      rows.push(row(t('map.violations'), d.violations));
      rows.push(row(t('map.contents'), countDescendants(d._node)));
    } else {
      rows.push(row(t('map.violations'), d.violations));
      rows.push(row(t('map.compliance'), d.compliance));
    }
    if (d.violations > 0) {
      if (sev.critical) rows.push(row(t('map.critical'), sev.critical, 'var(--color-sev-critical-text)'));
      if (sev.major) rows.push(row(t('map.major'), sev.major, 'var(--color-sev-major-text)'));
      if (sev.minor) rows.push(row(t('map.minor'), sev.minor, 'var(--color-sev-minor-text)'));
    }
    const nameCol = rgb(d.col);
    const name = d.name;
    const ff = refs.focusedFolderRef.current;
    const isFocused = h.type === 'folder' && ff && ff.starIdx === h.starIdx;
    // Whole-sentence keys, not "Click to " + a verb phrase: the fragment is
    // unassemblable in languages that order the clause differently.
    const hint = h.type === 'file' ? t('map.clickToZoomIn')
      : isFocused ? t('map.clickToEnterFolder') : t('map.clickToFocus');
    el.innerHTML = `<div style="font-weight:600;color:${nameCol};margin-bottom:4px">${escapeHtml(name)}</div>${rows.join('')}<div style="margin-top:6px;color:var(--color-text-muted);font-size:11px;opacity:0.6">${escapeHtml(hint)}</div>`;
    el.style.display = 'block';
    el.style.left = Math.min(cx + 16, window.innerWidth - 200) + 'px';
    el.style.top = Math.min(cy + 16, window.innerHeight - 160) + 'px';
  };
}
