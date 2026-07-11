import { useRef, useEffect } from 'react';
import ReferenceEditor from './ReferenceEditor.jsx';
import ThresholdFields from './ThresholdFields.jsx';
import SectionLabel from '../../../components/terminal/SectionLabel.jsx';
import { resolveRequirementText } from '../resolveRequirementText.js';

export default function RequirementForm({ requirement, principleIndex, reqIndex, onUpdateField, editable,
                                          reqOverrides, onChangeParam }) {
  const basePath = ['principles', principleIndex, 'requirements', reqIndex];
  const ruleRef = useRef(null);

  useEffect(() => {
    if (!requirement.text && ruleRef.current) ruleRef.current.focus();
  }, [principleIndex, reqIndex]);

  const hasParams = Boolean(requirement.params);
  const displayText = hasParams && !editable
    ? resolveRequirementText(requirement, reqOverrides)
    : requirement.text || '';

  return (
    <div className="requirement-form">
      <SectionLabel marker="▶">Requirement</SectionLabel>

      <div className="form-group">
        <label htmlFor={`req-text-${principleIndex}-${reqIndex}`}>Rule</label>
        <input
          ref={ruleRef}
          id={`req-text-${principleIndex}-${reqIndex}`}
          className="form-input"
          value={displayText}
          onChange={(e) => onUpdateField([...basePath, 'text'], e.target.value)}
          disabled={!editable}
          placeholder="e.g. Source code dependencies must point inward only"
        />
      </div>

      <div className="form-group">
        <label htmlFor={`req-desc-${principleIndex}-${reqIndex}`}>Description</label>
        <textarea
          id={`req-desc-${principleIndex}-${reqIndex}`}
          className="form-textarea"
          value={requirement.description || ''}
          onChange={(e) => onUpdateField([...basePath, 'description'], e.target.value)}
          disabled={!editable}
          placeholder="Context and rationale for this rule..."
          rows={3}
        />
      </div>

      <ReferenceEditor
        refs={requirement.refs || []}
        onChange={(updated) => onUpdateField([...basePath, 'refs'], updated)}
        disabled={!editable}
      />

      {hasParams && onChangeParam && (
        <ThresholdFields
          requirement={requirement}
          reqOverrides={reqOverrides}
          onChangeParam={onChangeParam}
        />
      )}
    </div>
  );
}
