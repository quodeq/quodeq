import { scoreGradeColorVar } from '../utils/formatters.js';

const SIZE_BREAKPOINT = 100;
const STROKE_WIDTH_LARGE = 8;
const STROKE_WIDTH_SMALL = 6;
const SCORE_FONT_LARGE = 30;
const SCORE_FONT_SMALL = 20;
const GRADE_FONT_LARGE = 13;
const GRADE_FONT_SMALL = 10;
const RADIUS_MARGIN = 2;
const FRACTION_DIVISOR = 10;

export default function ScoreCircle({ score, grade, size = 120 }) {
  const n = parseFloat(score);
  const fraction = isNaN(n) ? 0 : Math.min(n / FRACTION_DIVISOR, 1);
  const strokeColor = scoreGradeColorVar(score);

  const strokeWidth = size >= SIZE_BREAKPOINT ? STROKE_WIDTH_LARGE : STROKE_WIDTH_SMALL;
  const radius = (size / 2) - (strokeWidth / 2) - RADIUS_MARGIN;
  const circumference = 2 * Math.PI * radius;
  const dashoffset = circumference * (1 - fraction);

  const scoreFontSize = size >= SIZE_BREAKPOINT ? SCORE_FONT_LARGE : SCORE_FONT_SMALL;
  const gradeFontSize = size >= SIZE_BREAKPOINT ? GRADE_FONT_LARGE : GRADE_FONT_SMALL;

  return (
    <div className="score-circle" style={{ width: size, height: size, position: 'relative', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ transform: 'rotate(-90deg)' }} aria-hidden="true">
        <circle
          cx={size / 2} cy={size / 2} r={radius}
          fill="none" stroke="var(--color-border)" strokeWidth={strokeWidth}
        />
        <circle
          cx={size / 2} cy={size / 2} r={radius}
          fill="none" stroke={strokeColor} strokeWidth={strokeWidth}
          strokeDasharray={circumference} strokeDashoffset={dashoffset}
          strokeLinecap="round"
        />
      </svg>
      <div style={{ position: 'absolute', textAlign: 'center', lineHeight: 1.2 }}>
        <div style={{ fontSize: scoreFontSize, fontWeight: 700, color: 'var(--color-text)', fontVariantNumeric: 'tabular-nums' }}>
          {isNaN(n) ? '—' : score}
        </div>
        {grade && (
          <div style={{ fontSize: gradeFontSize, fontWeight: 600, color: strokeColor, marginTop: RADIUS_MARGIN }}>
            {grade}
          </div>
        )}
      </div>
    </div>
  );
}
