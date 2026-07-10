import { effectiveParamValue } from '../resolveRequirementText.js';

export default function ThresholdFields({ requirement, reqOverrides, onChangeParam }) {
  const params = requirement.params || {};
  return (
    <div className="threshold-fields">
      <div className="threshold-fields-title">Thresholds</div>
      {Object.entries(params).map(([name, spec]) => {
        const overridden = reqOverrides?.[name] != null;
        const value = effectiveParamValue(spec, reqOverrides?.[name]);
        const inputId = `threshold-${requirement.id}-${name}`;
        return (
          <div key={name} className="threshold-field-row">
            <label htmlFor={inputId}>{spec.label}</label>
            <input
              id={inputId}
              type="number"
              min={spec.min}
              max={spec.max}
              value={value}
              onChange={(e) => {
                const parsed = parseInt(e.target.value, 10);
                if (Number.isInteger(parsed)) onChangeParam(name, parsed);
              }}
            />
            <span className="threshold-field-hint">
              default {spec.default} · {spec.min} – {spec.max}
            </span>
            {overridden && (
              <button
                type="button"
                className="threshold-reset-btn"
                onClick={() => onChangeParam(name, null)}
              >
                Reset to default
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}
