import { useRef, useEffect } from 'react';
import ReferenceEditor from './ReferenceEditor.jsx';
import ThresholdFields from './ThresholdFields.jsx';
import SectionLabel from '../../../components/terminal/SectionLabel.jsx';
import { resolveRequirementText } from '../resolveRequirementText.js';
import { t } from '../../../strings/index.js';

function RuleField({ principleIndex, reqIndex, displayText, basePath, onUpdateField, editable, ruleRef }) {
  return (
    <div className="form-group">
      <label htmlFor={`req-text-${principleIndex}-${reqIndex}`}>{t('standards.ruleLabel')}</label>
      <input
        ref={ruleRef}
        id={`req-text-${principleIndex}-${reqIndex}`}
        className="form-input"
        value={displayText}
        onChange={(e) => onUpdateField([...basePath, 'text'], e.target.value)}
        disabled={!editable}
        placeholder={t('standards.rulePlaceholder')}
      />
    </div>
  );
}

function DescriptionField({ principleIndex, reqIndex, requirement, basePath, onUpdateField, editable }) {
  return (
    <div className="form-group">
      <label htmlFor={`req-desc-${principleIndex}-${reqIndex}`}>{t('standards.descriptionLabel')}</label>
      <textarea
        id={`req-desc-${principleIndex}-${reqIndex}`}
        className="form-textarea"
        value={requirement.description || ''}
        onChange={(e) => onUpdateField([...basePath, 'description'], e.target.value)}
        disabled={!editable}
        placeholder={t('standards.ruleDescPlaceholder')}
        rows={3}
      />
    </div>
  );
}

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
      <SectionLabel marker="▶">{t('standards.requirementLabel')}</SectionLabel>

      <RuleField principleIndex={principleIndex} reqIndex={reqIndex} displayText={displayText} basePath={basePath} onUpdateField={onUpdateField} editable={editable} ruleRef={ruleRef} />

      <DescriptionField principleIndex={principleIndex} reqIndex={reqIndex} requirement={requirement} basePath={basePath} onUpdateField={onUpdateField} editable={editable} />

      {hasParams && onChangeParam && (
        <ThresholdFields
          requirement={requirement}
          reqOverrides={reqOverrides}
          onChangeParam={onChangeParam}
        />
      )}

      <ReferenceEditor
        refs={requirement.refs || []}
        onChange={(updated) => onUpdateField([...basePath, 'refs'], updated)}
        disabled={!editable}
      />
    </div>
  );
}
