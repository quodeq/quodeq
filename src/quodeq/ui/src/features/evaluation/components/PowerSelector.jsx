import { useState } from 'react';
import { LEVELS, STORAGE_KEY } from './powerLevels.js';
import { t } from '../../../strings/index.js';

const DEFAULT_POWER_LEVEL = 2;

// This component's own label-placement prop values.
const LABEL_POSITION = Object.freeze({ LEFT: 'left', RIGHT: 'right' });

export default function PowerSelector({ value, onChange, onPersist, labelPosition = LABEL_POSITION.RIGHT }) {
  const [hover, setHover] = useState(null);

  const active = value ?? DEFAULT_POWER_LEVEL;
  const display = hover ?? active;
  const currentLevel = LEVELS.find(l => l.level === display);

  function handleClick(level) {
    onChange(level);
    if (onPersist) onPersist(level);
  }

  const label = <span className="power-label">{currentLevel?.label}</span>;
  const bars = (
    <div className="power-bars" onMouseLeave={() => setHover(null)}>
      {LEVELS.map(({ level }) => (
        <button
          key={level}
          type="button"
          className={`power-bar power-bar--${level}${level <= display ? ' active' : ''}`}
          onClick={() => handleClick(level)}
          onMouseEnter={() => setHover(level)}
          aria-label={t('evaluate.powerLevelAria', { level })}
        />
      ))}
    </div>
  );

  return (
    <div className="power-selector" title={t('evaluate.analysisPower', { level: currentLevel?.label })}>
      {labelPosition === LABEL_POSITION.LEFT ? <>{label}{bars}</> : <>{bars}{label}</>}
    </div>
  );
}

export { LEVELS, STORAGE_KEY };
