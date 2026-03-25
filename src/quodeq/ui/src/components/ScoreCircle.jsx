import { scoreGradeColorVar } from '../utils/formatters.js';

export default function ScoreCircle({ score, grade, size = 120 }) {
  const n = parseFloat(score);
  const fraction = isNaN(n) ? 0 : Math.min(n / 10, 1);
  const strokeColor = scoreGradeColorVar(score);

  const strokeWidth = size >= 100 ? 8 : 6;
  const radius = (size / 2) - (strokeWidth / 2) - 2;
  const circumference = 2 * Math.PI * radius;
  const dashoffset = circumference * (1 - fraction);

  const scoreFontSize = size >= 100 ? 30 : 20;
  const gradeFontSize = size >= 100 ? 13 : 10;

  return (
    <div className="score-circle" style={{ width: size, height: size, position: 'relative', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ transform: 'rotate(-90deg)' }}>
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
          <div style={{ fontSize: gradeFontSize, fontWeight: 600, color: strokeColor, marginTop: 2 }}>
            {grade}
          </div>
        )}
      </div>
    </div>
  );
}
