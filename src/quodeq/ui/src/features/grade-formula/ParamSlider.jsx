/**
 * Labeled range slider with numeric readout and a one-line hint.
 * Controlled: value/onChange. No free-text input by design.
 */
export default function ParamSlider({ label, value, min, max, step, hint, disabled, onChange }) {
  return (
    <div className="gf-slider-row">
      <label className="gf-slider-label">
        <span className="settings-label">{label}</span>
        <span className="gf-slider-value">{value}</span>
      </label>
      <input
        type="range"
        className="gf-slider"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        aria-label={label}
      />
      {hint ? <span className="settings-description">{hint}</span> : null}
    </div>
  );
}
