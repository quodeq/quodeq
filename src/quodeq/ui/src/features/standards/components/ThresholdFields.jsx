import { useState, useEffect } from 'react';
import { effectiveParamValue } from '../resolveRequirementText.js';
import { t } from '../../../strings/index.js';

// Was duplicated (inline) in handleChange and handleBlur before this
// extraction -- same bounds check, same semantics.
function isInRange(num, spec) {
  return (spec.min == null || num >= spec.min) && (spec.max == null || num <= spec.max);
}

function useThresholdDraft({ name, spec, effectiveValue, onChangeParam }) {
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
    if (raw !== '' && Number.isInteger(num) && isInRange(num, spec)) {
      onChangeParam(name, num);
      // out-of-range: do not fire; blur will restore effective value
    }
  }

  function handleBlur() {
    const num = Number(draft);
    const inRange = Number.isInteger(num) && isInRange(num, spec);
    if (draft === '' || !inRange) {
      // Invalid or out-of-range draft — snap back to effective value
      setDraft(String(effectiveValue));
    }
    setDirty(false);
  }

  return { draft, handleChange, handleBlur };
}

function ThresholdFieldRow({ name, spec, effectiveValue, overridden, onChangeParam, inputId }) {
  const { draft, handleChange, handleBlur } = useThresholdDraft({ name, spec, effectiveValue, onChangeParam });

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
        {t('standards.thresholdHint', { default: spec.default, min: spec.min, max: spec.max })}
      </span>
      {overridden && (
        <button
          type="button"
          className="threshold-reset-btn"
          onClick={() => onChangeParam(name, null)}
        >
          {t('standards.resetToDefault')}
        </button>
      )}
    </div>
  );
}

export default function ThresholdFields({ requirement, reqOverrides, onChangeParam }) {
  const params = requirement.params || {};
  return (
    <div className="threshold-fields">
      <div className="threshold-fields-title">{t('standards.thresholdsTitle')}</div>
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
