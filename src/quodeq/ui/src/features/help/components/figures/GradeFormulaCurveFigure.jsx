// Simplified Q2 score-curve illustration for the Grade Formula help section.
// Solid line = base curve, dashed = violation ceiling. Colors come from
// theme tokens so the figure adapts to every theme family.
export default function GradeFormulaCurveFigure() {
  return (
    <div className="gf-curve-figure">
      <svg viewBox="0 0 320 96" preserveAspectRatio="none">
        <line x1="0" y1="88" x2="320" y2="88" stroke="var(--color-border)" strokeWidth="1" />
        <path
          d="M0,4 C80,8 160,26 240,46 C280,56 310,60 320,62"
          fill="none"
          stroke="var(--color-text-muted)"
          strokeWidth="1.5"
          strokeDasharray="4 4"
        />
        <path
          d="M0,8 C60,18 120,46 200,68 C250,80 300,85 320,86"
          fill="none"
          stroke="var(--color-accent)"
          strokeWidth="2"
        />
      </svg>
      <div className="gf-curve-figure__chips">
        <span className="severity-tag critical">critical 4.0</span>
        <span className="severity-tag major">major 1.5</span>
        <span className="severity-tag minor">minor 0.25</span>
      </div>
    </div>
  );
}
