import ReferenceEditor from './ReferenceEditor.jsx';

export default function RequirementForm({ requirement, principleIndex, reqIndex, onUpdateField, editable }) {
  const basePath = ['principles', principleIndex, 'requirements', reqIndex];

  return (
    <div className="requirement-form">
      <h3 className="detail-form-title">Requirement</h3>

      <div className="form-group">
        <label htmlFor={`req-text-${principleIndex}-${reqIndex}`}>Rule</label>
        <input
          id={`req-text-${principleIndex}-${reqIndex}`}
          className="form-input"
          value={requirement.text || ''}
          onChange={(e) => onUpdateField([...basePath, 'text'], e.target.value)}
          disabled={!editable}
          placeholder="e.g. Source code dependencies must point inward only"
          autoFocus={!requirement.text}
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
    </div>
  );
}
