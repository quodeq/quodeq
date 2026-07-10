import { useState, useEffect } from 'react';
import { effectiveParamValue } from '../resolveRequirementText.js';

function ThresholdFieldRow({ name, spec, effectiveValue, overridden, onChangeParam, inputId }) {
  const [draft, setDraft] = useState(String(effectiveValue));
  const [dirty, setDirty] = useState(false);

  // Sync draft when effective value changes from outside (e.g. reset)
  useEffect(() => {
    if (!dirty) {
      setDraft(String(effectiveValue));
    }
  }, [effectiveValue, dirty]);

  function handleChange(e) {
    const raw = e.target.value;
    setDraft(raw);
    setDirty(true);

    const num = Number(raw);
    if (raw !== '' && Number.isInteger(num)) {
      onChangeParam(name, num);
    }
  }

  function handleBlur() {
    const num = Number(draft);
    if (draft === '' || !Number.isInteger(num)) {
      // Invalid draft — snap back to effective value
      setDraft(String(effectiveValue));
    }
    setDirty(false);
  }

  return (
    <div className="threshold-field-row">
      <label htmlFor={inputId}>{spec.label}</label>
      <input
        id={inputId}
        type="number"
        min={spec.min}
        max={spec.max}
        value={draft}
        onChange={handleChange}
        onBlur={handleBlur}
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
}

export default function ThresholdFields({ requirement, reqOverrides, onChangeParam }) {
  const params = requirement.params || {};
  return (
    <div className="threshold-fields">
      <div className="threshold-fields-title">Thresholds</div>
      {Object.entries(params).map(([name, spec]) => {
        const overridden = reqOverrides?.[name] != null;
        const effectiveValue = effectiveParamValue(spec, reqOverrides?.[name]);
        const inputId = `threshold-${requirement.id}-${name}`;
        return (
          <ThresholdFieldRow
            key={name}
            name={name}
            spec={spec}
            effectiveValue={effectiveValue}
            overridden={overridden}
            onChangeParam={onChangeParam}
            inputId={inputId}
          />
        );
      })}
    </div>
  );
}
