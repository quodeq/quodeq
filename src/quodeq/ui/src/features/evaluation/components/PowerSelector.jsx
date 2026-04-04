import { useState } from 'react';
import { LEVELS, STORAGE_KEY } from './powerLevels.js';

const DEFAULT_POWER_LEVEL = 2;

export default function PowerSelector({ value, onChange, onPersist, labelPosition = 'right' }) {
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
          aria-label={`Power level ${level}`}
        />
      ))}
    </div>
  );

  return (
    <div className="power-selector" title={`Analysis power: ${currentLevel?.label}`}>
      {labelPosition === 'left' ? <>{label}{bars}</> : <>{bars}{label}</>}
    </div>
  );
}

export { LEVELS, STORAGE_KEY };
