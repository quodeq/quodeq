import PrincipleForm from './PrincipleForm.jsx';
import RequirementForm from './RequirementForm.jsx';
import SectionLabel from '../../../components/terminal/SectionLabel.jsx';
import { t } from '../../../strings/index.js';
import { applyNameChange } from '../../../models/standard.js';

// Enough room for a couple of sentences without dominating the form.
const DESCRIPTION_ROWS = 4;

function EmptyState() {
  return (
    <p className="detail-empty-state">
      {t('standards.emptyDetailHint')}
    </p>
  );
}

// A labelled control in the root form. The label/control pairing and the
// disabled rule are the same for every field; only the control differs.
function FormGroup({ id, label, children }) {
  return (
    <div className="form-group">
      <label htmlFor={id}>{label}</label>
      {children}
    </div>
  );
}

function NameField({ standard, editable, isNew, onUpdateField }) {
  const handleNameChange = (e) => {
    const name = e.target.value;
    const updates = applyNameChange(standard, name, isNew);
    onUpdateField(['name'], updates.name);
    if ('id' in updates) {
      onUpdateField(['id'], updates.id);
    }
  };
  return (
    <FormGroup id="std-name" label={t('standards.colName')}>
      <input
        id="std-name"
        className="form-input"
        value={standard.name || ''}
        onChange={handleNameChange}
        disabled={!editable}
        placeholder={t('standards.namePlaceholder')}
        autoFocus={isNew}
      />
    </FormGroup>
  );
}

function DescriptionField({ standard, editable, onUpdateField }) {
  return (
    <FormGroup id="std-description" label={t('standards.descriptionLabel')}>
      <textarea
        id="std-description"
        className="form-textarea"
        value={standard.description || ''}
        onChange={(e) => onUpdateField(['description'], e.target.value)}
        disabled={!editable}
        placeholder={t('standards.describeStandardPlaceholder')}
        rows={DESCRIPTION_ROWS}
      />
    </FormGroup>
  );
}

function SourceField({ standard, editable, onUpdateField }) {
  return (
    <FormGroup id="std-source" label={t('standards.sourceLabel')}>
      <input
        id="std-source"
        className="form-input"
        value={standard.source || ''}
        onChange={(e) => onUpdateField(['source'], e.target.value)}
        disabled={!editable}
        placeholder={t('standards.sourcePlaceholder')}
      />
    </FormGroup>
  );
}

function RootDetail({ standard, onUpdateField, editable, isNew }) {
  return (
    <div className="standard-root-detail">
      <SectionLabel marker="▶">{t('standards.standardLabel')}</SectionLabel>
      <NameField standard={standard} editable={editable} isNew={isNew} onUpdateField={onUpdateField} />
      <DescriptionField standard={standard} editable={editable} onUpdateField={onUpdateField} />
      <SourceField standard={standard} editable={editable} onUpdateField={onUpdateField} />
      {standard.managed && <p className="detail-managed-notice">{t('standards.managedNotice')}</p>}
      {editable && (!standard.principles || standard.principles.length === 0) && <EmptyState />}
    </div>
  );
}

export default function StandardDetail({ standard, selectedNode, onUpdateField, editable, isNew, overrides, onChangeParam }) {
  if (!selectedNode || !standard) return null;

  if (selectedNode.type === 'root') {
    return <RootDetail standard={standard} onUpdateField={onUpdateField} editable={editable} isNew={isNew} />;
  }

  if (selectedNode.type === 'principle') {
    const principle = (standard.principles || [])[selectedNode.index];
    if (!principle) return null;
    return (
      <PrincipleForm
        principle={principle}
        principleIndex={selectedNode.index}
        onUpdateField={onUpdateField}
        editable={editable}
      />
    );
  }

  if (selectedNode.type === 'requirement') {
    const principle = (standard.principles || [])[selectedNode.principleIndex];
    if (!principle) return null;
    const requirement = (principle.requirements || [])[selectedNode.reqIndex];
    if (!requirement) return null;
    return (
      <RequirementForm
        key={requirement.id}
        requirement={requirement}
        principleIndex={selectedNode.principleIndex}
        reqIndex={selectedNode.reqIndex}
        onUpdateField={onUpdateField}
        editable={editable}
        reqOverrides={overrides?.[requirement.id]}
        onChangeParam={onChangeParam ? (name, v) => onChangeParam(requirement.id, name, v) : undefined}
      />
    );
  }

  return null;
}
