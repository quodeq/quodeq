/**
 * Badge — THE status pill/tag component. Every status chip (card sync state,
 * setup warnings, read-only markers, drawer chips) renders through this so
 * shape and tint stay consistent across every theme.
 *
 * tone      semantic color family; maps to --color-* tokens in badge.css
 * variant   'pill' (round micro-uppercase, project-card corners)
 *           'tag'  (squared mono, page headers and the drawer)
 * title     tooltip text
 * className extra class for LAYOUT-only tweaks (margins, ellipsis caps);
 *           visual identity must come from tone/variant, never the extra class
 */
const TONES = new Set(['neutral', 'accent', 'info', 'success', 'warning', 'danger']);

export default function Badge({ tone = 'neutral', variant = 'tag', title, className, children }) {
  const t = TONES.has(tone) ? tone : 'neutral';
  const cls = `badge badge--${variant} badge--${t}${className ? ` ${className}` : ''}`;
  return <span className={cls} title={title}>{children}</span>;
}
