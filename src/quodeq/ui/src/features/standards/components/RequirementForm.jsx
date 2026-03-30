import ReferenceEditor from './ReferenceEditor.jsx';

export default function RequirementForm({ requirement, principleIndex, reqIndex, onUpdateField, editable }) {
  const basePath = ['principles', principleIndex, 'requirements', reqIndex];

  return (
    <div className="requirement-form">
      <h3 className="detail-form-title">Requirement</h3>

      <div className="form-group">
        <label htmlFor={`req-text-${principleIndex}-${reqIndex}`}>Text</label>
        <textarea
          id={`req-text-${principleIndex}-${reqIndex}`}
          className="form-textarea"
          value={requirement.text || ''}
          onChange={(e) => onUpdateField([...basePath, 'text'], e.target.value)}
          disabled={!editable}
          placeholder="e.g. Source code dependencies must point inward only"
          rows={5}
          autoFocus={!requirement.text}
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
