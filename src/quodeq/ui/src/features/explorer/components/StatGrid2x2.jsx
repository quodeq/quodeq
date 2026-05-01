/**
 * StatGrid2x2 — small layout wrapper that renders its children as a 2-column
 * CSS grid. Children should be the existing terminal `Stat` component.
 */
export default function StatGrid2x2({ children }) {
  return <div className="qd-stats-2x2">{children}</div>;
}
